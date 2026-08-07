import uuid

from django.db import migrations, models


def fill_doctor_uuids(apps, schema_editor):
    DoctorProfile = apps.get_model("catalog", "DoctorProfile")
    for row in DoctorProfile.objects.filter(uuid__isnull=True):
        row.uuid = uuid.uuid4()
        row.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctorprofile",
            name="uuid",
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(fill_doctor_uuids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="doctorprofile",
            name="uuid",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
