from django.contrib.auth.decorators import login_required, permission_required


PERMISSION_BASE = "CafeDolbeau.acces_base"
PERMISSION_GERANT = "CafeDolbeau.acces_gerant"


def acces_base_requis(view):
    """Autorise les baristas, les gérants et les superutilisateurs actifs."""
    return login_required(permission_required(PERMISSION_BASE, raise_exception=True)(view))


def gerant_requis(view):
    """Protège les futures fonctions réservées aux gérants, y compris en POST."""
    return login_required(permission_required(PERMISSION_GERANT, raise_exception=True)(view))


def peut_annuler(transaction, employe):
    return (
        employe.is_active
        and employe.has_perm(PERMISSION_BASE)
        and not transaction.annulee
        and (employe.has_perm(PERMISSION_GERANT) or transaction.employe_id == employe.pk)
    )
