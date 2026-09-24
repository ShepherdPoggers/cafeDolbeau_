from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from .models import Client, TransactionCafe


@transaction.atomic
def ajouter_cafes(client, quantite, type_transaction=TransactionCafe.Type.ACHAT):
    """Quantité en cartes pour PREPAYE, en cafés pour ACHAT ou UTILISE.

    Chaque carte crédite 11 cafés aux deux compteurs. Sa consommation ne
    compte pas comme un nouvel achat et ne déclenche pas une seconde gratuité.
    """
    if type_transaction not in (
        TransactionCafe.Type.ACHAT, TransactionCafe.Type.PREPAYE, TransactionCafe.Type.UTILISE,
    ):
        raise ValidationError("Type de transaction invalide.")
    ajout = TransactionCafe(client=client, quantite=quantite, type_transaction=type_transaction)
    ajout.full_clean()
    quantite = ajout.quantite
    # Relit les compteurs actuels pour les commandes et les achats de cartes.
    client = Client.objects.select_for_update().get(pk=client.pk)
    if type_transaction == TransactionCafe.Type.PREPAYE:
        cafes = quantite * 11
        ajout.quantite = cafes
        ajout.full_clean()
        Client.objects.filter(pk=client.pk).update(
            nombre_cafes_prepayes=F("nombre_cafes_prepayes") + cafes,
            nombre_cafes_achetes=F("nombre_cafes_achetes") + cafes,
        )
        ajout.save()
        return [ajout]

    utilises = (
        min(client.nombre_cafes_prepayes, quantite)
        if type_transaction == TransactionCafe.Type.UTILISE else 0
    )
    hors_carte = quantite - utilises
    total = client.nombre_cafes_achetes
    # Les cartes ajoutent des multiples de 11 : elles ne décalent pas
    # la progression vers le prochain café gratuit hors carte.
    gratuits = (total + hors_carte) // 11 - total // 11
    payants = hors_carte - gratuits
    Client.objects.filter(pk=client.pk).update(
        nombre_cafes_achetes=F("nombre_cafes_achetes") + hors_carte,
        nombre_cafes_prepayes=F("nombre_cafes_prepayes") - utilises,
    )
    transactions = []
    for type_cafe, nombre in (
        (TransactionCafe.Type.UTILISE, utilises),
        (TransactionCafe.Type.ACHAT, payants),
        (TransactionCafe.Type.GRATUIT, gratuits),
    ):
        if nombre:
            transactions.append(TransactionCafe.objects.create(
                client=client, quantite=nombre, type_transaction=type_cafe
            ))
    return transactions
