from django.shortcuts import render

# Create your views here.


def clients(request):
    return render(request, "clients.html", {
        "titre": "Nos Clients"
    })