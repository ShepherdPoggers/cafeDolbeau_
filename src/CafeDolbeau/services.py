from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from .models import Client, TransactionCafe

# Utilisation de transaction.atomic pour all-or-nothing soit les tranaaction passe toute ou aucune.
@transaction.atomic
def ajouter_cafes(client : Client, quantite : int, type_transaction=TransactionCafe.Type.ACHAT):
    """Quantité en cartes pour PREPAYE, en cafés pour ACHAT ou UTILISE.

    Chaque carte crédite 11 cafés aux deux compteurs. Sa consommation ne
    compte pas comme un nouvel achat et ne déclenche pas une seconde gratuité.
    """
    if type_transaction not in (
        TransactionCafe.Type.ACHAT, TransactionCafe.Type.PREPAYE, TransactionCafe.Type.UTILISE,
    ):
        raise ValidationError("Type de transaction invalide.")
    client = Client.objects.select_for_update().get(pk=client.pk)
    # Relit les compteurs actuels pour les commandes et les achats de cartes.
    
    
    if type_transaction == TransactionCafe.Type.PREPAYE:
        return transaction_prepaye(client, quantite)

    utilises = (
        min(client.nombre_cafes_prepayes, quantite)
        if type_transaction == TransactionCafe.Type.UTILISE else 0
    )
    gratuits_utilises = (
    min(client.nombre_cafes_gratuits, quantite - utilises)
    if type_transaction == TransactionCafe.Type.UTILISE and utilises < quantite else 0
    )
  
    hors_carte = quantite - utilises - gratuits_utilises
    total = client.nombre_cafes_achetes
    gratuits = (total + hors_carte) // 10 - total // 10
    
    # Met à jours les différents compteurs
    Client.objects.filter(pk=client.pk).update(
        nombre_cafes_achetes=F("nombre_cafes_achetes") + hors_carte,
        nombre_cafes_prepayes=F("nombre_cafes_prepayes") - utilises,
        nombre_cafes_gratuits=F("nombre_cafes_gratuits") - gratuits_utilises + gratuits
    )
    transactions = []
    for type_cafe, nombre in (
        (TransactionCafe.Type.UTILISE, utilises + gratuits_utilises),
        (TransactionCafe.Type.ACHAT, hors_carte),
        (TransactionCafe.Type.GRATUIT, gratuits),
    ):
        if nombre:
            transactions.append(TransactionCafe.objects.create(
                client=client, quantite=nombre, type_transaction=type_cafe
            ))
    return transactions


def transaction_prepaye(client : Client, quantite : int):
    """Traitement d'une transaction prépayé"""
    ajout = TransactionCafe(client=client, quantite=quantite, type_transaction=TransactionCafe.Type.PREPAYE)
    ajout.full_clean()
    quantite = ajout.quantite
    cafes = quantite * 10
    ajout.quantite = cafes
    ajout.full_clean()
    Client.objects.filter(pk=client.pk).update(
        nombre_cafes_prepayes=F("nombre_cafes_prepayes") + cafes,
        nombre_cafes_achetes=F("nombre_cafes_achetes") + cafes,
        nombre_cafes_gratuits=F("nombre_cafes_gratuits") + quantite,
        )
    ajout.save()
    return [ajout]