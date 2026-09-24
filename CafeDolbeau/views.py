from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AchatCartesForm, AjoutCafesForm, ClientForm
from .models import Client, TransactionCafe
from .services import ajouter_cafes

# Create your views here.



    
def accueil(request):
    """Recherche des clients et gère leur ajout depuis l'accueil."""
    recherche = request.GET.get("q", "").strip()
    resultats = Client.objects.all()
    if recherche:
        resultats = Client.objects.filter(
            Q(nom_complet__icontains=recherche)
            | Q(telephone__icontains=recherche)
            | Q(courriel__icontains=recherche)
        )
    if request.method == "GET" and request.GET.get("partiel") == "recherche":
        return render(request, "resultats_recherche.html", {
            "recherche": recherche,
            "resultats": resultats,
        })
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

def ajouter_cafes_client(request, pk):
    client = get_object_or_404(Client, pk=pk)
    asynchrone = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    formulaires = {
        TransactionCafe.Type.ACHAT: AjoutCafesForm(),
        TransactionCafe.Type.PREPAYE: AchatCartesForm(auto_id="prepaye_%s"),
        TransactionCafe.Type.UTILISE: AjoutCafesForm(),

    }
    if request.method == "POST":
        type_transaction = request.POST.get("type_transaction", TransactionCafe.Type.ACHAT)
        if type_transaction not in formulaires:
            return HttpResponseBadRequest("Type de transaction invalide.")
        classe_formulaire = type(formulaires[type_transaction])
        form = classe_formulaire(request.POST, auto_id=f"{type_transaction}_%s")
        formulaires[type_transaction] = form
        if form.is_valid():
            transactions = ajouter_cafes(client, form.cleaned_data["quantite"], type_transaction)
            messages.success(request, "La transaction de cafés a été enregistrée.")
            gratuits = sum(t.quantite for t in transactions if t.type_transaction == TransactionCafe.Type.GRATUIT)
            if gratuits:
                messages.success(request, "Fecilication un café gratuit est accordé", extra_tags="felicitations")
                if gratuits > 1:
                    messages.success(request, f"{gratuits} cafés gratuits accordés au total.")
            if asynchrone:
                client.refresh_from_db()
                return JsonResponse({
                    "achetes": client.nombre_cafes_achetes,
                    "prepayes": client.nombre_cafes_prepayes,
                    "messages": [
                        {"texte": str(message), "tags": message.tags}
                        for message in messages.get_messages(request)
                    ],
                    "historique": render_to_string("transactions_cafe.html", {
                        "transactions": client.transactions_cafe.all()[:50],
                    }),
                })
            return redirect("ajouter_cafes", pk=client.pk)
        if asynchrone:
            return JsonResponse({"erreurs": form.errors.get_json_data()}, status=400)
    return render(request, "ajouter_cafes.html", {
        "client": client,
        "form": formulaires[TransactionCafe.Type.ACHAT],
        "form_prepaye": formulaires[TransactionCafe.Type.PREPAYE],
        "transactions": client.transactions_cafe.all()[:50],
    })
