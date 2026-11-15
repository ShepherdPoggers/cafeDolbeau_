from django.core.paginator import Paginator
from django.http import FileResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from ..forms.forms_rapports import RapportForm
from ..models import TransactionCafe
from ..permissions import gerant_requis, succursales_autorisees
from ..rapports import FUSEAU_RAPPORT, exporter_excel, generer_rapport


def _formulaire(request):
    if request.GET:
        return RapportForm(request.GET, employe=request.user)
    aujourd_hui = timezone.localdate(timezone=FUSEAU_RAPPORT)
    return RapportForm({
        "precision": "periode", "date_debut": aujourd_hui.replace(day=1),
        "date_fin": aujourd_hui, "types": [TransactionCafe.Type.ACHAT, TransactionCafe.Type.PREPAYE],
        "succursales": list(succursales_autorisees(request.user).values_list("pk", flat=True)),
    }, employe=request.user)


def _generer(request, form):
    filtres = form.cleaned_data.copy()
    succursales = filtres.pop("succursales")
    return generer_rapport(
        **filtres, employe=request.user,
        # Garder les choix validés : une nouvelle requête sur ce queryset
        # pourrait en retirer silencieusement après un retrait d’affectation.
        succursale_ids=[succursale.pk for succursale in succursales],
    )


def _contexte(request, form):
    return {"form": form, "aucune_succursale": not succursales_autorisees(request.user).exists()}


@never_cache
@gerant_requis
@require_GET
def rapports(request):
    form = _formulaire(request)
    contexte = _contexte(request, form)
    if form.is_valid():
        rapport = _generer(request, form)
        contexte["rapport"] = rapport
        if rapport.precision == "transaction":
            contexte["page_evenements"] = Paginator(rapport.evenements, 50).get_page(request.GET.get("page"))
            filtres = request.GET.copy()
            filtres.pop("page", None)
            contexte["filtres_pagination"] = filtres.urlencode()
    return render(request, "rapports.html", contexte)


@never_cache
@gerant_requis
@require_GET
def rapport_excel(request):
    form = _formulaire(request)
    if not form.is_valid():
        return render(request, "rapports.html", _contexte(request, form), status=400)
    rapport = _generer(request, form)
    fichier = exporter_excel(rapport)
    nom = f"rapport_cafes_{rapport.date_debut.isoformat()}_{rapport.date_fin.isoformat()}.xlsx"
    return FileResponse(fichier, as_attachment=True, filename=nom,
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
