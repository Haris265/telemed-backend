from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0004_clinical_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="visit_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="appointment",
            name="visit_ended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
