from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Create default admin user if missing"

    def handle(self, *args, **options):
        email = "admin@telemed.local"
        username = "admin"
        password = "admin123"

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "first_name": "Clinic",
                "last_name": "Admin",
            },
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created admin: {username} / {password}"))
        else:
            if user.role != User.Role.ADMIN:
                user.role = User.Role.ADMIN
                user.save(update_fields=["role"])
            self.stdout.write(self.style.WARNING(f"Admin already exists: {username}"))
