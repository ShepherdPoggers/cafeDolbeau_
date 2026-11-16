"""Adaptation V3 de l’exécution de 0016, sans modifier la migration livrée en V2."""
from importlib import import_module

from django.db import migrations


historique = import_module("CafeDolbeau.migrations.0016_fusions_sans_noms")


def verifier_contraintes_postgresql(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.connection.check_constraints()


class Migration(migrations.Migration):
    # Django reconnaît les installations où 0016 est déjà appliquée : aucune
    # opération de schéma ou de données n’est alors rejouée.
    replaces = [("CafeDolbeau", "0016_fusions_sans_noms")]
    dependencies = historique.Migration.dependencies

    # Les six premières opérations vont jusqu’au détachement des clients
    # supprimés. Vider les vérifications différées avant les ALTER TABLE suivants
    # évite l’erreur PostgreSQL « pending trigger events » dans cette transaction.
    operations = [
        *historique.Migration.operations[:6],
        migrations.RunPython(verifier_contraintes_postgresql, migrations.RunPython.noop),
        *historique.Migration.operations[6:],
    ]
