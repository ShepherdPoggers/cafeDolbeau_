from time import sleep
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError, connection, transaction
from django.db.models import F
from django.utils import timezone

from .models import AnnulationTransaction, Client, Employe, TransactionCafe
from .permissions import PERMISSION_BASE, PERMISSION_GERANT


COMPTEURS = (
    ("nombre_cafes_achetes", "variation_achetes", "Cafés achetés"),
    ("nombre_cafes_prepayes", "variation_prepayes", "Cafés prépayés"),
    ("nombre_cafes_gratuits", "variation_gratuits", "Cafés gratuits"),
)


def _avec_client_verrouille(clients, traitement):
    for tentative in range(6):
        try:
            with transaction.atomic():
                # Première requête : verrou d'écriture SQLite, ou de ligne
                # sur les moteurs qui prennent ces verrous en charge.
                if not clients.update(
                    nombre_cafes_achetes=F("nombre_cafes_achetes"),
                ):
                    raise Client.DoesNotExist
                return traitement(clients.get())
        except OperationalError as erreur:
            if connection.vendor != "sqlite" or "locked" not in str(erreur).lower() or tentative == 5:
                raise
            sleep(0.03 * (tentative + 1))


def _employe_actuel(employe):
    try:
        actuel = Employe.objects.get(pk=employe.pk)
    except Employe.DoesNotExist:
        raise PermissionDenied
    if not actuel.is_active or not actuel.has_perm(PERMISSION_BASE):
        raise PermissionDenied
    return actuel


def ajouter_cafes(client, quantite, type_transaction=TransactionCafe.Type.ACHAT, *, employe):
    """Enregistre ensemble les lignes et leurs effets, avec leur auteur."""
    if type_transaction not in (TransactionCafe.Type.ACHAT, TransactionCafe.Type.PREPAYE, TransactionCafe.Type.UTILISE):
        raise ValidationError("Type de transaction invalide.")
    if type(quantite) is not int or not 1 <= quantite <= 2147483647:
        raise ValidationError("Quantité de cafés invalide.")

    def enregistrer(client_actuel):
        auteur = _employe_actuel(employe)
        operation = uuid4()
        if type_transaction == TransactionCafe.Type.PREPAYE:
            if quantite > 2147483647 // 11:
                raise ValidationError("Nombre de cartes invalide.")
            cafes = quantite * 10
            lignes = [(TransactionCafe.Type.PREPAYE, cafes, (cafes, cafes, quantite))]
        else:
            gratuits_utilises = min(client_actuel.nombre_cafes_gratuits, quantite) if type_transaction == TransactionCafe.Type.UTILISE else 0
            prepayes_utilises = min(client_actuel.nombre_cafes_prepayes, quantite - gratuits_utilises) if type_transaction == TransactionCafe.Type.UTILISE else 0
            achetes = quantite - gratuits_utilises - prepayes_utilises
            total = client_actuel.nombre_cafes_achetes
            gratuits = (total + achetes) // 10 - total // 10
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
        Client.objects.filter(pk=client_actuel.pk).update(**{
            compteur: F(compteur) + sum(getattr(ligne, variation) for ligne in resultats)
            for compteur, variation, _ in COMPTEURS
        })
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
    lignes = list(TransactionCafe.objects.filter(
        pk__in=details_anciennes, client_id=source.client_id,
        operation_id__isnull=True, annulation__isnull=True,
    ).select_related("employe", "annulation"))
    if len(lignes) != len(details_anciennes):
        raise ValidationError("Choisissez uniquement les anciennes transactions non annulées de ce client.")
    for ligne in lignes:
        effets = details_anciennes[ligne.pk]
        valider_effets(ligne, effets)
        for (_, variation, _), valeur in zip(COMPTEURS, effets):
            setattr(ligne, variation, valeur)
    return lignes


def recapitulatif_annulation(client, lignes):
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
        Client.objects.filter(pk=client.pk).update(**{
            compteur: solde["apres"] for (compteur, _, _), solde in zip(COMPTEURS, nouveaux_soldes)
        })
        return len(lignes)

    clients = Client.objects.filter(transactions_cafe__pk=transaction_id)
    return _avec_client_verrouille(clients, annuler)
