from django import forms

from .models import Client


class AjoutCafesForm(forms.Form):
    quantite = forms.IntegerField(label="Nombre de cafés à ajouter", min_value=1,
                                 max_value=2147483647, initial=1)




class AchatCartesForm(forms.Form):
    quantite = forms.IntegerField(
        label="Nombre de cartes de 11 cafés", min_value=1,
        max_value=2147483647 // 11, initial=1,
    )


class ClientForm(forms.ModelForm):
    """Formulaire pour ajouter ou modifier un client."""
    class Meta:
        """Spécifie le modèle et les champs du formulaire."""
        model = Client
        fields = ["nom_complet", "courriel", "telephone"]
        labels = {
            "nom_complet": "Nom complet",
            "courriel": "Courriel",
            "telephone": "Téléphone",
        }
        widgets = { 
            # Précise les boites de saisie pour chaque champ du formulaire.
            "nom_complet": forms.TextInput(attrs={"autocomplete": "name"}),
            "courriel": forms.EmailInput(attrs={"autocomplete": "email"}),
            "telephone": forms.TextInput(
                attrs={"type": "tel", "autocomplete": "tel"}
            ),
        }
