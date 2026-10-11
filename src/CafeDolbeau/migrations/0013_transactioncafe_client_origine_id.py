from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("CafeDolbeau", "0012_parametres_gratuite")]

    operations = [
        migrations.AddField(
            model_name="transactioncafe",
            name="client_origine_id",
            field=models.BigIntegerField(
                blank=True, db_index=True, editable=False, null=True,
                verbose_name="identifiant du client supprimé",
            ),
        ),
    ]
