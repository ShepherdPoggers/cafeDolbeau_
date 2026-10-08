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
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from CafeDolbeau import views
from CafeDolbeau.forms import ConnexionForm


urlpatterns = [
    path('connexion/', LoginView.as_view(
        template_name='registration/login.html',
        authentication_form=ConnexionForm,
        redirect_authenticated_user=True,
    ), name='connexion'),
    path('deconnexion/', LogoutView.as_view(), name='deconnexion'),
    path('admin/', admin.site.urls),
    path('', views.accueil, name="accueil"),
    path('clients/<int:pk>/cafes/', views.ajouter_cafes_client, name="ajouter_cafes"),
    path('clients/<int:pk>/transactions/<int:transaction_id>/annuler/', views.annuler_transaction, name="annuler_transaction"),
]
