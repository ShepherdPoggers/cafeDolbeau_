from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

from ..models import AffectationEmployeSuccursale, Client, Employe, ParametresCafe, Succursale
from ..permissions import PERMISSION_BASE, PERMISSION_GERANT, employes_administrables, est_proprietaire, succursales_autorisees


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
        queryset=Group.objects.filter(name__in=("Barista", "Gérant", "Propriétaire")),
        empty_label="Choisir un rôle",
    )
    succursales = forms.ModelMultipleChoiceField(
        label="Succursales", queryset=Succursale.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, acteur=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acteur = acteur
        self.creation = not self.instance.pk
        self.perimetre = succursales_autorisees(acteur) if acteur else Succursale.objects.none()
        self.fields["succursales"].queryset = self.perimetre
        if "role" in self.fields and (acteur is None or not est_proprietaire(acteur)):
            self.fields["role"].queryset = Group.objects.filter(name="Barista")
        if self.instance.pk:
            self.initial["succursales"] = self.perimetre.filter(
                affectations_employes__employe_id=self.instance.pk,
            )
            roles = {groupe.name: groupe.pk for groupe in self.instance.groups.all()}
            for nom in ("Propriétaire", "Gérant", "Barista"):
                if nom in roles:
                    self.initial["role"] = roles[nom]
                    break
            if self.instance.is_superuser and "role" not in self.initial:
                self.initial["role"] = Group.objects.get(name="Gérant").pk

    def clean(self):
        donnees = super().clean()
        if not self.instance.pk and self.acteur and not est_proprietaire(self.acteur) and not donnees.get("succursales"):
            self.add_error("succursales", "Choisissez au moins une de vos succursales.")
        return donnees

    def _save_m2m(self):
        acteur = Employe.objects.get(pk=self.acteur.pk)
        if not acteur.is_active or not acteur.has_perm(PERMISSION_GERANT):
            raise PermissionDenied
        if not self.creation and not employes_administrables(acteur).filter(pk=self.instance.pk).exists():
            raise PermissionDenied
        role = self.cleaned_data.get("role")
        if not est_proprietaire(acteur) and role is not None and role.name != "Barista":
            raise PermissionDenied
        perimetre = succursales_autorisees(acteur)
        choisies = self.cleaned_data["succursales"]
        if choisies.exclude(pk__in=perimetre).exists():
            raise PermissionDenied
        super()._save_m2m()
        if role is not None:
            anciens_roles = self.instance.groups.filter(
                name__in=("Barista", "Gérant", "Propriétaire"),
            ).exclude(pk=role.pk)
            self.instance.groups.remove(*anciens_roles)
            self.instance.groups.add(role)
        # Ne remplacer que les affectations que l'acteur est autorisé à gérer.
        AffectationEmployeSuccursale.objects.filter(
            employe_id=self.instance.pk, succursale__in=perimetre,
        ).exclude(succursale__in=choisies).delete()
        for succursale in choisies:
            AffectationEmployeSuccursale.objects.get_or_create(employe_id=self.instance.pk, succursale=succursale)


class CreationEmployeForm(RoleEmployeForm, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Employe
        fields = ("username",)


class ModificationEmployeForm(RoleEmployeForm, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Employe


class ParametresCafeForm(forms.ModelForm):
    class Meta:
        model = ParametresCafe
        fields = ("cafes_pour_gratuite", "date_application")
        widgets = {
            "date_application": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }


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
