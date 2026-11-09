import django.db.models.deletion
from django.db import migrations, models


def creer_role_et_affectations(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")
    Affectation = apps.get_model("CafeDolbeau", "AffectationEmployeSuccursale")
    contenu, _ = ContentType.objects.using(alias).get_or_create(app_label="CafeDolbeau", model="employe")
    permission, _ = Permission.objects.using(alias).get_or_create(
        content_type=contenu, codename="acces_proprietaire",
        defaults={"name": "Accéder à toutes les succursales et gérer les employés"},
    )
    groupe, _ = Group.objects.using(alias).get_or_create(name="Propriétaire")
    groupe.permissions.add(permission)
    groupe.permissions.add(*Permission.objects.using(alias).filter(
        content_type__app_label="CafeDolbeau",
        codename__in=("acces_base", "acces_gerant", "add_client", "view_client", "change_client", "delete_client"),
    ))
    employes = User.objects.using(alias).filter(groups__name__in=("Barista", "Gérant")).distinct()
    for employe_id in employes.values_list("pk", flat=True).iterator():
        Affectation.objects.using(alias).get_or_create(employe_id=employe_id, succursale_id=1)


class Migration(migrations.Migration):
    dependencies = [("CafeDolbeau", "0017_succursales")]

    operations = [
        migrations.AlterModelOptions(
            name="employe",
            options={
                "verbose_name": "employé", "verbose_name_plural": "employés", "default_permissions": (),
                "permissions": [
                    ("acces_base", "Accéder aux fonctions de base du café"),
                    ("acces_gerant", "Accéder aux fonctions de gérant du café"),
                    ("acces_proprietaire", "Accéder à toutes les succursales et gérer les employés"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AffectationEmployeSuccursale",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("employe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="affectations_succursales", to="CafeDolbeau.employe", verbose_name="employé")),
                ("succursale", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="affectations_employes", to="CafeDolbeau.succursale")),
            ],
            options={
                "verbose_name": "affectation à une succursale",
                "verbose_name_plural": "affectations aux succursales",
                "constraints": [models.UniqueConstraint(fields=("employe", "succursale"), name="affectation_employe_succursale_unique")],
            },
        ),
        migrations.RunPython(creer_role_et_affectations, migrations.RunPython.noop),
    ]
