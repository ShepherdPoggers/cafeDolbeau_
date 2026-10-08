from django.db import migrations


def creer_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    database = schema_editor.connection.alias
    content_type, _ = ContentType.objects.using(database).get_or_create(
        app_label="CafeDolbeau", model="client",
    )
    permissions = {}
    # Les permissions natives sont normalement créées après les migrations.
    # Les créer ici permet d'attribuer les rôles aussi sur une base neuve.
    for codename, name in (
        ("acces_base", "Accéder aux fonctions de base du café"),
        ("acces_gerant", "Accéder aux fonctions de gérant du café"),
        ("add_client", "Can add client"),
        ("change_client", "Can change client"),
        ("delete_client", "Can delete client"),
        ("view_client", "Can view client"),
    ):
        permissions[codename], _ = Permission.objects.using(database).get_or_create(
            content_type=content_type, codename=codename, defaults={"name": name},
        )
    barista, _ = Group.objects.using(database).get_or_create(name="Barista")
    gerant, _ = Group.objects.using(database).get_or_create(name="Gérant")
    barista.permissions.set([permissions["acces_base"]])
    gerant.permissions.set(permissions.values())


class Migration(migrations.Migration):
    dependencies = [
        ("CafeDolbeau", "0008_client_client_telephone_unique_non_vide_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="client",
            options={
                "ordering": ["nom_complet"],
                "verbose_name": "client",
                "verbose_name_plural": "clients",
                "permissions": [
                    ("acces_base", "Accéder aux fonctions de base du café"),
                    ("acces_gerant", "Accéder aux fonctions de gérant du café"),
                ],
            },
        ),
        # Un retour en arrière conserve les comptes et leurs groupes.
        migrations.RunPython(creer_roles, migrations.RunPython.noop),
    ]
