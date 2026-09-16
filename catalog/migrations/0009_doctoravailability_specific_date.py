from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0008_doctorclinic_order_by_created"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctoravailability",
            name="specific_date",
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text="When set, this row overrides weekly hours for this date only.",
                null=True,
            ),
        ),
        migrations.AlterModelOptions(
            name="doctoravailability",
            options={
                "ordering": ["specific_date", "weekday", "start_time"],
                "verbose_name_plural": "doctor availabilities",
            },
        ),
    ]
