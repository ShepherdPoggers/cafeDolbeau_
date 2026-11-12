from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.decorators.http import require_http_methods

from ..models import CompteurPromotion, Employe, Promotion, PromotionSuccursale, Succursale, verifier_periodes_promotion
from ..permissions import est_proprietaire
from ..promotions import annuler_promotion


def verifier_affectations(promotion, identifiants):
    verifier_periodes_promotion(promotion, identifiants)
    if promotion.pk and (promotion.annulee_le or promotion.transactions.exists()):
        actuelles = set(promotion.succursales.values_list("pk", flat=True))
        if set(identifiants) != actuelles:
            raise ValidationError("Les succursales d’une promotion utilisée sont figées.")


class PromotionForm(forms.ModelForm):
    succursales = forms.ModelMultipleChoiceField(queryset=Succursale.objects.all(), widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Promotion
        fields = ("nom", "cafes_pour_gratuite", "date_debut", "date_fin", "succursales")
        widgets = {champ: forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}) for champ in ("date_debut", "date_fin")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["succursales"] = self.instance.succursales.all()

    def clean(self):
        donnees = super().clean()
        if all(donnees.get(champ) is not None for champ in ("date_debut", "date_fin", "succursales")):
            with transaction.atomic():
                list(Succursale.objects.order_by("pk").select_for_update())
                promotion = Promotion(pk=self.instance.pk, annulee_le=self.instance.annulee_le, nom=donnees.get("nom", ""),
                                      cafes_pour_gratuite=donnees.get("cafes_pour_gratuite"),
                                      date_debut=donnees["date_debut"], date_fin=donnees["date_fin"])
                verifier_affectations(promotion, donnees["succursales"].values_list("pk", flat=True))
        return donnees

    def _save_m2m(self):
        with transaction.atomic():
            list(Succursale.objects.order_by("pk").select_for_update())
            promotion = Promotion.objects.select_for_update().get(pk=self.instance.pk)
            choisies = set(self.cleaned_data["succursales"].values_list("pk", flat=True))
            verifier_affectations(promotion, choisies)
            promotion.affectations.exclude(succursale_id__in=choisies).delete()
            actuelles = set(promotion.succursales.values_list("pk", flat=True))
            for identifiant in sorted(choisies - actuelles):
                PromotionSuccursale.objects.create(promotion=promotion, succursale_id=identifiant)


class AnnulationPromotionForm(forms.Form):
    motif = forms.CharField(label="Motif (facultatif)", max_length=500, required=False, widget=forms.Textarea)


class AdministrationProprietaire(admin.ModelAdmin):
    def has_module_permission(self, request):
        return est_proprietaire(request.user)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Promotion)
class PromotionAdmin(AdministrationProprietaire):
    form = PromotionForm
    change_form_template = "admin/CafeDolbeau/promotion/change_form.html"
    readonly_fields = ("annulee_le", "annulee_par", "motif_annulation")
    list_display = ("id", "nom", "cafes_pour_gratuite", "date_debut", "date_fin", "annulee_le", "lien_annuler")
    list_filter = ("annulee_le", "succursales", "date_debut", "date_fin")
    search_fields = ("nom",)
    actions = None

    def get_urls(self):
        return [path("<int:object_id>/annuler/", self.admin_site.admin_view(self.annuler_view),
                     name="CafeDolbeau_promotion_annuler"), *super().get_urls()]

    @admin.display(description="Annulation")
    def lien_annuler(self, obj):
        if obj.annulee_le:
            return "Annulée"
        if obj.date_debut <= timezone.localdate() <= obj.date_fin:
            return format_html('<a href="{}">Annuler la promotion</a>',
                               reverse("admin:CafeDolbeau_promotion_annuler", args=[obj.pk]))
        return "—"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        objet = self.get_object(request, object_id)
        contexte = {**(extra_context or {}), "annulation_promotion": None}
        if objet and not objet.annulee_le and objet.date_debut <= timezone.localdate() <= objet.date_fin:
            contexte["annulation_promotion"] = reverse("admin:CafeDolbeau_promotion_annuler", args=[objet.pk])
        return super().change_view(request, object_id, form_url, contexte)

    @method_decorator(require_http_methods(["GET", "POST"]))
    def annuler_view(self, request, object_id):
        if not est_proprietaire(request.user):
            raise PermissionDenied
        promotion = get_object_or_404(Promotion, pk=object_id)
        formulaire = AnnulationPromotionForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and formulaire.is_valid():
            try:
                modifiee = annuler_promotion(promotion.pk, employe=request.user, motif=formulaire.cleaned_data["motif"])
            except ValidationError as erreur:
                formulaire.add_error(None, erreur)
            else:
                self.message_user(request, "La promotion est annulée." if modifiee else "Cette promotion est déjà annulée.", messages.SUCCESS)
                return redirect("admin:CafeDolbeau_promotion_change", promotion.pk)
        contexte = {
            **self.admin_site.each_context(request), "opts": self.opts,
            "title": "Annuler la promotion", "promotion": promotion, "form": formulaire,
            "annulation_possible": not promotion.annulee_le and promotion.date_debut <= timezone.localdate() <= promotion.date_fin,
        }
        return TemplateResponse(request, "admin/CafeDolbeau/promotion/confirmer_annulation.html", contexte)

    def save_model(self, request, obj, form, change):
        acteur = Employe.objects.get(pk=request.user.pk)
        if not est_proprietaire(acteur):
            raise PermissionDenied
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request) and (obj is None or (not obj.annulee_le and not obj.transactions.exists()))


@admin.register(CompteurPromotion)
class CompteurPromotionAdmin(AdministrationProprietaire):
    list_display = ("client", "promotion", "progression", "cafes_gratuits")
    list_filter = ("promotion",)
    search_fields = ("client__nom_complet",)
    readonly_fields = ("client", "promotion", "progression", "cafes_gratuits")
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
