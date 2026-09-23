from django.db import transaction
from django.db.models import F

from .models import Client, TransactionCafe


@transaction.atomic
def ajouter_cafes(client, quantite):
    """Enregistre la transaction et augmente le compteur en une seule opération."""
    ajout = TransactionCafe(client=client, quantite=quantite)
    ajout.full_clean()
    Client.objects.filter(pk=client.pk).update(
        nombre_cafes_achetes=F("nombre_cafes_achetes") + quantite
    )
    ajout.save()
    return ajout
