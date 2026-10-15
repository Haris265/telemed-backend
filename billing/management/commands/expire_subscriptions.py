from django.core.management.base import BaseCommand

from billing.services import expire_subscriptions


class Command(BaseCommand):
    help = "Mark past-due ACTIVE clinic subscriptions as EXPIRED"

    def handle(self, *args, **options):
        count = expire_subscriptions()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} subscription(s)."))
