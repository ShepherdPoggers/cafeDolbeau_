from django import forms
from django.contrib import admin, messages
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from .models import Client, FusionClient
from .permissions import PERMISSION_GERANT
from .services import COMPTEURS, annuler_fusion, fusionner_clients, soldes_clients, verifier_fusion_possible


class DestinationFusionForm(forms.Form):
    destination = forms.ModelChoiceField(
        label="Client à conserver", queryset=Client.objects.none(), empty_label="Choisir explicitement un client",
    )

    def __init__(self, *args, clients, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destination"].queryset = Client.objects.filter(pk__in=[client.pk for client in clients])


def confirmer_fusion(modeladmin, request, queryset):
    if not modeladmin.has_fusion_permission(request):
        raise PermissionDenied
    clients = list(queryset.order_by("pk"))
    if len(clients) != 2:
        modeladmin.message_user(request, "Sélectionnez exactement deux clients à fusionner.", messages.ERROR)
        return redirect("admin:CafeDolbeau_client_changelist")
    form = DestinationFusionForm(request.POST if request.POST.get("etape") else None, clients=clients)
    erreurs, statut = [], 200
    contexte = {
        **modeladmin.admin_site.each_context(request), "opts": modeladmin.opts,
        "title": "Fusionner deux clients", "clients": clients, "form": form,
    }
    if form.is_bound and form.is_valid():
        destination = form.cleaned_data["destination"]
        source = next(client for client in clients if client.pk != destination.pk)
        if request.POST.get("etape") == "confirmer":
            try:
                confirmation = signing.loads(request.POST.get("confirmation", ""), salt="fusion-clients", max_age=1800)
                if (confirmation["employe"] != request.user.pk or confirmation["source"] != source.pk
                        or confirmation["destination"] != destination.pk):
                    raise signing.BadSignature
                fusion = fusionner_clients(
                    source.pk, destination.pk, employe=request.user, soldes_attendus=confirmation["soldes"],
                )
            except (signing.BadSignature, KeyError, TypeError, ValueError):
                erreurs = ["La confirmation est invalide ou expirée. Vérifiez la nouvelle confirmation."]
                statut = 400
            except ValidationError as erreur:
                erreurs = erreur.messages
                statut = 409 if getattr(erreur, "code", None) == "soldes_modifies" else 400
            except OperationalError:
                erreurs = ["La fusion est momentanément indisponible. Veuillez réessayer."]
                statut = 503
            else:
                modeladmin.message_user(request, "Fusion effectuée. Elle reste réversible jusqu’à la prochaine opération.", messages.SUCCESS)
                return redirect("admin:CafeDolbeau_fusionclient_change", fusion.pk)
            clients = list(queryset.all().order_by("pk"))
            source = next((client for client in clients if client.pk == source.pk), None)
            destination = next((client for client in clients if client.pk == destination.pk), None)
        try:
            if source is None or destination is None:
                raise ValidationError("Un des clients n'existe plus.")
            totaux = verifier_fusion_possible(source, destination)
        except ValidationError as erreur:
            erreurs.extend(erreur.messages)
            statut = 400
        else:
            contexte.update(
                source=source, destination=destination,
                compteurs=[{
                    "libelle": libelle, "source": getattr(source, compteur),
                    "destination": getattr(destination, compteur), "total": totaux[compteur],
                } for compteur, _, libelle in COMPTEURS],
                confirmation=signing.dumps({
                    "employe": request.user.pk, "source": source.pk, "destination": destination.pk,
                    "soldes": soldes_clients(clients),
                }, salt="fusion-clients", compress=True),
            )
    contexte.update(erreurs=erreurs, clients=clients)
    request.current_app = modeladmin.admin_site.name
    return TemplateResponse(request, "admin/CafeDolbeau/client/confirmer_fusion.html", contexte, status=statut)


@admin.register(FusionClient)
class FusionClientAdmin(admin.ModelAdmin):
    list_display = ("source_nom", "destination_nom", "statut", "cree_le", "cree_par", "terminee_le", "lien_annuler")
    list_filter = ("statut", "cree_le")
    search_fields = ("source_nom", "destination_nom", "client_source_id", "client_destination_id")
    readonly_fields = (
        "client_source_id", "source_nom", "client_destination_id", "destination_nom", "statut",
        "compteurs_initiaux", "transactions_deplacees", "cree_le", "cree_par", "terminee_le",
        "terminee_par", "operation_finalisation_id", "lien_annuler",
    )
    fields = readonly_fields
    actions = None

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("cree_par", "terminee_par")

    def has_module_permission(self, request):
        return request.user.is_active and request.user.has_perm(PERMISSION_GERANT)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [path(
            "<int:fusion_id>/annuler/", self.admin_site.admin_view(self.annuler_view),
            name="CafeDolbeau_fusionclient_annuler",
        ), *super().get_urls()]

    @admin.display(description="Retour arrière")
    def lien_annuler(self, fusion):
        if fusion.statut != FusionClient.Statut.EN_ATTENTE:
            return "—"
        return format_html('<a href="{}">Annuler cette fusion</a>', reverse("admin:CafeDolbeau_fusionclient_annuler", args=[fusion.pk]))

    @admin.display(description="Compteurs initiaux")
    def compteurs_initiaux(self, fusion):
        lignes = format_html_join("", "<tr><th>{}</th><td>{}</td><td>{}</td></tr>", (
            (libelle, fusion.soldes_source[champ], fusion.soldes_destination[champ]) for champ, _, libelle in COMPTEURS
        ))
        return format_html("<table><thead><tr><th>Compteur</th><th>{}</th><th>{}</th></tr></thead><tbody>{}</tbody></table>", fusion.source_nom, fusion.destination_nom, lignes)

    def annuler_view(self, request, fusion_id):
        if not self.has_view_permission(request):
            raise PermissionDenied
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        fusion = get_object_or_404(FusionClient, pk=fusion_id)
        erreurs, statut = [], 200
        if request.method == "POST":
            try:
                confirmation = signing.loads(request.POST.get("confirmation", ""), salt="annulation-fusion", max_age=1800)
                if confirmation["fusion"] != fusion.pk or confirmation["employe"] != request.user.pk:
                    raise signing.BadSignature
                annuler_fusion(fusion.pk, employe=request.user)
            except (signing.BadSignature, KeyError, TypeError, ValueError):
                erreurs = ["La confirmation est invalide ou expirée."]
                statut = 400
            except ValidationError as erreur:
                erreurs, statut = erreur.messages, 409
            except OperationalError:
                erreurs, statut = ["Le retour arrière est momentanément indisponible. Veuillez réessayer."], 503
            else:
                self.message_user(request, "La fusion a été annulée. Les deux clients ont été restaurés.", messages.SUCCESS)
                return redirect("admin:CafeDolbeau_fusionclient_change", fusion.pk)
            fusion.refresh_from_db()
        contexte = {
            **self.admin_site.each_context(request), "opts": self.opts, "fusion": fusion,
            "title": "Confirmer le retour arrière de la fusion", "erreurs": erreurs,
            "compteurs": [{
                "libelle": libelle, "source": fusion.soldes_source[champ],
                "destination": fusion.soldes_destination[champ],
            } for champ, _, libelle in COMPTEURS],
        }
        if fusion.statut == FusionClient.Statut.EN_ATTENTE:
            contexte["confirmation"] = signing.dumps({"fusion": fusion.pk, "employe": request.user.pk}, salt="annulation-fusion")
        request.current_app = self.admin_site.name
        return TemplateResponse(request, "admin/CafeDolbeau/fusionclient/confirmer_annulation.html", contexte, status=statut)
