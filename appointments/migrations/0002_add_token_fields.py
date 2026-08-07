import datetime

from django.db import migrations, models


def backfill_tokens(apps, schema_editor):
    Appointment = apps.get_model("appointments", "Appointment")
    counters: dict[tuple[int, datetime.date], int] = {}
    for appt in Appointment.objects.order_by("id"):
        day = appt.scheduled_at.date() if appt.scheduled_at else datetime.date.today()
        key = (appt.doctor_id, day)
        counters[key] = counters.get(key, 0) + 1
        appt.token_date = day
        appt.token_number = counters[key]
        appt.save(update_fields=["token_date", "token_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="token_date",
            field=models.DateField(db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="appointment",
            name="token_number",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.RunPython(backfill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="appointment",
            name="token_date",
            field=models.DateField(db_index=True),
        ),
        migrations.AlterField(
            model_name="appointment",
            name="token_number",
            field=models.PositiveIntegerField(),
        ),
        migrations.AlterModelOptions(
            name="appointment",
            options={"ordering": ["-token_date", "token_number"]},
        ),
        migrations.AddConstraint(
            model_name="appointment",
            constraint=models.UniqueConstraint(
                fields=("doctor", "token_date", "token_number"),
                name="uniq_doctor_token_per_day",
            ),
        ),
    ]
