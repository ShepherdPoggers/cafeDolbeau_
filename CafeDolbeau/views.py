from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AjoutCafesForm, ClientForm
from .models import Client, TransactionCafe
from .services import ajouter_cafes

# Create your views here.



    
def accueil(request):
    """Recherche des clients et gère leur ajout depuis l'accueil."""
    recherche = request.GET.get("q", "").strip()
    resultats = Client.objects.none()
    if recherche:
        resultats = Client.objects.filter(
            Q(nom_complet__icontains=recherche)
            | Q(telephone__icontains=recherche)
            | Q(courriel__icontains=recherche)
        )
    form = ClientForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        form.save() # Crée un nouvel objet Client et l'enregistre dans la base de données.
        messages.success(request, "Le client a été ajouté avec succès.")
        return redirect("accueil")
    return render(request, "accueil.html", {
        "form": form,
        "recherche": recherche,
        "resultats": resultats,
    })


def modifier_client(request, pk):
    """Modifie les coordonnées d'un client existant."""
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(
        request.POST if request.method == "POST" else None,
        instance=client,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Le client a été modifié avec succès.")
        return redirect("accueil")
    return render(request, "modifier_client.html", {"form": form, "client": client})


def ajouter_cafes_client(request, pk):
    client = get_object_or_404(Client, pk=pk)
    formulaires = {
        TransactionCafe.Type.ACHAT: AjoutCafesForm(),
        TransactionCafe.Type.PREPAYE: AjoutCafesForm(auto_id="prepaye_%s"),
    }
    if request.method == "POST":
        type_transaction = request.POST.get("type_transaction", TransactionCafe.Type.ACHAT)
        if type_transaction not in formulaires:
            return HttpResponseBadRequest("Type de transaction invalide.")
        form = AjoutCafesForm(request.POST, auto_id=f"{type_transaction}_%s")
        formulaires[type_transaction] = form
        if form.is_valid():
            transactions = ajouter_cafes(client, form.cleaned_data["quantite"], type_transaction)
            messages.success(request, "La transaction de cafés a été enregistrée.")
            gratuits = sum(t.quantite for t in transactions if t.type_transaction == TransactionCafe.Type.GRATUIT)
            if gratuits:
                messages.success(request, "Fecilication un café gratuit est accordé", extra_tags="felicitations")
                if gratuits > 1:
                    messages.success(request, f"{gratuits} cafés gratuits accordés au total.")
            return redirect("ajouter_cafes", pk=client.pk)
    return render(request, "ajouter_cafes.html", {
        "client": client,
        "form": formulaires[TransactionCafe.Type.ACHAT],
        "form_prepaye": formulaires[TransactionCafe.Type.PREPAYE],
        "transactions": client.transactions_cafe.all()[:50],
    })
