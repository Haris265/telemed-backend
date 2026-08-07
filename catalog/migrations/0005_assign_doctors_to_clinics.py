from django.db import migrations


def assign_doctors_to_clinics(apps, schema_editor):
    Clinic = apps.get_model("catalog", "Clinic")
    DoctorProfile = apps.get_model("catalog", "DoctorProfile")
    clinics = list(Clinic.objects.filter(is_active=True).order_by("id"))
    if not clinics:
        return
    doctors = list(
        DoctorProfile.objects.filter(is_active=True, clinic__isnull=True).order_by("id")
    )
    for index, doctor in enumerate(doctors):
        doctor.clinic_id = clinics[index % len(clinics)].id
        doctor.save(update_fields=["clinic_id"])


def clear_doctor_clinics(apps, schema_editor):
    DoctorProfile = apps.get_model("catalog", "DoctorProfile")
    DoctorProfile.objects.filter(clinic__isnull=False).update(clinic=None)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_clinic_and_doctor_clinic"),
    ]

    operations = [
        migrations.RunPython(assign_doctors_to_clinics, clear_doctor_clinics),
    ]
