from django.contrib.admin import AdminSite
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from ..permissions import PERMISSION_GERANT


class AdministrationCafe(AdminSite):
    def has_permission(self, request):
        # Le rôle de gérant suffit ; le statut « équipe » ne donne aucun accès.
        return request.user.is_active and request.user.has_perm(PERMISSION_GERANT)

    @login_not_required
    def login(self, request, extra_context=None):
        """Utilise la même connexion pour l'application et l'administration."""
        if request.user.is_authenticated:
            if not self.has_permission(request):
                raise PermissionDenied
            return redirect("admin:index")
        return redirect_to_login(
            request.GET.get("next") or reverse("admin:index"),
            login_url=reverse("connexion"),
        )
