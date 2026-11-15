"""Démonstration V3 ajoutée explicitement, sans réinitialiser la base."""
from datetime import timedelta
import secrets

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from ...models import (
    AffectationEmployeSuccursale, Client, Employe, Promotion,
    PromotionSuccursale, Succursale, TransactionCafe,
)
from ...promotions import annuler_promotion
from ...services import ajouter_cafes, annuler_operation


SUCCURSALES = ("[Démo V3] Centre", "[Démo V3] Nord", "[Démo V3] Sud")
# Nom, rôle, indices de succursales, activation.
EMPLOYES = (
    ("demo_proprietaire", "Propriétaire", (), True),
    ("demo_gerant_centre_nord", "Gérant", (0, 1), True),
    ("demo_gerant_sud", "Gérant", (2,), True),
    ("demo_barista_centre", "Barista", (0,), True),
    ("demo_barista_nord", "Barista", (1,), True),
    ("demo_barista_sud", "Barista", (2,), True),
    ("demo_barista_mobile", "Barista", (0, 2), True),
    ("demo_inactif", "Barista", (0,), False),
)


class Command(BaseCommand):
    help = "Ajouter les comptes, succursales, clients, promotions et transactions de démonstration V3."
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Mot de passe commun des comptes de démonstration ; aléatoire si omis.")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Le jeu V3 utilise uniquement PostgreSQL, selon la configuration courante.")
        mot_de_passe = options["password"] or ("DemoV3-" + secrets.token_urlsafe(20) + "!")
        jour = timezone.localdate()
        with transaction.atomic():
            groupes = {g.name: g for g in Group.objects.filter(name__in=("Propriétaire", "Gérant", "Barista"))}
            if len(groupes) != 3:
                raise CommandError("Les rôles sont absents. Appliquez les migrations avant de charger la démonstration.")
            if (
                Employe.objects.filter(username__in=[e[0] for e in EMPLOYES]).exists()
                or Succursale.objects.filter(nom__in=SUCCURSALES).exists()
                or Client.objects.filter(courriel__in=[f"demo-v3-{i}@example.test" for i in range(1, 7)]).exists()
                or Client.objects.filter(telephone__in=[f"418-555-01{i:02d}" for i in range(1, 7)]).exists()
            ):
                raise CommandError("Des identifiants de démonstration V3 existent déjà. Aucun changement effectué.")
            succursales = [Succursale.objects.create(nom=nom) for nom in SUCCURSALES]
            employes = {}
            for nom, role, indices, actif in EMPLOYES:
                employe = Employe.objects.create_user(
                    username=nom, password=mot_de_passe, is_active=actif,
                    is_staff=role in ("Propriétaire", "Gérant"), is_superuser=False,
                )
                employe.groups.add(groupes[role])
                for index in indices:
                    AffectationEmployeSuccursale.objects.create(employe=employe, succursale=succursales[index])
                employes[nom] = employe
            clients = [
                Client.objects.create(
                    nom_complet=f"[Démo V3] {nom}", telephone=f"418-555-01{i:02d}",
                    courriel=f"demo-v3-{i}@example.test",
                )
                for i, nom in enumerate(("Alice Tremblay", "Benoît Gagnon", "Camille Roy", "Dominique Fortin", "Émilie Bouchard", "Félix Simard"), 1)
            ]
            proprietaire = employes["demo_proprietaire"]

            def operation(client, quantite, index, auteur, type_cafe=TransactionCafe.Type.ACHAT, jours=0):
                lignes = ajouter_cafes(
                    client, quantite, type_cafe, employe=employes[auteur], succursale_id=succursales[index].pk,
                )
                if jours:
                    TransactionCafe.objects.filter(pk__in=[ligne.pk for ligne in lignes]).update(
                        date_creation=timezone.now() - timedelta(days=jours),
                    )
                return lignes

            # Fidélité habituelle, cartes prépayées et consommation dans le Sud.
            operation(clients[1], 12, 2, "demo_barista_sud", jours=7)
            operation(clients[2], 2, 2, "demo_barista_mobile", TransactionCafe.Type.PREPAYE, jours=5)
            operation(clients[2], 4, 2, "demo_barista_sud", TransactionCafe.Type.UTILISE, jours=4)

            active = Promotion.objects.create(
                nom="[Démo V3] Duo Centre et Nord", cafes_pour_gratuite=3,
                date_debut=jour - timedelta(days=14), date_fin=jour + timedelta(days=14),
            )
            for succursale in succursales[:2]:
                PromotionSuccursale.objects.create(promotion=active, succursale=succursale)
            operation(clients[0], 2, 0, "demo_barista_centre", jours=3)
            operation(clients[0], 2, 1, "demo_barista_nord", jours=2)
            operation(clients[0], 1, 0, "demo_barista_centre", TransactionCafe.Type.UTILISE, jours=1)
            # Plus de dix opérations et plusieurs auteurs pour tester l’historique global.
            for index in range(12):
                operation(clients[3], 1, index % 3, ("demo_barista_centre", "demo_barista_nord", "demo_barista_sud")[index % 3])
            lignes = operation(clients[4], 6, 0, "demo_barista_centre")
            annuler_operation(lignes[0].pk, employes["demo_gerant_centre_nord"], succursale_id=succursales[1].pk)

            annulee = Promotion.objects.create(
                nom="[Démo V3] Offre interrompue", cafes_pour_gratuite=2,
                date_debut=jour, date_fin=jour + timedelta(days=7),
            )
            PromotionSuccursale.objects.create(promotion=annulee, succursale=succursales[2])
            operation(clients[5], 5, 2, "demo_barista_sud")
            annuler_promotion(annulee.pk, employe=proprietaire, motif="Démonstration d’une annulation en cours.")
            future = Promotion.objects.create(
                nom="[Démo V3] Prochaine journée spéciale", cafes_pour_gratuite=4,
                date_debut=jour + timedelta(days=30), date_fin=jour + timedelta(days=30),
            )
            PromotionSuccursale.objects.create(promotion=future, succursale=succursales[2])

        self.stdout.write(self.style.SUCCESS("Démonstration V3 créée : 3 succursales, 8 employés, 6 clients et 3 promotions."))
        for nom, role, indices, actif in EMPLOYES:
            perimetre = "Tout le réseau" if role == "Propriétaire" else ", ".join(succursales[i].nom for i in indices)
            self.stdout.write(f"{nom} | {role} | {perimetre}" + (" | INACTIF" if not actif else ""))
        self.stdout.write(f"Mot de passe commun de démonstration : {mot_de_passe}")
        for succursale in succursales:
            self.stdout.write(f"{succursale.nom} : /succursales/{succursale.pk}/")
        self.stdout.write(f"Promotion active #{active.pk}, annulée #{annulee.pk}, à venir #{future.pk}. Rapports : /rapports/")
