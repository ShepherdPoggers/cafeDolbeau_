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

    class Meta:
        verbose_name = "client"
        verbose_name_plural = "clients"
        ordering = ["nom_complet"]

    def clean(self):
        """Valide que le client a au moins un courriel ou un téléphone renseigné."""
        super().clean() # Redéfinition de la fonction parent qui est callé dans le form.is_valid()
        if not self.courriel.strip() and not self.telephone.strip():
            raise ValidationError("Veuillez renseigner un courriel ou un téléphone.")

    def __str__(self):
        return self.nom_complet


    """Permet d'enregistrer l'achat de cafés par un client et de mettre"""
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name="transactions_cafe"
    )
    quantite = models.PositiveIntegerField("quantité", validators=[MinValueValidator(1)])
    date_creation = models.DateTimeField("date", auto_now_add=True)

    class Meta:class TransactionCafe(models.Model):

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
