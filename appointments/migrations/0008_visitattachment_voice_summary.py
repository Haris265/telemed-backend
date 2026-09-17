# Generated manually for voice Roman Urdu summary fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0007_visit_attachment"),
    ]

    operations = [
        migrations.AddField(
            model_name="visitattachment",
            name="transcript_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="visitattachment",
            name="summary_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="visitattachment",
            name="summary_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                    ("skipped", "Skipped"),
                ],
                default="skipped",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="visitattachment",
            name="summary_error",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
