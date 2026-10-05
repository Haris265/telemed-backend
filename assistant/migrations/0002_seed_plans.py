from django.db import migrations


def seed_plans(apps, schema_editor):
    AssistantPlan = apps.get_model("assistant", "AssistantPlan")
    defaults = [
        {
            "code": "A",
            "name": "Starter",
            "max_bot_replies_per_patient_month": 10,
            "max_text_messages_per_day": 60,
            "max_voice_notes_per_day": 15,
            "is_active": True,
        },
        {
            "code": "B",
            "name": "Standard",
            "max_bot_replies_per_patient_month": 20,
            "max_text_messages_per_day": 150,
            "max_voice_notes_per_day": 40,
            "is_active": True,
        },
        {
            "code": "C",
            "name": "Premium",
            "max_bot_replies_per_patient_month": 30,
            "max_text_messages_per_day": 400,
            "max_voice_notes_per_day": 100,
            "is_active": True,
        },
    ]
    for row in defaults:
        code = row["code"]
        payload = {k: v for k, v in row.items() if k != "code"}
        AssistantPlan.objects.update_or_create(code=code, defaults=payload)


def unseed_plans(apps, schema_editor):
    AssistantPlan = apps.get_model("assistant", "AssistantPlan")
    AssistantPlan.objects.filter(code__in=["A", "B", "C"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("assistant", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_plans, unseed_plans),
    ]
