"""Raise AssistantPlan caps for local / playground testing."""

from django.core.management.base import BaseCommand

from assistant.models import AssistantPlan

# High caps so playground testing is not blocked by Plan A (10/month).
TEST_CAPS = {
    "max_bot_replies_per_patient_month": 500,
    "max_text_messages_per_day": 500,
    "max_voice_notes_per_day": 100,
}


class Command(BaseCommand):
    help = "Raise Plan A/B/C quotas to testing levels (500 patient replies / month)."

    def handle(self, *args, **options):
        plans = AssistantPlan.objects.filter(code__in=["A", "B", "C"]).order_by("code")
        if not plans.exists():
            self.stderr.write(self.style.ERROR("No AssistantPlan rows found (A/B/C)."))
            return

        for plan in plans:
            before = (
                f"patient={plan.max_bot_replies_per_patient_month} "
                f"text_day={plan.max_text_messages_per_day} "
                f"voice_day={plan.max_voice_notes_per_day}"
            )
            for field, value in TEST_CAPS.items():
                setattr(plan, field, value)
            plan.save(update_fields=list(TEST_CAPS.keys()))
            after = (
                f"patient={plan.max_bot_replies_per_patient_month} "
                f"text_day={plan.max_text_messages_per_day} "
                f"voice_day={plan.max_voice_notes_per_day}"
            )
            self.stdout.write(
                self.style.SUCCESS(f"Plan {plan.code}: {before} → {after}")
            )

        self.stdout.write(self.style.SUCCESS("Done. Refresh playground to see new max."))
