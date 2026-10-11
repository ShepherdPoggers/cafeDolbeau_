from time import sleep
from uuid import uuid4

from django.contrib.admin.models import CHANGE, DELETION, LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError, connection, transaction
from django.db.models import F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import AnnulationTransaction, Client, Employe, FusionClient, ParametresCafe, TransactionCafe
from .permissions import PERMISSION_BASE, PERMISSION_GERANT


COMPTEURS = (
    ("nombre_cafes_achetes", "variation_achetes", "Cafés achetés"),
    ("nombre_cafes_prepayes", "variation_prepayes", "Cafés prépayés"),
    ("nombre_cafes_gratuits", "variation_gratuits", "Cafés gratuits"),
)


def _avec_clients_verrouilles(clients, traitement):
    for tentative in range(6):
        try:
            with transaction.atomic():
                # Première requête : verrou d'écriture SQLite, ou de ligne
                # sur les moteurs qui prennent ces verrous en charge.
                if connection.vendor == "sqlite":
                    clients.update(nombre_cafes_achetes=F("nombre_cafes_achetes"))
                else:
                    list(clients.order_by("pk").select_for_update())
                return traitement(clients)
        except OperationalError as erreur:
            if connection.vendor != "sqlite" or "locked" not in str(erreur).lower() or tentative == 5:
                raise
            sleep(0.03 * (tentative + 1))


def _avec_client_verrouille(clients, traitement):
    # Une opération verrouille aussi l'autre participant d'une fusion en attente.
    # Les sous-requêtes évitent une lecture SQLite avant le verrou d'écriture.
    identifiants = clients.values("pk")
    fusions = FusionClient.objects.filter(statut=FusionClient.Statut.EN_ATTENTE).filter(
        Q(client_source_id__in=identifiants) | Q(client_destination_id__in=identifiants),
    )
    participants = Client.objects.filter(
        Q(pk__in=identifiants) | Q(pk__in=fusions.values("client_source_id"))
        | Q(pk__in=fusions.values("client_destination_id")),
    )
    return _avec_clients_verrouilles(participants, lambda verrouilles: traitement(clients.get()))


def _employe_actuel(employe):
    try:
        actuel = Employe.objects.get(pk=employe.pk)
    except Employe.DoesNotExist:
        raise PermissionDenied
    if not actuel.is_active or not actuel.has_perm(PERMISSION_BASE):
        raise PermissionDenied
    return actuel


def soldes_clients(clients):
    """Instantané signé par l'administration, revérifié sous verrou au POST."""
    return {
        str(client.pk): [getattr(client, compteur) for compteur, _, _ in COMPTEURS]
        for client in clients
    }


def _gerant_actuel(employe):
    acteur = _employe_actuel(employe)
    if not acteur.has_perm(PERMISSION_GERANT):
        raise PermissionDenied
    return acteur


def _compteurs_client(client):
    return {compteur: getattr(client, compteur) for compteur, _, _ in COMPTEURS}


def verifier_fusion_possible(source, destination):
    if source.pk == destination.pk or source.pk <= 0 or destination.pk <= 0:
        raise ValidationError("Choisissez deux clients distincts, sans le client fictif.")
    if not source.est_actif or not destination.est_actif:
        raise ValidationError("Les deux clients doivent être actifs.")
    if FusionClient.en_attente_pour(source.pk, destination.pk).exists():
        raise ValidationError("Un de ces clients participe déjà à une fusion réversible.")
    totaux = {
        compteur: getattr(source, compteur) + getattr(destination, compteur)
        for compteur, _, _ in COMPTEURS
    }
    if any(total > 2147483647 for total in totaux.values()):
        raise ValidationError("La fusion dépasse la limite des compteurs de cafés.")
    return totaux


def fusionner_clients(source_id, destination_id, *, employe, soldes_attendus=None):
    if any(type(pk) is not int or pk <= 0 for pk in (source_id, destination_id)) or source_id == destination_id:
        raise ValidationError("Choisissez deux clients distincts, sans le client fictif.")

    def fusionner(verrouilles):
        acteur = _gerant_actuel(employe)
        clients = verrouilles.in_bulk()
        if len(clients) != 2:
            raise ValidationError("Un des clients n'existe plus.")
        source, destination = clients[source_id], clients[destination_id]
        totaux = verifier_fusion_possible(source, destination)
        if soldes_attendus is not None and soldes_clients(clients.values()) != soldes_attendus:
            raise ValidationError("Les soldes ont changé. Vérifiez la nouvelle confirmation.", code="soldes_modifies")
        fusion = FusionClient.objects.create(
            client_source_id=source.pk, client_destination_id=destination.pk,
            source_nom=source.nom_complet, destination_nom=destination.nom_complet,
            soldes_source=_compteurs_client(source), soldes_destination=_compteurs_client(destination),
            transactions_deplacees=list(source.transactions_cafe.order_by("pk").values("id", "client_origine_id")),
            cree_par=acteur,
        )
        source.transactions_cafe.update(
            client_origine_id=Coalesce("client_origine_id", F("client_id")), client_id=destination.pk,
        )
        Client.objects.filter(pk=source.pk).update(est_actif=False)
        Client.objects.filter(pk=destination.pk).update(**totaux)
        LogEntry.objects.log_actions(
            user_id=acteur.pk, queryset=[source, destination], action_flag=CHANGE,
            change_message=f"Fusion #{fusion.pk} : {source.nom_complet} vers {destination.nom_complet}.",
        )
        return fusion

    return _avec_clients_verrouilles(Client.objects.filter(pk__in=[source_id, destination_id]), fusionner)


def annuler_fusion(fusion_id, *, employe):
    def annuler(verrouilles):
        acteur = _gerant_actuel(employe)
        fusion = FusionClient.objects.select_for_update().get(pk=fusion_id)
        if fusion.statut == FusionClient.Statut.ANNULEE:
            return fusion
        if fusion.statut != FusionClient.Statut.EN_ATTENTE:
            raise ValidationError("Cette fusion est définitive et ne peut plus être annulée.")
        clients = verrouilles.in_bulk()
        source = clients.get(fusion.client_source_id)
        destination = clients.get(fusion.client_destination_id)
        totaux = {compteur: fusion.soldes_source[compteur] + fusion.soldes_destination[compteur] for compteur, _, _ in COMPTEURS}
        if (source is None or destination is None or source.est_actif or not destination.est_actif
                or _compteurs_client(source) != fusion.soldes_source or _compteurs_client(destination) != totaux):
            raise ValidationError("Les comptes de la fusion ont changé. Le retour arrière est indisponible.")
        origines = {ligne["id"]: ligne["client_origine_id"] for ligne in fusion.transactions_deplacees}
        lignes = list(TransactionCafe.objects.filter(pk__in=origines, client=destination))
        if len(lignes) != len(origines):
            raise ValidationError("L'historique déplacé a changé. Le retour arrière est indisponible.")
        for ligne in lignes:
            ligne.client_id = source.pk
            ligne.client_origine_id = origines[ligne.pk]
        TransactionCafe.objects.bulk_update(lignes, ["client", "client_origine_id"])
        Client.objects.filter(pk=source.pk).update(est_actif=True, **fusion.soldes_source)
        Client.objects.filter(pk=destination.pk).update(**fusion.soldes_destination)
        fusion.statut = FusionClient.Statut.ANNULEE
        fusion.terminee_le = timezone.now()
        fusion.terminee_par = acteur
        fusion.save(update_fields=["statut", "terminee_le", "terminee_par"])
        LogEntry.objects.log_actions(user_id=acteur.pk, queryset=[source, destination], action_flag=CHANGE, change_message=f"Annulation de la fusion #{fusion.pk}.")
        return fusion

    fusions = FusionClient.objects.filter(pk=fusion_id)
    participants = Client.objects.filter(
        Q(pk__in=fusions.values("client_source_id")) | Q(pk__in=fusions.values("client_destination_id")),
    )
    return _avec_clients_verrouilles(participants, annuler)


def _finaliser_fusion(client, acteur, operation):
    fusion = FusionClient.en_attente_pour(client.pk).filter(client_destination_id=client.pk).first()
    if fusion is None:
        return
    sources = Client.objects.filter(pk=fusion.client_source_id)
    sources.update(nombre_cafes_achetes=F("nombre_cafes_achetes"))
    source = sources.get()
    fusion.statut = FusionClient.Statut.FINALISEE
    fusion.terminee_le = timezone.now()
    fusion.terminee_par = acteur
    fusion.operation_finalisation_id = operation
    fusion.save(update_fields=["statut", "terminee_le", "terminee_par", "operation_finalisation_id"])
    LogEntry.objects.log_actions(user_id=acteur.pk, queryset=[source], action_flag=DELETION, change_message=f"Finalisation de la fusion #{fusion.pk}.")
    source.delete()


def filtrer_meme_origine(lignes, source):
    origine = source.client_origine_id if source.client_origine_id is not None else source.client_id
    return lignes.filter(Q(client_origine_id=origine) | Q(client_origine_id__isnull=True, client_id=origine))


def supprimer_clients(client_ids, *, employe, soldes_attendus=None):
    """Transfère l'historique et journalise la suppression dans une transaction."""
    identifiants = set(client_ids)
    if Client.ID_SUPPRIME in identifiants:
        raise ValidationError("Le client fictif ne peut pas être supprimé.")

    def supprimer(verrouilles):
        acteur = _gerant_actuel(employe)
        clients = list(verrouilles.order_by("pk"))
        if FusionClient.en_attente_pour(*(client.pk for client in clients)).exists():
            raise ValidationError("Annulez ou finalisez la fusion avant de supprimer ces clients.")
        if soldes_attendus is not None and soldes_clients(clients) != soldes_attendus:
            raise ValidationError(
                "Les clients ou leurs soldes ont changé. Vérifiez la nouvelle confirmation.",
                code="soldes_modifies",
            )
        if not clients:
            return 0
        Client.objects.get_or_create(
            pk=Client.ID_SUPPRIME, defaults={"nom_complet": "Client supprimé", "est_actif": False},
        )
        TransactionCafe.objects.filter(client_id__in=[client.pk for client in clients]).update(
            client_origine_id=Coalesce("client_origine_id", F("client_id")), client_id=Client.ID_SUPPRIME,
        )
        LogEntry.objects.log_actions(user_id=acteur.pk, queryset=clients, action_flag=DELETION)
        verrouilles.delete()
        return len(clients)

    return _avec_clients_verrouilles(Client.objects.filter(pk__in=identifiants), supprimer)


def ajouter_cafes(client, quantite, type_transaction=TransactionCafe.Type.ACHAT, *, employe):
    """Enregistre ensemble les lignes et leurs effets, avec leur auteur."""
    if type_transaction not in (TransactionCafe.Type.ACHAT, TransactionCafe.Type.PREPAYE, TransactionCafe.Type.UTILISE):
        raise ValidationError("Type de transaction invalide.")
    if type(quantite) is not int or not 1 <= quantite <= 2147483647:
        raise ValidationError("Quantité de cafés invalide.")
    if client.pk == Client.ID_SUPPRIME:
        raise ValidationError("Impossible d'ajouter des cafés au client fictif.")

    def enregistrer(client_actuel):
        auteur = _employe_actuel(employe)
        if not client_actuel.est_actif:
            raise ValidationError("Ce client a été fusionné. Ouvrez la fiche du client conservé.")
        operation = uuid4()
        if type_transaction == TransactionCafe.Type.PREPAYE:
            if quantite > 2147483647 // 11:
                raise ValidationError("Nombre de cartes invalide.")
            cafes = quantite * 10
            lignes = [(TransactionCafe.Type.PREPAYE, cafes, (0, cafes, quantite))]
        else:
            gratuits_utilises = min(client_actuel.nombre_cafes_gratuits, quantite) if type_transaction == TransactionCafe.Type.UTILISE else 0
            prepayes_utilises = min(client_actuel.nombre_cafes_prepayes, quantite - gratuits_utilises) if type_transaction == TransactionCafe.Type.UTILISE else 0
            achetes = quantite - gratuits_utilises - prepayes_utilises
            total = client_actuel.nombre_cafes_achetes
            seuil = ParametresCafe.charger().cafes_pour_gratuite
            gratuits = (total + achetes) // seuil - total // seuil
            lignes = [
                (TransactionCafe.Type.UTILISE, prepayes_utilises + gratuits_utilises, (0, -prepayes_utilises, -gratuits_utilises)),
                (TransactionCafe.Type.ACHAT, achetes, (achetes, 0, 0)),
                (TransactionCafe.Type.GRATUIT, gratuits, (0, 0, gratuits)),
            ]
        resultats = []
        for type_cafe, nombre, effets in lignes:
            if nombre:
                ligne = TransactionCafe(
                    client=client_actuel, employe=auteur, operation_id=operation,
                    type_transaction=type_cafe, quantite=nombre,
                    **dict(zip((champ for _, champ, _ in COMPTEURS), effets)),
                )
                ligne.full_clean()
                ligne.save()
                resultats.append(ligne)
        nouveaux_soldes = {
            compteur: getattr(client_actuel, compteur) + sum(getattr(ligne, variation) for ligne in resultats)
            for compteur, variation, _ in COMPTEURS
        }
        if any(not 0 <= valeur <= 2147483647 for valeur in nouveaux_soldes.values()):
            raise ValidationError("L'opération dépasse la limite des compteurs de cafés.")
        Client.objects.filter(pk=client_actuel.pk).update(**nouveaux_soldes)
        _finaliser_fusion(client_actuel, auteur, operation)
        return resultats

    return _avec_client_verrouille(Client.objects.filter(pk=client.pk), enregistrer)


def valider_effets(ligne, effets):
    if len(effets) != 3 or any(type(valeur) is not int or abs(valeur) > 2147483647 for valeur in effets):
        raise ValidationError("Renseignez les trois variations avec des nombres entiers valides.")
    if not any(effets):
        raise ValidationError("Une transaction doit avoir au moins un effet sur les compteurs.")
    consommation = ligne.type_transaction == TransactionCafe.Type.UTILISE
    if consommation and (effets[0] != 0 or any(valeur > 0 for valeur in effets)):
        raise ValidationError("Une consommation diminue les soldes prépayés/gratuits et ne modifie pas les achats.")
    if not consommation and any(valeur < 0 for valeur in effets):
        raise ValidationError("Un achat ou un crédit doit avoir des variations positives ou nulles.")

# Annulation des transactions prémigration.
def preparer_annulation(source, employe, details_anciennes=None):
    gerant = employe.is_active and employe.has_perm(PERMISSION_GERANT)
    if not employe.is_active or not employe.has_perm(PERMISSION_BASE):
        raise PermissionDenied
    if source.client_id == Client.ID_SUPPRIME and not gerant:
        raise PermissionDenied
    if FusionClient.en_attente_pour(source.client_id).exists():
        raise ValidationError("Annulez ou finalisez la fusion avant d'annuler une transaction de ces clients.")
    if source.operation_id:
        lignes = list(TransactionCafe.objects.filter(
            client_id=source.client_id, operation_id=source.operation_id,
        ).select_related("employe", "annulation__employe"))
        if not gerant and any(ligne.employe_id != employe.pk for ligne in lignes):
            raise PermissionDenied
        if all(ligne.annulee for ligne in lignes):
            return lignes
        if any(ligne.annulee for ligne in lignes):
            raise ValidationError("L’opération comporte une annulation partielle. Contactez l’administrateur.")
        if details_anciennes is not None:
            raise ValidationError("L’opération a changé. Actualisez le récapitulatif.")
        if any(getattr(ligne, variation) is None for ligne in lignes for _, variation, _ in COMPTEURS):
            raise ValidationError("Les effets de cette opération sont incomplets.")
        return lignes
    if not gerant:
        raise PermissionDenied
    if source.annulee:
        return [source]
    if not details_anciennes or source.pk not in details_anciennes:
        raise ValidationError("Complétez l’ancienne opération et incluez la transaction sélectionnée.")
    lignes = list(filtrer_meme_origine(TransactionCafe.objects.filter(
        pk__in=details_anciennes, client_id=source.client_id,
        operation_id__isnull=True, annulation__isnull=True,
    ), source).select_related("employe", "annulation"))
    if len(lignes) != len(details_anciennes):
        raise ValidationError("Choisissez uniquement les anciennes transactions non annulées de ce client.")
    for ligne in lignes:
        effets = details_anciennes[ligne.pk]
        valider_effets(ligne, effets)
        for (_, variation, _), valeur in zip(COMPTEURS, effets):
            setattr(ligne, variation, valeur)
    return lignes


def recapitulatif_annulation(client, lignes):
    if client.pk == Client.ID_SUPPRIME:
        return []
    return [
        {
            "libelle": libelle,
            "avant": getattr(client, compteur),
            "apres": max(0, getattr(client, compteur) - sum(getattr(ligne, variation) for ligne in lignes)),
        }
        for compteur, variation, libelle in COMPTEURS
    ]


def annuler_operation(transaction_id, employe, details_anciennes=None):
    def annuler(client):
        acteur = _employe_actuel(employe)
        source = TransactionCafe.objects.select_related("annulation").get(pk=transaction_id, client=client)
        lignes = preparer_annulation(source, acteur, details_anciennes)
        if all(ligne.annulee for ligne in lignes):
            return 0
        nouveaux_soldes = recapitulatif_annulation(client, lignes)
        if source.operation_id is None:
            operation = uuid4()
            for ligne in lignes:
                ligne.operation_id = operation
                ligne.save(update_fields=["operation_id", *(variation for _, variation, _ in COMPTEURS)])
        date = timezone.now()
        for ligne in lignes:
            AnnulationTransaction.objects.create(transaction=ligne, employe=acteur, date_annulation=date)
        if client.pk != Client.ID_SUPPRIME:
            Client.objects.filter(pk=client.pk).update(**{
                compteur: solde["apres"] for (compteur, _, _), solde in zip(COMPTEURS, nouveaux_soldes)
            })
        return len(lignes)

    clients = Client.objects.filter(transactions_cafe__pk=transaction_id)
    return _avec_client_verrouille(clients, annuler)
