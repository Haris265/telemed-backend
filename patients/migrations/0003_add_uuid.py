import uuid

from django.db import migrations, models


def fill_patient_uuids(apps, schema_editor):
    PatientProfile = apps.get_model("patients", "PatientProfile")
    for row in PatientProfile.objects.filter(uuid__isnull=True):
        row.uuid = uuid.uuid4()
        row.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0002_latest_first_ordering"),
    ]

    operations = [
        migrations.AddField(
            model_name="patientprofile",
            name="uuid",
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(fill_patient_uuids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="patientprofile",
            name="uuid",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
