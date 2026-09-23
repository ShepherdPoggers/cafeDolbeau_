from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AjoutCafesForm, ClientForm
from .models import Client
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
    form = AjoutCafesForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        ajouter_cafes(client, form.cleaned_data["quantite"])
        messages.success(request, "La transaction de cafés a été enregistrée.")
        return redirect("ajouter_cafes", pk=client.pk)
    return render(request, "ajouter_cafes.html", {
        "client": client,
        "form": form,
        "transactions": client.transactions_cafe.all()[:50],
    })
