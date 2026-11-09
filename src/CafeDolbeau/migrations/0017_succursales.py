import django.db.models.deletion
from django.core.management.color import no_style
from django.db import migrations, models


def creer_succursale_initiale(apps, schema_editor):
    Succursale = apps.get_model("CafeDolbeau", "Succursale")
    connexion = schema_editor.connection
    Succursale.objects.using(connexion.alias).get_or_create(
        pk=1, defaults={"nom": "Succursale #1"},
    )
    # L'insertion d'un identifiant explicite n'avance pas la séquence PostgreSQL.
    for sql in connexion.ops.sequence_reset_sql(no_style(), [Succursale]):
        schema_editor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [("CafeDolbeau", "0016_fusions_sans_noms")]

    operations = [
        migrations.CreateModel(
            name="Succursale",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nom", models.CharField(max_length=200, verbose_name="nom")),
            ],
            options={
                "verbose_name": "succursale",
                "verbose_name_plural": "succursales",
                "ordering": ["pk"],
            },
        ),
        migrations.RunPython(creer_succursale_initiale, migrations.RunPython.noop),
        migrations.AddField(
            model_name="transactioncafe",
            name="succursale",
            field=models.ForeignKey(
                default=1, on_delete=django.db.models.deletion.PROTECT,
                related_name="transactions_cafe", to="CafeDolbeau.succursale",
                verbose_name="succursale",
            ),
        ),
    ]
