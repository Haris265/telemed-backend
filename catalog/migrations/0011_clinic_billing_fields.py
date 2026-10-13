from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0010_payment_ocr_phase1"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinic",
            name="billing_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="clinic",
            name="owner_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
    ]
