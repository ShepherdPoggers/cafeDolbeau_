from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models.signals import m2m_changed, pre_delete
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
            ("acces_proprietaire", "Accéder à toutes les succursales et gérer les employés"),
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

    def calculer_cafes_gratuits(self, total_achetes, nouveaux_achats):
        seuil = self.seuil_gratuite_actif
        return (
            (total_achetes + nouveaux_achats) // seuil
            - total_achetes // seuil
        )

    def __str__(self):
        return "Paramètres du café"


class Succursale(models.Model):
    nom = models.CharField("nom", max_length=200)

    class Meta:
        verbose_name = "succursale"
        verbose_name_plural = "succursales"
        ordering = ["pk"]

    def __str__(self):
        return self.nom


class Promotion(models.Model):
    nom = models.CharField(max_length=200)
    cafes_pour_gratuite = models.PositiveIntegerField(
        "cafés achetés pour un gratuit", validators=[MinValueValidator(1), MaxValueValidator(2147483647)],
    )
    date_debut = models.DateField("date de début")
    date_fin = models.DateField("date de fin incluse")
    succursales = models.ManyToManyField(Succursale, through="PromotionSuccursale", related_name="promotions")
    annulee_le = models.DateTimeField("annulée le", null=True, blank=True, editable=False)
    annulee_par = models.ForeignKey(
        Employe, on_delete=models.PROTECT, null=True, blank=True, editable=False,
        related_name="promotions_annulees", verbose_name="annulée par",
    )
    motif_annulation = models.CharField("motif de l’annulation", max_length=500, blank=True, editable=False)

    class Meta:
        ordering = ["-date_debut", "-pk"]
        constraints = [
            models.CheckConstraint(condition=(
                models.Q(annulee_le__isnull=True, annulee_par__isnull=True)
                | models.Q(annulee_le__isnull=False, annulee_par__isnull=False)
            ), name="promotion_annulation_complete"),
            models.CheckConstraint(condition=models.Q(date_fin__gte=models.F("date_debut")), name="promotion_dates_valides"),
            models.CheckConstraint(condition=models.Q(cafes_pour_gratuite__gte=1, cafes_pour_gratuite__lte=2147483647), name="promotion_seuil_positif"),
        ]

    def __str__(self):
        return f"Promotion #{self.pk} — {self.nom}"

    def clean(self):
        super().clean()
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError("La fin doit être postérieure ou égale au début.")
        ancien = Promotion.objects.filter(pk=self.pk).first() if self.pk else None
        if ancien and (self.annulee_le, self.annulee_par_id, self.motif_annulation) != (
            ancien.annulee_le, ancien.annulee_par_id, ancien.motif_annulation,
        ):
            raise ValidationError("L’annulation a changé. Rechargez la promotion ; utilisez l’action d’annulation dédiée.")
        if ancien and ancien.annulee_le and (
            self.date_debut != ancien.date_debut or self.date_fin != ancien.date_fin
            or self.cafes_pour_gratuite != ancien.cafes_pour_gratuite
        ):
            raise ValidationError("Une promotion annulée ne peut pas être reprogrammée ou prolongée.")
        if ancien and self.date_debut and self.date_fin:
            if ancien.transactions.exists() and (
                self.cafes_pour_gratuite != ancien.cafes_pour_gratuite
                or self.date_debut != ancien.date_debut or self.date_fin < ancien.date_fin
            ):
                raise ValidationError("Une promotion utilisée conserve son seuil et son début ; seule une prolongation est permise.")
            if self.date_fin > ancien.date_fin and ancien.date_fin < timezone.localdate():
                raise ValidationError("Une promotion expirée ne peut plus être prolongée.")
            if self.date_debut and self.date_fin:
                verifier_periodes_promotion(self, self.succursales.values_list("pk", flat=True))

    def save(self, *args, **kwargs):
        with transaction.atomic():
            # Ordre commun aux affectations et à la caisse : succursales, puis promotion.
            list(Succursale.objects.order_by("pk").select_for_update())
            if self.pk:
                list(Promotion.objects.filter(pk=self.pk).select_for_update())
            self.full_clean()
            return super().save(*args, **kwargs)


def verifier_periodes_promotion(promotion, succursales):
    if promotion.annulee_le:
        return
    if PromotionSuccursale.objects.filter(
        promotion__annulee_le__isnull=True, succursale_id__in=succursales,
        promotion__date_debut__lte=promotion.date_fin,
        promotion__date_fin__gte=promotion.date_debut,
    ).exclude(promotion_id=promotion.pk).exists():
        raise ValidationError("Une autre promotion est déjà prévue à ces dates dans une succursale choisie.")


class PromotionSuccursale(models.Model):
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name="affectations")
    succursale = models.ForeignKey(Succursale, on_delete=models.PROTECT, related_name="promotions_planifiees")

    class Meta:
        verbose_name = "affectation de promotion"
        verbose_name_plural = "affectations des promotions"
        constraints = [models.UniqueConstraint(fields=["promotion", "succursale"], name="promotion_succursale_unique")]

    def clean(self):
        super().clean()
        if self.promotion_id and self.succursale_id:
            ancienne = type(self).objects.filter(pk=self.pk).first() if self.pk else None
            if ancienne and (ancienne.promotion_id != self.promotion_id or ancienne.succursale_id != self.succursale_id):
                raise ValidationError("Retirez l’affectation puis créez-en une nouvelle.")
            if not ancienne and (self.promotion.annulee_le or self.promotion.transactions.exists()):
                raise ValidationError("Les succursales d’une promotion utilisée sont figées.")
            verifier_periodes_promotion(self.promotion, [self.succursale_id])

    def save(self, *args, **kwargs):
        with transaction.atomic():
            list(Succursale.objects.filter(pk=self.succursale_id).select_for_update())
            self.promotion = Promotion.objects.select_for_update().get(pk=self.promotion_id)
            self.full_clean()
            return super().save(*args, **kwargs)


@receiver(pre_delete, sender=PromotionSuccursale)
def proteger_affectation_promotion(sender, instance, **kwargs):
    with transaction.atomic():
        list(Succursale.objects.filter(pk=instance.succursale_id).select_for_update())
        promotion = Promotion.objects.select_for_update().get(pk=instance.promotion_id)
        if promotion.annulee_le or promotion.transactions.exists():
            raise ValidationError("Les succursales d’une promotion utilisée sont figées.")


class AffectationEmployeSuccursale(models.Model):
    employe = models.ForeignKey(
        Employe, on_delete=models.CASCADE, related_name="affectations_succursales",
        verbose_name="employé",
    )
    succursale = models.ForeignKey(
        Succursale, on_delete=models.CASCADE, related_name="affectations_employes",
    )

    class Meta:
        verbose_name = "affectation à une succursale"
        verbose_name_plural = "affectations aux succursales"
        constraints = [models.UniqueConstraint(
            fields=["employe", "succursale"], name="affectation_employe_succursale_unique",
        )]

    def __str__(self):
        return f"{self.employe} — {self.succursale}"


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
    nombre_cafes_fidelite = models.PositiveIntegerField(
        "achats admissibles à la fidélité habituelle", default=0, editable=False,
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

    def save(self, *args, **kwargs):
        if self._state.adding and not self.nombre_cafes_fidelite:
            self.nombre_cafes_fidelite = self.nombre_cafes_achetes
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nom_complet


class CompteurPromotion(models.Model):
    promotion = models.ForeignKey(Promotion, on_delete=models.PROTECT, related_name="compteurs")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="compteurs_promotion")
    progression = models.PositiveIntegerField(default=0)
    cafes_gratuits = models.PositiveIntegerField("cafés promotionnels disponibles", default=0)

    class Meta:
        verbose_name = "compteur promotionnel"
        verbose_name_plural = "compteurs promotionnels"
        constraints = [models.UniqueConstraint(fields=["promotion", "client"], name="compteur_promotion_client_unique")]


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
    succursale = models.ForeignKey(
        Succursale, on_delete=models.PROTECT, default=1,
        related_name="transactions_cafe", verbose_name="succursale",
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
    promotion = models.ForeignKey(
        Promotion, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions",
    )
    variation_fidelite = models.IntegerField(null=True, blank=True)
    variation_progression_promotion = models.IntegerField(default=0)
    variation_gratuits_promotion = models.IntegerField(default=0)
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
    """Historique des fusions, avec les noms lus depuis les clients existants."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "Réversible"
        ANNULEE = "annulee", "Annulée"
        FINALISEE = "finalisee", "Définitive"

    client_source = models.ForeignKey(
        Client, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fusions_comme_source", verbose_name="client fusionné", editable=False,
    )
    client_destination = models.ForeignKey(
        Client, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fusions_comme_destination", verbose_name="client conservé", editable=False,
    )
    soldes_source = models.JSONField(default=dict, editable=False)
    soldes_destination = models.JSONField(default=dict, editable=False)
    promotions_source = models.JSONField(default=dict, editable=False)
    promotions_destination = models.JSONField(default=dict, editable=False)
    promotions_fusionnees = models.JSONField(default=dict, editable=False)
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
                condition=(
                    (models.Q(client_source__isnull=True) | models.Q(client_source__gt=0))
                    & (models.Q(client_destination__isnull=True) | models.Q(client_destination__gt=0))
                    & (models.Q(client_source__isnull=True) | models.Q(client_destination__isnull=True)
                       | ~models.Q(client_source=models.F("client_destination")))
                ),
                name="fusion_clients_distincts_positifs",
            ),
            models.CheckConstraint(condition=models.Q(statut__in=["en_attente", "annulee", "finalisee"]), name="fusion_statut_valide"),
            models.UniqueConstraint(fields=["client_source"], condition=models.Q(statut="en_attente"), name="fusion_source_en_attente_unique"),
            models.UniqueConstraint(fields=["client_destination"], condition=models.Q(statut="en_attente"), name="fusion_destination_en_attente_unique"),
        ]

    @classmethod
    def en_attente_pour(cls, *identifiants):
        return cls.objects.filter(statut=cls.Statut.EN_ATTENTE).filter(
            models.Q(client_source_id__in=identifiants) | models.Q(client_destination_id__in=identifiants),
        )

    def __str__(self):
        source = self.client_source or "Client supprimé"
        destination = self.client_destination or "Client supprimé"
        return f"{source} → {destination}"


@receiver(pre_delete, sender=FusionClient)
def proteger_historique_fusion(sender, instance, **kwargs):
    raise ValidationError("L'historique des fusions ne peut pas être supprimé.")


@receiver(pre_delete, sender=Promotion)
def proteger_promotion_utilisee(sender, instance, **kwargs):
    with transaction.atomic():
        list(Succursale.objects.order_by("pk").select_for_update())
        list(Promotion.objects.filter(pk=instance.pk).select_for_update())
        if instance.annulee_le or instance.transactions.exists():
            raise ValidationError("Une promotion utilisée ou annulée ne peut pas être supprimée.")


@receiver(m2m_changed, sender=Promotion.succursales.through)
def valider_liens_promotions(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in ("pre_add", "pre_remove", "pre_clear"):
        return
    # Les opérations M2M Django utilisent bulk_create et ne passent pas par save().
    list(Succursale.objects.order_by("pk").select_for_update())
    if reverse:
        promotions = Promotion.objects.filter(pk__in=pk_set) if pk_set is not None else instance.promotions.all()
    else:
        promotions = Promotion.objects.filter(pk=instance.pk)
    for promotion in promotions.order_by("pk").select_for_update():
        actuelles = set(promotion.succursales.values_list("pk", flat=True))
        concernees = {instance.pk} if reverse else set(pk_set or actuelles)
        modifiees = (concernees - actuelles) if action == "pre_add" else (concernees & actuelles)
        if modifiees and (promotion.annulee_le or promotion.transactions.exists()):
            raise ValidationError("Les succursales d’une promotion utilisée sont figées.")
        if action == "pre_add":
            verifier_periodes_promotion(promotion, concernees)
