from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.html import format_html

from .forms import CreationEmployeForm, ModificationEmployeForm
from .models import AnnulationTransaction, Client, Employe, TransactionCafe
from .permissions import PERMISSION_GERANT


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
    list_display = ("nom_complet", "telephone", "courriel", "nombre_cafes_achetes", "nombre_cafes_prepayes", "nombre_cafes_gratuits")
    search_fields = ("nom_complet", "telephone", "courriel")


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
    readonly_fields = ("client", "type_transaction", "quantite", "employe", "date_creation", "operation_id", "variation_achetes", "variation_prepayes", "variation_gratuits", "est_annulee", "lien_annuler")
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
        url = reverse("annuler_transaction", args=[obj.client_id, obj.pk])
        return format_html('<a href="{}?origine=admin">Annuler l’opération</a>', url)
