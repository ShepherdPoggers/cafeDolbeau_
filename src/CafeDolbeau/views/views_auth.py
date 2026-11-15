from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse

from ..forms.forms import ConnexionForm
from ..models import Succursale
from ..permissions import SESSION_SUCCURSALE, succursales_autorisees


class ConnexionView(LoginView):
    template_name = "registration/login.html"
    authentication_form = ConnexionForm
    redirect_authenticated_user = True

    def get_success_url(self):
        succursale_id = self.request.session.get(SESSION_SUCCURSALE)
        if succursale_id is not None:
            # Au changement d’employé, reprendre la caisse sans rouvrir la fiche
            # client ou la confirmation que l’employé précédent consultait.
            return reverse("accueil_succursale", args=[succursale_id])
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        self.request.succursale = Succursale.objects.filter(
            pk=self.request.session.get(SESSION_SUCCURSALE),
        ).first()
        return super().get_context_data(**kwargs)


class DeconnexionView(LogoutView):
    def post(self, request, *args, **kwargs):
        succursale_id = request.session.get(SESSION_SUCCURSALE)
        try:
            contexte_page = int(request.POST.get("succursale_id", ""))
        except (TypeError, ValueError):
            contexte_page = None
        # Si plusieurs caisses sont ouvertes dans des onglets, conserver celle
        # du formulaire utilisé, après contrôle côté serveur.
        if contexte_page is not None and succursales_autorisees(request.user).filter(pk=contexte_page).exists():
            succursale_id = contexte_page
        reponse = super().post(request, *args, **kwargs)
        # logout() vide la session et ses informations privées. Ne rétablir
        # que le contexte de la caisse dans la nouvelle session anonyme.
        if succursale_id is not None:
            request.session[SESSION_SUCCURSALE] = succursale_id
        return reponse
