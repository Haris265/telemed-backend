from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import DoctorProfile, Speciality

User = get_user_model()

SPECIALITIES = [
    "General Physician",
    "Cardiologist",
    "Dermatologist",
    "Pediatrician",
    "Gynecologist",
    "Orthopedic",
    "ENT Specialist",
    "Neurologist",
    "Psychiatrist",
    "Dentist",
]

DOCTORS = [
    {
        "first_name": "Ahmed",
        "last_name": "Khan",
        "email": "ahmed.khan@telemed.local",
        "specialities": ["General Physician", "Cardiologist"],
        "session_time": 20,
    },
    {
        "first_name": "Sara",
        "last_name": "Malik",
        "email": "sara.malik@telemed.local",
        "specialities": ["Dermatologist"],
        "session_time": 15,
    },
    {
        "first_name": "Hassan",
        "last_name": "Raza",
        "email": "hassan.raza@telemed.local",
        "specialities": ["Pediatrician"],
        "session_time": 15,
    },
    {
        "first_name": "Ayesha",
        "last_name": "Siddiqui",
        "email": "ayesha.siddiqui@telemed.local",
        "specialities": ["Gynecologist"],
        "session_time": 20,
    },
    {
        "first_name": "Bilal",
        "last_name": "Ahmed",
        "email": "bilal.ahmed@telemed.local",
        "specialities": ["Orthopedic", "General Physician"],
        "session_time": 20,
    },
    {
        "first_name": "Fatima",
        "last_name": "Noor",
        "email": "fatima.noor@telemed.local",
        "specialities": ["ENT Specialist"],
        "session_time": 15,
    },
    {
        "first_name": "Imran",
        "last_name": "Shah",
        "email": "imran.shah@telemed.local",
        "specialities": ["Neurologist"],
        "session_time": 30,
    },
    {
        "first_name": "Zainab",
        "last_name": "Ali",
        "email": "zainab.ali@telemed.local",
        "specialities": ["Psychiatrist"],
        "session_time": 45,
    },
]

DEFAULT_PASSWORD = "doctor123"


class Command(BaseCommand):
    help = "Seed specialities and sample doctors"

    @transaction.atomic
    def handle(self, *args, **options):
        speciality_map = {}
        created_specs = 0
        for name in SPECIALITIES:
            obj, created = Speciality.objects.get_or_create(
                name=name,
                defaults={"is_active": True},
            )
            speciality_map[name] = obj
            if created:
                created_specs += 1
                self.stdout.write(self.style.SUCCESS(f"Speciality: {name}"))
            else:
                self.stdout.write(self.style.WARNING(f"Speciality exists: {name}"))

        created_docs = 0
        for data in DOCTORS:
            email = data["email"].lower()
            if User.objects.filter(email__iexact=email).exists():
                self.stdout.write(self.style.WARNING(f"Doctor exists: {email}"))
                continue

            user = User.objects.create_user(
                username=email,
                email=email,
                password=DEFAULT_PASSWORD,
                role=User.Role.DOCTOR,
                first_name=data["first_name"],
                last_name=data["last_name"],
            )
            doctor = DoctorProfile.objects.create(
                user=user,
                first_name=data["first_name"],
                last_name=data["last_name"],
                session_time=data["session_time"],
                is_active=True,
            )
            specs = [speciality_map[n] for n in data["specialities"]]
            doctor.specialities.set(specs)
            created_docs += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Doctor: Dr. {doctor.full_name} ({email}) / {DEFAULT_PASSWORD}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Specialities created: {created_specs}, Doctors created: {created_docs}"
            )
        )
