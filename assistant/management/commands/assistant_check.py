from django.core.management.base import BaseCommand

from assistant.models import ClinicAssistantConfig
from assistant.redis_client import ping_redis
from assistant import settings_access as sa


class Command(BaseCommand):
    help = "Smoke-check assistant Redis, LLM key, and enabled clinic configs."

    def handle(self, *args, **options):
        ok = True

        if ping_redis():
            self.stdout.write(self.style.SUCCESS(f"Redis OK ({sa.redis_url()})"))
        else:
            ok = False
            self.stdout.write(self.style.ERROR(f"Redis FAIL ({sa.redis_url()})"))

        if sa.llm_api_key():
            self.stdout.write(
                self.style.SUCCESS(
                    f"LLM key present (provider={sa.llm_provider()}, model={sa.llm_model()})"
                )
            )
        else:
            ok = False
            self.stdout.write(self.style.WARNING("CHATBOT_LLM_API_KEY is empty"))

        enabled = ClinicAssistantConfig.objects.filter(is_enabled=True).count()
        self.stdout.write(f"Enabled clinic configs: {enabled}")

        if ok:
            self.stdout.write(self.style.SUCCESS("assistant_check passed"))
        else:
            self.stdout.write(self.style.WARNING("assistant_check completed with warnings"))
