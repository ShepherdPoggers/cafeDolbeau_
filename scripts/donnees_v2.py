"""Créer directement une base V2 avec des scénarios fonctionnels."""
from datetime import timedelta

from _donnees_test import attribuer_roles, comptes, initialiser, terminer


def main():
    initialiser()
    from django.core.management import call_command
    from django.db import transaction
    from django.utils import timezone
    call_command("migrate", interactive=False, verbosity=0)
    from CafeDolbeau.models import Client, TransactionCafe
    from CafeDolbeau.services import ajouter_cafes, annuler_operation, fusionner_clients, supprimer_clients

    with transaction.atomic():
        utilisateurs = comptes()
        attribuer_roles(utilisateurs)
        gerant = utilisateurs["gerant_test"]
        barista = utilisateurs["barista_test"]
        autre = utilisateurs["barista2_test"]
        clients = []
        for index, nom in enumerate([
            "Alice Tremblay", "Benoît Gagnon", "Camille Roy", "Dominique Fortin",
            "Fusion source", "Fusion destination", "Client à supprimer", "Alice Tremblay",
        ], 1):
            clients.append(Client.objects.create(
                nom_complet=nom, telephone=f"418-555-{index:04d}" if index != 4 else "",
                courriel=f"client{index}@example.test" if index != 8 else "",
            ))
        ajouter_cafes(clients[0], 9, employe=barista)
        ajouter_cafes(clients[1], 10, employe=barista)
        ajouter_cafes(clients[2], 20, TransactionCafe.Type.PREPAYE, employe=autre)
        ajouter_cafes(clients[2], 5, TransactionCafe.Type.UTILISE, employe=autre)
        ajouter_cafes(clients[1], 2, employe=autre)
        ligne = clients[1].transactions_cafe.order_by("-pk").first()
        annuler_operation(ligne.pk, gerant)
        ajouter_cafes(clients[4], 3, employe=barista)
        ajouter_cafes(clients[5], 4, employe=autre)
        fusionner_clients(clients[4].pk, clients[5].pk, employe=gerant)
        ajouter_cafes(clients[6], 10, TransactionCafe.Type.PREPAYE, employe=barista)
        supprimer_clients([clients[6].pk], employe=gerant)
        # Étaler les opérations sur plusieurs périodes pour les rapports.
        operations = list(TransactionCafe.objects.order_by("pk").values_list("operation_id", flat=True).distinct())
        for index, operation in enumerate(dict.fromkeys(operations)):
            TransactionCafe.objects.filter(operation_id=operation).update(
                date_creation=timezone.now() - timedelta(days=45-index*4))
    print("V2 : achats, récompenses, cartes, consommation, annulation, fusion réversible et suppression avec historique.")
    terminer()


if __name__ == "__main__":
    main()
