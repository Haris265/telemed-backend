from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0010_payment_ocr_phase1"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="patient_type",
            field=models.CharField(
                choices=[("normal", "Normal"), ("discounted", "Discounted")],
                db_index=True,
                default="normal",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="jamat_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
    ]
