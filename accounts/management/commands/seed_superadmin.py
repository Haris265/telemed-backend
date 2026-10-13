from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Create default superadmin user if missing"

    def handle(self, *args, **options):
        email = "superadmin@telemed.local"
        username = "superadmin"
        password = "superadmin123"

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "role": User.Role.SUPERADMIN,
                "is_staff": True,
                "is_superuser": True,
                "first_name": "Platform",
                "last_name": "Superadmin",
            },
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"Created superadmin: {username} / {password}")
            )
        else:
            if user.role != User.Role.SUPERADMIN:
                user.role = User.Role.SUPERADMIN
                user.save(update_fields=["role"])
            self.stdout.write(self.style.WARNING(f"Superadmin already exists: {username}"))
