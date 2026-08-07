from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


SAMPLE_CLINICS = [
    {
        "name": "Telemed Clifton Care",
        "address": "Block 5, Clifton Road",
        "city": "Karachi",
        "phone": "021111000111",
        "latitude": Decimal("24.813800"),
        "longitude": Decimal("67.029900"),
    },
    {
        "name": "Telemed Gulshan Clinic",
        "address": "Main University Road, Gulshan-e-Iqbal",
        "city": "Karachi",
        "phone": "021111000222",
        "latitude": Decimal("24.920000"),
        "longitude": Decimal("67.090000"),
    },
    {
        "name": "Telemed DHA Medical Centre",
        "address": "Khadafi Road, DHA Phase 5",
        "city": "Karachi",
        "phone": "021111000333",
        "latitude": Decimal("24.805000"),
        "longitude": Decimal("67.065000"),
    },
]


def seed_sample_clinics(apps, schema_editor):
    Clinic = apps.get_model("catalog", "Clinic")
    if Clinic.objects.exists():
        return
    for row in SAMPLE_CLINICS:
        Clinic.objects.create(**row, is_active=True)


def unseed_sample_clinics(apps, schema_editor):
    Clinic = apps.get_model("catalog", "Clinic")
    names = [row["name"] for row in SAMPLE_CLINICS]
    Clinic.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_doctor_subscription"),
    ]

    operations = [
        migrations.CreateModel(
            name="Clinic",
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
                ("name", models.CharField(max_length=200)),
                ("address", models.CharField(max_length=300)),
                ("city", models.CharField(blank=True, default="", max_length=100)),
                ("phone", models.CharField(blank=True, default="", max_length=30)),
                ("latitude", models.DecimalField(decimal_places=6, max_digits=9)),
                ("longitude", models.DecimalField(decimal_places=6, max_digits=9)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="clinic",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="doctors",
                to="catalog.clinic",
            ),
        ),
        migrations.RunPython(seed_sample_clinics, unseed_sample_clinics),
    ]
