from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse


class SanteTests(TestCase):
    def test_sante_accessible_sans_connexion_et_non_cachee(self):
        reponse = self.client.get(reverse("sante"))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json(), {"status": "ok"})
        self.assertIn("no-store", reponse["Cache-Control"])

    def test_base_indisponible_ne_divulgue_pas_erreur_interne(self):
        with patch("CafeDolbeau.views.views_sante.connection.cursor", side_effect=OperationalError("information-interne")):
            reponse = self.client.get(reverse("sante"))
        self.assertEqual(reponse.status_code, 503)
        self.assertEqual(reponse.json(), {"status": "unavailable"})
        self.assertNotContains(reponse, "information-interne", status_code=503)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_sante_interne_fonctionne_aussi_quand_https_est_active(self):
        self.assertEqual(self.client.get(reverse("sante")).status_code, 200)

    def test_sante_refuse_les_ecritures(self):
        self.assertEqual(self.client.post(reverse("sante")).status_code, 405)


class ConfigurationSecretsTests(SimpleTestCase):
    def test_generateur_complete_secrets_et_preserve_configuration_existante(self):
        racine = Path(__file__).resolve().parents[3]
        configurer = run_path(str(racine / "scripts/configurer_env.py"))["configurer"]
        with TemporaryDirectory() as dossier:
            chemin = Path(dossier) / ".env"
            chemin.write_text("SECRET_KEY=\nPOSTGRES_PASSWORD=\nPOSTGRES_DB=conserver\n")
            configurer(chemin)
            premier = chemin.read_text()
            valeurs = dict(ligne.split("=", 1) for ligne in premier.splitlines())
            self.assertGreaterEqual(len(valeurs["SECRET_KEY"]), 50)
            self.assertGreaterEqual(len(valeurs["POSTGRES_PASSWORD"]), 32)
            self.assertEqual(valeurs["POSTGRES_DB"], "conserver")
            configurer(chemin)
            self.assertEqual(chemin.read_text(), premier)
            self.assertEqual(chemin.stat().st_mode & 0o777, 0o600)
