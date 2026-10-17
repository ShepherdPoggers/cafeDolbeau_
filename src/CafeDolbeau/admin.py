from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.contrib.admin.utils import unquote
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html

from .forms.forms import CreationEmployeForm, ModificationEmployeForm, ParametresCafeForm
from .models import AnnulationTransaction, Client, Employe, FusionClient, ParametresCafe, TransactionCafe
from .admin_fusions import confirmer_fusion
from .permissions import PERMISSION_GERANT
from .services import COMPTEURS, _avec_client_verrouille, soldes_clients, supprimer_clients


admin.site.site_header = "Administration Café Dolbeau"
admin.site.site_title = "Administration Café Dolbeau"


admin.site.unregister(User)


@admin.register(Employe)
class EmployeAdmin(UserAdmin):
    add_form_template = "admin/CafeDolbeau/employe/add_form.html"
    add_form = CreationEmployeForm
    form = ModificationEmployeForm
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "role", "password1", "password2")}),
    )
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Rôle et accès", {"fields": ("role", "is_active")}),
        ("Informations personnelles", {"fields": ("first_name", "last_name", "email")}),
        ("Permissions avancées", {
            "classes": ("collapse",),
            "fields": ("is_staff", "is_superuser", "user_permissions"),
        }),
        ("Dates importantes", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ("last_login", "date_joined")
    list_display = ("username", "afficher_role", "first_name", "last_name", "email", "is_active")
    list_filter = ("is_active", "groups")
    filter_horizontal = ("user_permissions",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")

    @admin.display(description="Rôle")
    def afficher_role(self, employe):
        roles = {groupe.name for groupe in employe.groups.all()}
        if employe.is_superuser or "Gérant" in roles:
            return "Gérant"
        if "Barista" in roles:
            return "Barista"
        return "Non attribué"


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("nom_complet", "telephone", "courriel", "nombre_cafes_achetes", "nombre_cafes_prepayes", "nombre_cafes_gratuits", "est_actif")
    search_fields = ("nom_complet", "telephone", "courriel")
    list_filter = ("est_actif",)
    readonly_fields = ("est_actif",)
    actions = ("delete_selected", "fusionner_selection")

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(pk=Client.ID_SUPPRIME)

    def has_change_permission(self, request, obj=None):
        return (obj is None or (obj.pk != Client.ID_SUPPRIME and obj.est_actif)) and super().has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        champs = super().get_readonly_fields(request, obj)
        if obj and FusionClient.en_attente_pour(obj.pk).exists():
            return (*champs, *(compteur for compteur, _, _ in COMPTEURS))
        return champs

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)

        def enregistrer(actuel):
            compteurs_modifies = [champ for champ, _, _ in COMPTEURS if champ in form.changed_data]
            if not actuel.est_actif or (
                FusionClient.en_attente_pour(obj.pk).exists()
                and compteurs_modifies
            ):
                raise PermissionDenied("Ce client participe à une fusion réversible.")
            for champ, _, _ in COMPTEURS:
                if champ not in compteurs_modifies:
                    setattr(obj, champ, getattr(actuel, champ))
            obj.est_actif = actuel.est_actif
            obj.save(force_update=True)

        try:
            _avec_client_verrouille(Client.objects.filter(pk=obj.pk), enregistrer)
        except Client.DoesNotExist:
            raise PermissionDenied("Ce client a été supprimé.")

    def has_fusion_permission(self, request):
        return request.user.is_active and request.user.has_perm(PERMISSION_GERANT)

    @admin.action(description="Fusionner deux clients", permissions=["fusion"])
    def fusionner_selection(self, request, queryset):
        return confirmer_fusion(self, request, queryset)

    def has_delete_permission(self, request, obj=None):
        return (
            request.user.is_active and request.user.has_perm(PERMISSION_GERANT)
            and (obj is None or (obj.pk != Client.ID_SUPPRIME and obj.est_actif
                                and not FusionClient.en_attente_pour(obj.pk).exists()))
            and super().has_delete_permission(request, obj)
        )

    def delete_model(self, request, obj):
        supprimer_clients([obj.pk], employe=request.user)

    def delete_queryset(self, request, queryset):
        supprimer_clients(queryset.values_list("pk", flat=True), employe=request.user)

    def delete_view(self, request, object_id, extra_context=None):
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        if not self.has_delete_permission(request):
            raise PermissionDenied
        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            raise Http404
        if not self.has_delete_permission(request, obj):
            raise PermissionDenied
        return self._confirmer_suppression(
            request, self.get_queryset(request).filter(pk=obj.pk), en_lot=False,
        )

    @admin.action(description="Supprimer les clients sélectionnés", permissions=["delete"])
    def delete_selected(self, request, queryset):
        return self._confirmer_suppression(request, queryset, en_lot=True)

    def _confirmer_suppression(self, request, queryset, *, en_lot):
        if not self.has_delete_permission(request):
            raise PermissionDenied
        clients = list(queryset.order_by("pk"))
        erreurs = []
        statut = 200
        if request.method == "POST" and request.POST.get("post") == "yes":
            try:
                confirmation = signing.loads(
                    request.POST.get("confirmation", ""), salt="suppression-client", max_age=1800,
                )
                if confirmation["employe"] != request.user.pk or not isinstance(confirmation["soldes"], dict):
                    raise signing.BadSignature
                if set(confirmation["soldes"]) != {str(client.pk) for client in clients}:
                    raise ValidationError(
                        "La sélection a changé. Vérifiez la nouvelle confirmation.", code="soldes_modifies",
                    )
                nombre = supprimer_clients(
                    [client.pk for client in clients], employe=request.user,
                    soldes_attendus=confirmation["soldes"],
                )
            except (signing.BadSignature, KeyError, TypeError, ValueError):
                erreurs = ["La confirmation est invalide ou expirée. Vérifiez la nouvelle confirmation."]
                statut = 400
            except ValidationError as erreur:
                erreurs = erreur.messages
                statut = 409 if getattr(erreur, "code", None) == "soldes_modifies" else 400
            except OperationalError:
                erreurs = ["La suppression est momentanément indisponible. Veuillez réessayer."]
                statut = 503
            else:
                self.message_user(
                    request, f"{nombre} client(s) supprimé(s). Les transactions ont été conservées.",
                    messages.SUCCESS,
                )
                return redirect("admin:CafeDolbeau_client_changelist")
            clients = list(queryset.all().order_by("pk"))
        contexte = {
            **self.admin_site.each_context(request), "opts": self.opts,
            "title": "Confirmer la suppression des clients" if en_lot else "Confirmer la suppression du client",
            "clients": clients, "en_lot": en_lot, "erreurs": erreurs,
            "confirmation": signing.dumps({
                "employe": request.user.pk, "soldes": soldes_clients(clients),
            }, salt="suppression-client", compress=True),
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(request, "admin/CafeDolbeau/client/confirmer_suppression.html", contexte, status=statut)


@admin.register(ParametresCafe)
class ParametresCafeAdmin(admin.ModelAdmin):
    form = ParametresCafeForm
    fields = ("seuil_actuel", "cafes_pour_gratuite", "date_application")
    readonly_fields = ("seuil_actuel",)
    list_display = ("__str__", "seuil_actuel", "cafes_pour_gratuite", "date_application")
    actions = None

    @admin.display(description="Seuil actuellement en vigueur")
    def seuil_actuel(self, obj):
        return obj.seuil_gratuite_actif

    def save_model(self, request, obj, form, change):
        # Le formulaire est enregistré dans la transaction de l’administration.
        actuel = ParametresCafe.objects.select_for_update().get(pk=obj.pk)
        obj.cafes_pour_gratuite_precedent = actuel.seuil_gratuite_actif
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        ParametresCafe.charger()
        return super().get_queryset(request)

    def has_module_permission(self, request):
        return request.user.has_perm(PERMISSION_GERANT)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(PERMISSION_GERANT)

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm(PERMISSION_GERANT)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StatutAnnulationFilter(admin.SimpleListFilter):
    title = "statut"
    parameter_name = "annulee"

    def lookups(self, request, model_admin):
        return [("oui", "Annulées"), ("non", "Actives")]

    def queryset(self, request, queryset):
        if self.value() in ("oui", "non"):
            return queryset.filter(annulation__isnull=self.value() == "non")
        return queryset


class AnnulationInline(admin.StackedInline):
    model = AnnulationTransaction
    fields = ("date_annulation", "employe")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(PERMISSION_GERANT)


@admin.register(TransactionCafe)
class TransactionCafeAdmin(admin.ModelAdmin):
    change_form_template = "admin/CafeDolbeau/transactioncafe/change_form.html"
    list_display = ("id", "client", "type_transaction", "quantite", "employe", "date_creation", "est_annulee", "lien_annuler")
    list_filter = (StatutAnnulationFilter, "client", "employe", "type_transaction", "date_creation")
    search_fields = ("client__nom_complet", "client__telephone", "client__courriel", "employe__username")
    readonly_fields = ("client", "client_origine_id", "type_transaction", "quantite", "employe", "date_creation", "operation_id", "variation_achetes", "variation_prepayes", "variation_gratuits", "est_annulee", "lien_annuler")
    fields = readonly_fields
    actions = None
    inlines = (AnnulationInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("client", "employe", "annulation__employe")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(PERMISSION_GERANT)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(boolean=True, description="Annulée")
    def est_annulee(self, obj):
        return obj.annulee

    @admin.display(description="Annulation")
    def lien_annuler(self, obj):
        if obj.annulee:
            return "Déjà annulée"
        if FusionClient.en_attente_pour(obj.client_id).exists():
            return "Annulation indisponible pendant la fusion réversible"
        url = reverse("annuler_transaction_admin", args=[obj.pk])
        return format_html('<a href="{}">Annuler l’opération</a>', url)
