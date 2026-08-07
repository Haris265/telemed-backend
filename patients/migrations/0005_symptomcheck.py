from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
        ("patients", "0004_patient_role_and_user_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="SymptomCheck",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("symptoms_text", models.TextField()),
                (
                    "urgency",
                    models.CharField(
                        choices=[
                            ("routine", "Routine"),
                            ("urgent", "Urgent"),
                            ("emergency", "Emergency"),
                        ],
                        default="routine",
                        max_length=20,
                    ),
                ),
                ("summary", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="symptom_checks",
                        to="patients.patientprofile",
                    ),
                ),
                (
                    "recommended_specialities",
                    models.ManyToManyField(
                        blank=True,
                        related_name="symptom_checks",
                        to="catalog.speciality",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
