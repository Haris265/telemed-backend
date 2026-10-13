# Generated manually for superadmin + clinic_admin roles

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0008_doctorclinic_order_by_created"),
        ("accounts", "0002_patient_role_and_user_link"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("superadmin", "Superadmin"),
                    ("admin", "Admin"),
                    ("clinic_admin", "Clinic Admin"),
                    ("doctor", "Doctor"),
                    ("patient", "Patient"),
                ],
                default="admin",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="ClinicAdminProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "clinic",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clinic_admins",
                        to="catalog.clinic",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clinic_admin_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
