"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from CafeDolbeau.views import views, views_rapports
from CafeDolbeau.views.views_auth import ConnexionView, DeconnexionView
from CafeDolbeau.views.views_sante import sante


urlpatterns = [
    path('healthz', sante, name="sante"),
    path('connexion/', ConnexionView.as_view(), name='connexion'),
    path('deconnexion/', DeconnexionView.as_view(), name='deconnexion'),
    path('admin/', admin.site.urls),
    path('', views.entree, name="accueil"),
    path('succursales/<int:succursale_id>/', views.accueil, name="accueil_succursale"),
    path('rapports/', views_rapports.rapports, name="rapports"),
    path('rapports/export.xlsx', views_rapports.rapport_excel, name="rapport_excel"),
    path('succursales/<int:succursale_id>/clients/<int:pk>/cafes/', views.ajouter_cafes_client, name="ajouter_cafes"),
    path('succursales/<int:succursale_id>/clients/<int:pk>/transactions/<int:transaction_id>/annuler/', views.annuler_transaction, name="annuler_transaction"),
    path('transactions/<int:transaction_id>/annuler/', views.annuler_transaction_admin, name="annuler_transaction_admin"),
]
