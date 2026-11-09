from functools import wraps

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404

from .models import Client, Employe, FusionClient, Succursale, TransactionCafe


PERMISSION_BASE = "CafeDolbeau.acces_base"
PERMISSION_GERANT = "CafeDolbeau.acces_gerant"
PERMISSION_PROPRIETAIRE = "CafeDolbeau.acces_proprietaire"


def acces_base_requis(view):
    """Autorise les baristas, les gérants et les superutilisateurs actifs."""
    return login_required(permission_required(PERMISSION_BASE, raise_exception=True)(view))


def gerant_requis(view):
    """Protège les futures fonctions réservées aux gérants, y compris en POST."""
    return login_required(permission_required(PERMISSION_GERANT, raise_exception=True)(view))


def proprietaire_requis(view):
    return login_required(permission_required(PERMISSION_PROPRIETAIRE, raise_exception=True)(view))


def est_proprietaire(employe):
    return employe.is_active and employe.has_perm(PERMISSION_PROPRIETAIRE)


def succursales_autorisees(employe):
    if not employe.is_active or not employe.has_perm(PERMISSION_BASE):
        return Succursale.objects.none()
    if est_proprietaire(employe):
        return Succursale.objects.all()
    return Succursale.objects.filter(affectations_employes__employe_id=employe.pk)


def verifier_acces_succursale(employe, succursale_id):
    if type(succursale_id) is not int or not Succursale.objects.filter(pk=succursale_id).exists():
        raise ValidationError({"succursale": "Cette succursale n’existe pas."})
    if not succursales_autorisees(employe).filter(pk=succursale_id).exists():
        raise PermissionDenied


def succursale_requise(view):
    @wraps(view)
    def controle(request, *args, succursale_id, **kwargs):
        request.succursale = get_object_or_404(Succursale, pk=succursale_id)
        verifier_acces_succursale(request.user, succursale_id)
        return view(request, *args, **kwargs)
    return acces_base_requis(controle)


def transactions_administrables(employe):
    if not employe.is_active or not employe.has_perm(PERMISSION_GERANT):
        return TransactionCafe.objects.none()
    return TransactionCafe.objects.filter(succursale__in=succursales_autorisees(employe))


def employes_administrables(employe):
    lignes = Employe.objects.all()
    if not employe.is_active or not employe.has_perm(PERMISSION_GERANT):
        return lignes.none()
    if employe.is_superuser:
        return lignes
    lignes = lignes.filter(is_superuser=False)
    if est_proprietaire(employe):
        return lignes
    return lignes.filter(groups__name="Barista").exclude(
        groups__permissions__codename__in=("acces_gerant", "acces_proprietaire"),
    ).exclude(user_permissions__codename__in=("acces_gerant", "acces_proprietaire")).distinct()


def peut_intervenir_transaction(ligne, employe, *, succursale_id=None, verifier_recence=True):
    """Droits sur la source, indépendamment de son état d'annulation."""
    if not employe.is_active or not employe.has_perm(PERMISSION_BASE):
        return False
    if est_proprietaire(employe):
        return True
    if employe.has_perm(PERMISSION_GERANT):
        return succursales_autorisees(employe).filter(pk=ligne.succursale_id).exists()
    return (
        ligne.client_id != Client.ID_SUPPRIME
        and ligne.employe_id == employe.pk
        and ligne.succursale_id == succursale_id
        and succursales_autorisees(employe).filter(pk=succursale_id).exists()
        and (not verifier_recence or ligne.pk in ligne.client.transactions_cafe.values_list("pk", flat=True)[:10])
    )


def peut_annuler(transaction, employe, *, succursale_id=None):
    return (
        not transaction.annulee
        and not FusionClient.en_attente_pour(transaction.client_id).exists()
        and peut_intervenir_transaction(transaction, employe, succursale_id=succursale_id)
    )
