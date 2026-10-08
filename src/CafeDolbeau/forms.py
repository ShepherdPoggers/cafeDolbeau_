from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm
from django.contrib.auth.models import Group

from .models import Client, Employe
from .permissions import PERMISSION_BASE


class ConnexionForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.has_perm(PERMISSION_BASE):
            raise forms.ValidationError(
                "Aucun rôle n’est attribué à votre compte. Contactez l’administrateur.",
                code="role_manquant",
            )


class RoleEmployeForm(forms.ModelForm):
    role = forms.ModelChoiceField(
        label="Rôle",
        queryset=Group.objects.filter(name__in=("Barista", "Gérant")),
        empty_label="Choisir un rôle",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            roles = {groupe.name: groupe.pk for groupe in self.instance.groups.all()}
            if self.instance.is_superuser or "Gérant" in roles:
                self.initial["role"] = self.fields["role"].queryset.get(name="Gérant").pk
            elif "Barista" in roles:
                self.initial["role"] = roles["Barista"]

    def _save_m2m(self):
        super()._save_m2m()
        role = self.cleaned_data["role"]
        anciens_roles = self.instance.groups.filter(
            name__in=("Barista", "Gérant"),
        ).exclude(pk=role.pk)
        self.instance.groups.remove(*anciens_roles)
        self.instance.groups.add(role)


class CreationEmployeForm(RoleEmployeForm, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Employe
        fields = ("username",)


class ModificationEmployeForm(RoleEmployeForm, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Employe


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
