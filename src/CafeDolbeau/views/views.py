from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from ..forms.forms import AchatCartesForm, AjoutCafesForm, ClientForm
from ..forms.forms_annulation import EffetsAnciennesFormSet, SelectionAnciennesForm
from ..models import Client, FusionClient, TransactionCafe
from ..permissions import PERMISSION_GERANT, acces_base_requis, gerant_requis, peut_annuler
from ..services import ajouter_cafes, annuler_operation, preparer_annulation, recapitulatif_annulation


def historique_client(client, employe):
    lignes = list(client.transactions_cafe.select_related("employe", "annulation__employe")[:10])
    for ligne in lignes:
        ligne.annulation_disponible = peut_annuler(ligne, employe)
    return lignes

@never_cache
@acces_base_requis
def accueil(request):
    """Recherche des clients et gère leur ajout depuis l'accueil."""
    recherche = request.GET.get("q", "").strip()
    resultats = Client.objects.filter(est_actif=True).exclude(pk=Client.ID_SUPPRIME)
    if recherche:
        resultats = resultats.filter(
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

@never_cache
@acces_base_requis
def ajouter_cafes_client(request, pk):
    client = get_object_or_404(Client.objects.exclude(pk=Client.ID_SUPPRIME), pk=pk)
    if not client.est_actif:
        if request.method == "POST":
            raise PermissionDenied("Ce client est désactivé par une fusion.")
        fusion = FusionClient.en_attente_pour(client.pk).filter(client_source_id=client.pk).first()
        if fusion and Client.objects.filter(pk=fusion.client_destination_id, est_actif=True).exists():
            return redirect("ajouter_cafes", pk=fusion.client_destination_id)
        raise Http404
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
            try:
                transactions = ajouter_cafes(client, form.cleaned_data["quantite"], type_transaction, employe=request.user)
            except Client.DoesNotExist:
                raise Http404("Ce client a été supprimé.")
            except ValidationError as erreur:
                form.add_error(None, erreur)
                if asynchrone:
                    return JsonResponse({"erreurs": form.errors.get_json_data()}, status=400)
                return render(request, "ajouter_cafes.html", {
                    "client": client, "form": formulaires[TransactionCafe.Type.ACHAT],
                    "form_prepaye": formulaires[TransactionCafe.Type.PREPAYE],
                    "transactions": historique_client(client, request.user),
                    "fusion_en_attente": FusionClient.en_attente_pour(client.pk).first(),
                }, status=400)
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
                    "gratuits": client.nombre_cafes_gratuits,
                    "fusion_en_attente": FusionClient.en_attente_pour(client.pk).exists(),
                    "messages": [
                        {"texte": str(message), "tags": message.tags}
                        for message in messages.get_messages(request)
                    ],
                    "historique": render_to_string("transactions_cafe.html", {
                        "transactions": historique_client(client, request.user),
                    }, request=request),
                })
            return redirect("ajouter_cafes", pk=client.pk)
        if asynchrone:
            return JsonResponse({"erreurs": form.errors.get_json_data()}, status=400)
    return render(request, "ajouter_cafes.html", {
        "client": client,
        "form": formulaires[TransactionCafe.Type.ACHAT],
        "form_prepaye": formulaires[TransactionCafe.Type.PREPAYE],
        "transactions": historique_client(client, request.user),
        "fusion_en_attente": FusionClient.en_attente_pour(client.pk).first(),
    })


@never_cache
@acces_base_requis
@require_http_methods(["GET", "POST"])
def annuler_transaction(request, pk, transaction_id):
    return _annuler_transaction(request, transaction_id, pk=pk)


@never_cache
@gerant_requis
@require_http_methods(["GET", "POST"])
def annuler_transaction_admin(request, transaction_id):
    return _annuler_transaction(request, transaction_id, origine_admin=True)


def _annuler_transaction(request, transaction_id, *, pk=None, origine_admin=False):
    source = get_object_or_404(
        TransactionCafe.objects.select_related("client", "employe", "annulation__employe"),
        pk=transaction_id, **({"client_id": pk} if pk is not None else {}),
    )
    gerant = request.user.has_perm(PERMISSION_GERANT)
    if not gerant and (source.client_id == Client.ID_SUPPRIME or source.employe_id != request.user.pk):
        raise PermissionDenied
    origine_admin = origine_admin or (request.GET.get("origine") == "admin" and gerant)
    contexte = {
        "client": source.client, "source": source, "origine_admin": origine_admin,
        "client_supprime": source.client_id == Client.ID_SUPPRIME,
    }
    if FusionClient.en_attente_pour(source.client_id).exists():
        contexte["erreurs"] = ["Annulez ou finalisez la fusion avant d'annuler une transaction de ces clients."]
        return render(request, "annuler_transaction.html", contexte, status=400)
    statut = 200

    def terminer(nombre):
        messages.success(request, "L’opération a été annulée." if nombre else "Cette opération est déjà annulée.")
        if origine_admin or not Client.objects.filter(pk=pk).exists():
            return redirect("admin:CafeDolbeau_transactioncafe_changelist")
        return redirect("ajouter_cafes", pk=pk)

    try:
        if request.method == "POST" and request.POST.get("action") == "confirmer":
            try:
                confirmation = signing.loads(request.POST.get("confirmation", ""), salt="annulation-cafe", max_age=1800)
                if confirmation["source"] != source.pk or confirmation["employe"] != request.user.pk:
                    raise signing.BadSignature
                if not source.annulee and confirmation["operation"] != (str(source.operation_id) if source.operation_id else None):
                    raise ValidationError("L’opération a changé. Actualisez le récapitulatif.")
                details = confirmation.get("details")
                if details is not None:
                    details = {int(identifiant): tuple(valeurs) for identifiant, valeurs in details.items()}
            except (signing.BadSignature, KeyError, TypeError, ValueError):
                raise ValidationError("La confirmation est invalide ou expirée. Ouvrez à nouveau le récapitulatif.")
            return terminer(annuler_operation(source.pk, request.user, details))

        if source.annulee:
            contexte["deja_annulee"] = True
        elif source.operation_id:
            if request.method == "POST":
                return HttpResponseBadRequest("Action d’annulation invalide.")
            lignes = preparer_annulation(source, request.user)
            if all(ligne.annulee for ligne in lignes):
                contexte["deja_annulee"] = True
            else:
                contexte.update(lignes=lignes, soldes=recapitulatif_annulation(source.client, lignes))
                contexte["confirmation"] = signing.dumps({
                    "source": source.pk, "employe": request.user.pk,
                    "operation": str(source.operation_id), "details": None,
                }, salt="annulation-cafe")
        else:
            selection = SelectionAnciennesForm(
                request.POST if request.method == "POST" else None,
                client=source.client, source=source,
            )
            contexte["selection"] = selection
            action = request.POST.get("action")
            if request.method == "POST" and action not in ("completer", "previsualiser"):
                return HttpResponseBadRequest("Action d’annulation invalide.")
            if request.method == "POST" and selection.is_valid():
                lignes = list(selection.cleaned_data["lignes"])
                effets = EffetsAnciennesFormSet(
                    request.POST if action == "previsualiser" else None,
                    lignes=lignes, initial=[{"transaction_id": ligne.pk} for ligne in lignes],
                )
                contexte.update(effets=effets, lignes_selectionnees=lignes)
                if action == "previsualiser" and effets.is_valid():
                    details = effets.details()
                    lignes = preparer_annulation(source, request.user, details)
                    contexte.update(lignes=lignes, soldes=recapitulatif_annulation(source.client, lignes))
                    contexte["confirmation"] = signing.dumps({
                        "source": source.pk, "employe": request.user.pk,
                        "operation": None, "details": details,
                    }, salt="annulation-cafe", compress=True)
    except ValidationError as erreur:
        contexte["erreurs"] = erreur.messages
        statut = 400
    except OperationalError:
        contexte["erreurs"] = ["L’opération est momentanément indisponible. Actualisez le récapitulatif avant de réessayer."]
        statut = 503
    return render(request, "annuler_transaction.html", contexte, status=statut)
