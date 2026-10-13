from decimal import Decimal

from django.core.management.base import BaseCommand

from billing.models import Package


class Command(BaseCommand):
    help = "Seed sample clinic packages if missing"

    def handle(self, *args, **options):
        samples = [
            {
                "name": "Starter",
                "code": "starter",
                "description": "Small clinics — up to 3 doctors.",
                "price": Decimal("5000.00"),
                "duration_days": 30,
                "max_doctors": 3,
                "max_patients": 200,
                "features": {"whatsapp": False, "reports": True},
            },
            {
                "name": "Growth",
                "code": "growth",
                "description": "Growing clinics — up to 10 doctors.",
                "price": Decimal("12000.00"),
                "duration_days": 30,
                "max_doctors": 10,
                "max_patients": 1000,
                "features": {"whatsapp": True, "reports": True},
            },
            {
                "name": "Enterprise",
                "code": "enterprise",
                "description": "Large networks — unlimited scale.",
                "price": Decimal("25000.00"),
                "duration_days": 30,
                "max_doctors": 50,
                "max_patients": 10000,
                "features": {"whatsapp": True, "reports": True, "priority_support": True},
            },
        ]
        for sample in samples:
            obj, created = Package.objects.get_or_create(
                code=sample["code"],
                defaults=sample,
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created package: {obj.code}"))
            else:
                self.stdout.write(self.style.WARNING(f"Package exists: {obj.code}"))
