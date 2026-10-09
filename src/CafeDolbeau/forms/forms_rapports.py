from datetime import date

from django import forms

from ..rapports import PRECISIONS, TYPES_RAPPORT, dernier_jour_mois


class RapportForm(forms.Form):
    precision = forms.ChoiceField(label="Niveau de détail", choices=PRECISIONS)
    date_debut = forms.DateField(label="Date de début", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    date_fin = forms.DateField(label="Date de fin", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    types = forms.MultipleChoiceField(label="Types de transactions", choices=TYPES_RAPPORT, widget=forms.CheckboxSelectMultiple)

    def clean(self):
        donnees = super().clean()
        debut, fin = donnees.get("date_debut"), donnees.get("date_fin")
        precision = donnees.get("precision")
        if debut is None or fin is None:
            return donnees
        if fin == date.max:
            self.add_error("date_fin", "Cette date de fin est trop éloignée.")
        if debut > fin:
            self.add_error("date_fin", "La date de fin doit être égale ou postérieure à la date de début.")
        if precision == "semaine":
            if debut.weekday() != 0:
                self.add_error("date_debut", "Une période hebdomadaire doit commencer un lundi.")
            if fin.weekday() != 6:
                self.add_error("date_fin", "Une période hebdomadaire doit se terminer un dimanche.")
        elif precision == "mois":
            if debut.day != 1:
                self.add_error("date_debut", "Une période mensuelle doit commencer le premier jour du mois.")
            if fin != dernier_jour_mois(fin):
                self.add_error("date_fin", "Une période mensuelle doit se terminer le dernier jour du mois.")
        return donnees
