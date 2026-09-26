from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

class Client(models.Model):
    nom_complet = models.CharField("nom complet", max_length=200)
    telephone = models.CharField("numéro de téléphone", max_length=30, blank=True)
    courriel = models.EmailField("courriel", blank=True)
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
        if not self.courriel.strip() and not self.telephone.strip():
            raise ValidationError("Veuillez renseigner un courriel ou un téléphone.")

    def __str__(self):
        return self.nom_complet


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
    quantite = models.PositiveIntegerField("quantité", validators=[MinValueValidator(1)])
    date_creation = models.DateTimeField("date", auto_now_add=True)

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
