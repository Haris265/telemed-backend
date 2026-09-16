# Generated manually for booking mode + clinic-first doctor pick

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("whatsapp", "0005_doctor_whatsapp_account"),
    ]

    operations = [
        migrations.AlterField(
            model_name="whatsappsession",
            name="state",
            field=models.CharField(
                choices=[
                    ("idle", "Idle"),
                    ("awaiting_name", "Awaiting Name"),
                    ("awaiting_otp", "Awaiting OTP"),
                    ("awaiting_booking_mode", "Awaiting Booking Mode"),
                    ("awaiting_speciality", "Awaiting Speciality"),
                    ("awaiting_doctor", "Awaiting Doctor"),
                    ("awaiting_clinic", "Awaiting Clinic"),
                    ("awaiting_clinic_doctor", "Awaiting Clinic Doctor"),
                    ("awaiting_date", "Awaiting Date"),
                    ("awaiting_slot", "Awaiting Slot"),
                    ("awaiting_confirm", "Awaiting Confirm"),
                    ("menu", "Menu"),
                ],
                default="idle",
                max_length=32,
            ),
        ),
    ]
