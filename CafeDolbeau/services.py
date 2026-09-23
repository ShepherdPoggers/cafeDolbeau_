from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest

from .models import Client, TransactionCafe


@transaction.atomic #Permet de s'assurer que les deux opérations dans la bd sont effectuées. Sinon on en fait aucune.
def ajouter_cafes(client, quantite, type_transaction=TransactionCafe.Type.ACHAT):
    """Retourne les transactions créées, en séparant les cafés gratuits."""
    if type_transaction not in (TransactionCafe.Type.ACHAT, TransactionCafe.Type.PREPAYE):
        raise ValidationError("Type de transaction invalide.")
    ajout = TransactionCafe(client=client, quantite=quantite, type_transaction=type_transaction)
    ajout.full_clean()
    if type_transaction == TransactionCafe.Type.PREPAYE:
        Client.objects.filter(pk=client.pk).update(
            nombre_cafes_prepayes=F("nombre_cafes_prepayes") + quantite
        )
        ajout.save()
        return [ajout]

    # Relit et verrouille le client pour calculer les seuils sur le total actuel.
    client = Client.objects.select_for_update().get(pk=client.pk)
    total = client.nombre_cafes_achetes
    gratuits = (total + quantite) // 11 - total // 11
    payants = quantite - gratuits
    Client.objects.filter(pk=client.pk).update(
        nombre_cafes_achetes=F("nombre_cafes_achetes") + quantite,
        nombre_cafes_prepayes=Greatest(F("nombre_cafes_prepayes") - payants, 0),
    )
    transactions = []
    for type_cafe, nombre in (
        (TransactionCafe.Type.ACHAT, payants),
        (TransactionCafe.Type.GRATUIT, gratuits),
    ):
        if nombre:
            transactions.append(TransactionCafe.objects.create(
                client=client, quantite=nombre, type_transaction=type_cafe
            ))
    return transactions
