# Generated manually for voice follow-up reminder fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0008_visitattachment_voice_summary"),
    ]

    operations = [
        migrations.AddField(
            model_name="visitattachment",
            name="follow_up_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="visitattachment",
            name="follow_up_reminder_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
