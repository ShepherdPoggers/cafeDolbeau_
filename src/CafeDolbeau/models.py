from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone


class Employe(User):
    """Compte employé utilisant les comptes et les groupes d'authentification Django."""

    class Meta:
        proxy = True
        verbose_name = "employé"
        verbose_name_plural = "employés"
        default_permissions = ()
        permissions = [
            ("acces_base", "Accéder aux fonctions de base du café"),
            ("acces_gerant", "Accéder aux fonctions de gérant du café"),
        ]


class ParametresCafe(models.Model):
    """Gestion de la règle des cafés gratuits"""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    cafes_pour_gratuite = models.PositiveIntegerField(
        "nombre de cafés achetés pour un café gratuit", default=10,
        validators=[MinValueValidator(1), MaxValueValidator(2147483647)],
        help_text="Entier supérieur ou égal à 1. S’applique à la date choisie sans recalculer les soldes existants.",
    )
    date_application = models.DateField(
        "date d’entrée en vigueur", default=timezone.localdate,
        help_text="À partir de minuit, heure du Québec. Choisissez aujourd’hui pour une application immédiate.",
    )
    cafes_pour_gratuite_precedent = models.PositiveIntegerField(
        default=10, editable=False,
        validators=[MinValueValidator(1), MaxValueValidator(2147483647)],
    )

    class Meta:
        verbose_name = "paramètres du café"
        verbose_name_plural = "paramètres du café"
        constraints = [
            models.CheckConstraint(condition=models.Q(pk=1), name="parametres_cafe_uniques"),
            models.CheckConstraint(
                condition=models.Q(cafes_pour_gratuite__gte=1, cafes_pour_gratuite__lte=2147483647),
                name="seuil_gratuite_entier_positif",
            ),
            models.CheckConstraint(
                condition=models.Q(cafes_pour_gratuite_precedent__gte=1, cafes_pour_gratuite_precedent__lte=2147483647),
                name="seuil_gratuite_precedent_positif",
            ),
        ]

    @classmethod
    def charger(cls):
        """Retourne l’instance unique des paramètres du café, en la créant si nécessaire."""
        parametres, _ = cls.objects.get_or_create(pk=1)
        return parametres

    @property
    def seuil_gratuite_actif(self):
        """Retourne le bon seuil de cafés selon la date d’application choisie."""
        if timezone.localdate() < self.date_application:
            return self.cafes_pour_gratuite_precedent
        return self.cafes_pour_gratuite

    def __str__(self):
        return "Paramètres du café"


class Client(models.Model):
    ID_SUPPRIME = -1

    nom_complet = models.CharField("nom complet", max_length=200)
    telephone = models.CharField("numéro de téléphone", max_length=30, blank=True)
    courriel = models.EmailField("courriel", blank=True)
    est_actif = models.BooleanField("actif", default=True, editable=False)
    nombre_cafes_prepayes = models.PositiveIntegerField(
        "nombre de cafés prépayés", default=0
    )
    nombre_cafes_achetes = models.PositiveIntegerField(
        "nombre de cafés achetés", default=0
    )
    nombre_cafes_gratuits = models.PositiveIntegerField(
        "nombre de cafés gratuits", default=0
    )

    class Meta:
        verbose_name = "client"
        verbose_name_plural = "clients"
        ordering = ["nom_complet"]
        constraints = [
            models.UniqueConstraint(
                fields=["telephone"],
                condition=~models.Q(telephone=""),
                name="client_telephone_unique_non_vide",
                violation_error_message="Ce numéro de téléphone est déjà associé à un client.",
            ),
            models.UniqueConstraint(
                fields=["courriel"],
                condition=~models.Q(courriel=""),
                name="client_courriel_unique_non_vide",
                violation_error_message="Ce courriel est déjà associé à un client.",
            ),
        ]

    def clean(self):
        """Valide que le client a au moins un courriel ou un téléphone renseigné."""
        super().clean() # Redéfinition de la fonction parent qui est callé dans le form.is_valid()
        if self.pk != self.ID_SUPPRIME and not self.courriel.strip() and not self.telephone.strip():
            raise ValidationError("Veuillez renseigner un courriel ou un téléphone.")

    def __str__(self):
        return self.nom_complet


@receiver(pre_delete, sender=Client)
def proteger_client_supprime(sender, instance, **kwargs):
    if instance.pk == Client.ID_SUPPRIME:
        raise ValidationError("Le client fictif ne peut pas être supprimé.")
    if FusionClient.en_attente_pour(instance.pk).exists():
        raise ValidationError("Annulez ou finalisez la fusion avant de supprimer ce client.")


class TransactionCafe(models.Model):
    """Historique des ajouts de cafés achetés ou prépayés."""

    class Type(models.TextChoices):
        """Enum qui traite du type de transaction"""
        ACHAT = "achat", "Cafés achetés"
        PREPAYE = "prepaye", "Cafés prépayés"
        GRATUIT = "gratuit", "Cafés gratuits"
        UTILISE = "utilise", "Cafés prépayés consommés"

    type_transaction = models.CharField(
        "type de transaction", max_length=10, choices=Type.choices, default=Type.ACHAT
    )
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name="transactions_cafe"
    )
    client_origine_id = models.BigIntegerField(
        "identifiant du client d'origine", null=True, blank=True, editable=False,
        db_index=True,
    )
    quantite = models.PositiveIntegerField("quantité", validators=[MinValueValidator(1)])
    date_creation = models.DateTimeField("date", auto_now_add=True)
    employe = models.ForeignKey(
        Employe, on_delete=models.PROTECT, null=True, blank=True,
        related_name="transactions_effectuees", verbose_name="employé",
    )
    operation_id = models.UUIDField("opération", null=True, blank=True, db_index=True)
    variation_achetes = models.IntegerField(null=True, blank=True)
    variation_prepayes = models.IntegerField(null=True, blank=True)
    variation_gratuits = models.IntegerField(null=True, blank=True)

    @property
    def annulee(self):
        return hasattr(self, "annulation")

    class Meta:

        ordering = ["-date_creation", "-pk"]
        verbose_name = "transaction de cafés"
        verbose_name_plural = "transactions de cafés"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantite__gte=1), name="transaction_cafe_quantite_positive"
            )
        ]

    def __str__(self):
        return f"{self.client} : {self.quantite} café(s)"


class AnnulationTransaction(models.Model):
    transaction = models.OneToOneField(
        TransactionCafe, on_delete=models.PROTECT, related_name="annulation",
    )
    date_annulation = models.DateTimeField(default=timezone.now, editable=False)
    employe = models.ForeignKey(
        Employe, on_delete=models.PROTECT, related_name="annulations_effectuees",
        verbose_name="employé",
    )

    class Meta:
        verbose_name = "annulation de transaction"
        verbose_name_plural = "annulations de transactions"
        ordering = ["-date_annulation", "-pk"]

    def __str__(self):
        return f"Annulation de la transaction #{self.transaction_id}"


class FusionClient(models.Model):
    """Historique et instantanés indépendants de la survie des deux clients."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "Réversible"
        ANNULEE = "annulee", "Annulée"
        FINALISEE = "finalisee", "Définitive"

    client_source_id = models.PositiveBigIntegerField("ID du client fusionné", editable=False)
    client_destination_id = models.PositiveBigIntegerField("ID du client conservé", editable=False)
    source_nom = models.CharField("client fusionné", max_length=200, editable=False)
    destination_nom = models.CharField("client conservé", max_length=200, editable=False)
    soldes_source = models.JSONField(default=dict, editable=False)
    soldes_destination = models.JSONField(default=dict, editable=False)
    transactions_deplacees = models.JSONField(default=list, editable=False)
    statut = models.CharField("statut", max_length=10, choices=Statut.choices, default=Statut.EN_ATTENTE, editable=False)
    cree_le = models.DateTimeField("créée le", default=timezone.now, editable=False)
    cree_par = models.ForeignKey(Employe, on_delete=models.PROTECT, related_name="fusions_creees", verbose_name="créée par", editable=False)
    terminee_le = models.DateTimeField("terminée le", null=True, blank=True, editable=False)
    terminee_par = models.ForeignKey(Employe, on_delete=models.PROTECT, related_name="fusions_terminees", verbose_name="terminée par", null=True, blank=True, editable=False)
    operation_finalisation_id = models.UUIDField("opération de finalisation", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "fusion de clients"
        verbose_name_plural = "fusions de clients"
        ordering = ["-cree_le", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(client_source_id__gt=0, client_destination_id__gt=0) & ~models.Q(client_source_id=models.F("client_destination_id")),
                name="fusion_clients_distincts_positifs",
            ),
            models.CheckConstraint(condition=models.Q(statut__in=["en_attente", "annulee", "finalisee"]), name="fusion_statut_valide"),
            models.UniqueConstraint(fields=["client_source_id"], condition=models.Q(statut="en_attente"), name="fusion_source_en_attente_unique"),
            models.UniqueConstraint(fields=["client_destination_id"], condition=models.Q(statut="en_attente"), name="fusion_destination_en_attente_unique"),
        ]

    @classmethod
    def en_attente_pour(cls, *identifiants):
        return cls.objects.filter(statut=cls.Statut.EN_ATTENTE).filter(
            models.Q(client_source_id__in=identifiants) | models.Q(client_destination_id__in=identifiants),
        )

    def __str__(self):
        return f"{self.source_nom} → {self.destination_nom}"


@receiver(pre_delete, sender=FusionClient)
def proteger_historique_fusion(sender, instance, **kwargs):
    raise ValidationError("L'historique des fusions ne peut pas être supprimé.")
