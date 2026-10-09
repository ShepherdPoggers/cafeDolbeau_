from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from ..models import TransactionCafe
from ..services import valider_effets


class ChoixTransactionField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, ligne):
        date = timezone.localtime(ligne.date_creation).strftime("%d/%m/%Y %H:%M")
        return f"#{ligne.pk} — {date} — {ligne.get_type_transaction_display()} : {ligne.quantite}"


class SelectionAnciennesForm(forms.Form):
    lignes = ChoixTransactionField(
        label="Lignes de l’ancienne opération", queryset=TransactionCafe.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, client, source, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = source
        self.fields["lignes"].queryset = TransactionCafe.objects.filter(
            client=client, operation_id__isnull=True, annulation__isnull=True,
        )
        if not self.is_bound:
            self.initial["lignes"] = [source.pk]

    def clean_lignes(self):
        lignes = self.cleaned_data["lignes"]
        if self.source.pk not in {ligne.pk for ligne in lignes}:
            raise ValidationError("Incluez la transaction depuis laquelle vous avez demandé l’annulation.")
        return lignes


class EffetsAncienneForm(forms.Form):
    transaction_id = forms.IntegerField(widget=forms.HiddenInput, min_value=1)
    variation_achetes = forms.IntegerField(label="Variation des cafés achetés", min_value=-2147483647, max_value=2147483647)
    variation_prepayes = forms.IntegerField(label="Variation des cafés prépayés", min_value=-2147483647, max_value=2147483647)
    variation_gratuits = forms.IntegerField(label="Variation des cafés gratuits", min_value=-2147483647, max_value=2147483647)


class BaseEffetsAnciennesFormSet(forms.BaseFormSet):
    def __init__(self, *args, lignes, **kwargs):
        self.lignes = {ligne.pk: ligne for ligne in lignes}
        super().__init__(*args, **kwargs)
        for form in self.forms:
            form.empty_permitted = False
            identifiant = form["transaction_id"].value()
            try:
                form.ligne = self.lignes.get(int(identifiant))
            except (ValueError, TypeError):
                form.ligne = None

    def clean(self):
        if any(self.errors):
            return
        identifiants = [form.cleaned_data["transaction_id"] for form in self.forms]
        if len(set(identifiants)) != len(identifiants) or set(identifiants) != set(self.lignes):
            raise ValidationError("Renseignez exactement les effets de chacune des lignes sélectionnées.")
        for form in self.forms:
            valeurs = tuple(form.cleaned_data[champ] for champ in (
                "variation_achetes", "variation_prepayes", "variation_gratuits",
            ))
            try:
                valider_effets(self.lignes[form.cleaned_data["transaction_id"]], valeurs)
            except ValidationError as erreur:
                form.add_error(None, erreur)

    def details(self):
        return {
            form.cleaned_data["transaction_id"]: tuple(form.cleaned_data[champ] for champ in (
                "variation_achetes", "variation_prepayes", "variation_gratuits",
            ))
            for form in self.forms
        }


EffetsAnciennesFormSet = forms.formset_factory(
    EffetsAncienneForm, formset=BaseEffetsAnciennesFormSet, extra=0,
    max_num=2000, absolute_max=2000, validate_max=True,
)
