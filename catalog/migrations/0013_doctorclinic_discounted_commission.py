from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0012_doctorclinic_commission"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctorclinic",
            name="discounted_commission_type",
            field=models.CharField(
                choices=[("percentage", "Percentage"), ("fixed", "Fixed")],
                default="percentage",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="doctorclinic",
            name="discounted_commission_value",
            field=models.DecimalField(
                decimal_places=2,
                default=20,
                help_text="Clinic commission for discounted/jamat patients.",
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name="doctorclinic",
            name="discounted_commission_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
