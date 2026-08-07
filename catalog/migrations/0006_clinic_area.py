from django.db import migrations, models


AREA_BY_NAME = {
    "Telemed Clifton Care": "Clifton",
    "Telemed Gulshan Clinic": "Gulshan",
    "Telemed DHA Medical Centre": "DHA",
}


def backfill_clinic_areas(apps, schema_editor):
    Clinic = apps.get_model("catalog", "Clinic")
    for name, area in AREA_BY_NAME.items():
        Clinic.objects.filter(name=name, area="").update(area=area)


def clear_clinic_areas(apps, schema_editor):
    Clinic = apps.get_model("catalog", "Clinic")
    Clinic.objects.filter(name__in=AREA_BY_NAME.keys()).update(area="")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0005_assign_doctors_to_clinics"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinic",
            name="area",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Neighbourhood/area name used for map search (e.g. Gulshan, Clifton).",
                max_length=100,
            ),
        ),
        migrations.RunPython(backfill_clinic_areas, clear_clinic_areas),
    ]
