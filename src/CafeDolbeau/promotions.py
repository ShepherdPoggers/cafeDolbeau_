"""Compteurs promotionnels et instantanés, utilisés sous les verrous des clients."""
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import CompteurPromotion, Promotion, Succursale


LIMITE = 2147483647


def promotion_courante(succursale_id, *, verrouiller=False):
    if verrouiller:
        Succursale.objects.select_for_update().get(pk=succursale_id)
    jour = timezone.localdate()
    promotions = Promotion.objects.filter(
        affectations__succursale_id=succursale_id,
        date_debut__lte=jour, date_fin__gte=jour, annulee_le__isnull=True,
    )
    if verrouiller:
        promotions = promotions.select_for_update(of=("self",))
    return promotions.first()


def contexte_promotion(client, succursale_id):
    promotion = promotion_courante(succursale_id)
    if promotion is None:
        return None
    compteur = CompteurPromotion.objects.filter(client=client, promotion=promotion).first()
    return {
        "id": promotion.pk, "nom": promotion.nom, "seuil": promotion.cafes_pour_gratuite,
        "fin": promotion.date_fin.isoformat(),
        "progression": compteur.progression if compteur else 0,
        "gratuits": compteur.cafes_gratuits if compteur else 0,
    }


def instantane_promotions(client):
    return {
        str(ligne.promotion_id): [ligne.progression, ligne.cafes_gratuits]
        for ligne in CompteurPromotion.objects.filter(client=client).order_by("promotion_id")
    }


def fusionner_compteurs(source, destination):
    avant_source, avant_destination = instantane_promotions(source), instantane_promotions(destination)
    resultat = dict(avant_destination)
    seuils = dict(Promotion.objects.filter(pk__in=avant_source).values_list("pk", "cafes_pour_gratuite"))
    for identifiant, (progression, gratuits) in avant_source.items():
        progression_destination, gratuits_destination = resultat.get(identifiant, [0, 0])
        total_gratuits = gratuits + gratuits_destination
        if total_gratuits > LIMITE:
            raise ValidationError("La fusion dépasse la limite des cafés promotionnels.")
        resultat[identifiant] = [(progression + progression_destination) % seuils[int(identifiant)], total_gratuits]
    restaurer_compteurs(destination, resultat)
    return avant_source, avant_destination, resultat


def restaurer_compteurs(client, instantane):
    CompteurPromotion.objects.filter(client=client).exclude(promotion_id__in=instantane).delete()
    for identifiant, (progression, gratuits) in instantane.items():
        CompteurPromotion.objects.update_or_create(
            client=client, promotion_id=int(identifiant),
            defaults={"progression": progression, "cafes_gratuits": gratuits},
        )


def effets_annulation_promotion(client, lignes):
    """Inverse les effets enregistrés ; une promotion expirée reste inutilisable."""
    effets = {}
    for ligne in lignes:
        if ligne.promotion_id:
            progression, gratuits = effets.get(ligne.promotion_id, (0, 0))
            effets[ligne.promotion_id] = (
                progression + ligne.variation_progression_promotion,
                gratuits + ligne.variation_gratuits_promotion,
            )
    resultat = []
    for identifiant, (progression, gratuits) in effets.items():
        compteur = CompteurPromotion.objects.filter(client=client, promotion_id=identifiant).select_related("promotion").first()
        if compteur is None:
            raise ValidationError("Le compteur de cette promotion est introuvable.")
        resultat.append((compteur, (compteur.progression - progression) % compteur.promotion.cafes_pour_gratuite,
                         max(0, compteur.cafes_gratuits - gratuits)))
    if any(gratuits > LIMITE for _, _, gratuits in resultat):
        raise ValidationError("L’annulation dépasse la limite des cafés promotionnels.")
    return resultat


def annuler_promotion(promotion_id, *, employe, motif=""):
    """Arrêt définitif, sérialisé avec les achats et la planification."""
    from django.contrib.admin.models import CHANGE, LogEntry
    from django.core.exceptions import PermissionDenied
    from django.db import transaction
    from .models import Employe
    from .permissions import est_proprietaire

    if not isinstance(motif, str) or len(motif.strip()) > 500:
        raise ValidationError("Le motif doit contenir au maximum 500 caractères.")
    with transaction.atomic():
        acteur = Employe.objects.get(pk=employe.pk)
        if not est_proprietaire(acteur):
            raise PermissionDenied
        list(Succursale.objects.order_by("pk").select_for_update())
        promotion = Promotion.objects.select_for_update().get(pk=promotion_id)
        if promotion.annulee_le:
            return False
        jour = timezone.localdate()
        if not promotion.date_debut <= jour <= promotion.date_fin:
            raise ValidationError("Seule une promotion en cours peut être annulée.")
        Promotion.objects.filter(pk=promotion.pk).update(
            annulee_le=timezone.now(), annulee_par=acteur, motif_annulation=motif.strip(),
        )
        LogEntry.objects.log_actions(
            user_id=acteur.pk, queryset=[promotion], action_flag=CHANGE,
            change_message="Annulation immédiate de la promotion." + (" Motif : " + motif.strip() if motif.strip() else ""),
        )
        return True
