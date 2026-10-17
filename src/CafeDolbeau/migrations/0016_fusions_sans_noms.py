import django.db.models.deletion
from django.db import migrations, models


def detacher_clients_supprimes(apps, schema_editor):
    alias = schema_editor.connection.alias
    Client = apps.get_model("CafeDolbeau", "Client")
    FusionClient = apps.get_model("CafeDolbeau", "FusionClient")
    clients = Client.objects.using(alias).values("pk")
    fusions = FusionClient.objects.using(alias)
    fusions.exclude(client_source_id__in=clients).update(client_source_id=None)
    fusions.exclude(client_destination_id__in=clients).update(client_destination_id=None)


class Migration(migrations.Migration):
    dependencies = [("CafeDolbeau", "0015_date_application_gratuite")]

    operations = [
        migrations.RemoveConstraint(
            model_name="fusionclient", name="fusion_clients_distincts_positifs",
        ),
        migrations.RemoveConstraint(
            model_name="fusionclient", name="fusion_source_en_attente_unique",
        ),
        migrations.RemoveConstraint(
            model_name="fusionclient", name="fusion_destination_en_attente_unique",
        ),
        migrations.AlterField(
            model_name="fusionclient", name="client_source_id",
            field=models.PositiveBigIntegerField(editable=False, null=True, verbose_name="ID du client fusionné"),
        ),
        migrations.AlterField(
            model_name="fusionclient", name="client_destination_id",
            field=models.PositiveBigIntegerField(editable=False, null=True, verbose_name="ID du client conservé"),
        ),
        migrations.RunPython(detacher_clients_supprimes, migrations.RunPython.noop),
        migrations.RenameField(
            model_name="fusionclient", old_name="client_source_id", new_name="client_source",
        ),
        migrations.RenameField(
            model_name="fusionclient", old_name="client_destination_id", new_name="client_destination",
        ),
        migrations.AlterField(
            model_name="fusionclient", name="client_source",
            field=models.ForeignKey(
                blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="fusions_comme_source", to="CafeDolbeau.client", verbose_name="client fusionné",
            ),
        ),
        migrations.AlterField(
            model_name="fusionclient", name="client_destination",
            field=models.ForeignKey(
                blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="fusions_comme_destination", to="CafeDolbeau.client", verbose_name="client conservé",
            ),
        ),
        migrations.RemoveField(model_name="fusionclient", name="source_nom"),
        migrations.RemoveField(model_name="fusionclient", name="destination_nom"),
        migrations.AddConstraint(
            model_name="fusionclient",
            constraint=models.CheckConstraint(
                condition=(
                    (models.Q(client_source__isnull=True) | models.Q(client_source__gt=0))
                    & (models.Q(client_destination__isnull=True) | models.Q(client_destination__gt=0))
                    & (models.Q(client_source__isnull=True) | models.Q(client_destination__isnull=True)
                       | ~models.Q(client_source=models.F("client_destination")))
                ),
                name="fusion_clients_distincts_positifs",
            ),
        ),
        migrations.AddConstraint(
            model_name="fusionclient",
            constraint=models.UniqueConstraint(
                fields=["client_source"], condition=models.Q(statut="en_attente"),
                name="fusion_source_en_attente_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="fusionclient",
            constraint=models.UniqueConstraint(
                fields=["client_destination"], condition=models.Q(statut="en_attente"),
                name="fusion_destination_en_attente_unique",
            ),
        ),
    ]
