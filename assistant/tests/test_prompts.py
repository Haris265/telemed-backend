"""Unit tests for assistant prompt policy and language heuristic."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from assistant.context import ClinicContext
from assistant.prompts import (
    _ROMAN_URDU_TOKENS,
    _policy,
    build_system_prompt,
    detect_reply_language,
)
from assistant.tests.factories import enable_assistant, make_clinic


class DetectReplyLanguageTests(SimpleTestCase):
    def test_roman_urdu_sample(self):
        self.assertEqual(
            detect_reply_language(
                "Assalam o alaikum, dentist ke bare mein batao"
            ),
            "roman_urdu",
        )

    def test_english_sample(self):
        self.assertEqual(
            detect_reply_language("Hi, tell me about the dentist"),
            "english",
        )

    def test_empty_defaults_english(self):
        self.assertEqual(detect_reply_language(""), "english")
        self.assertEqual(detect_reply_language("   "), "english")


class PolicyTextTests(SimpleTestCase):
    def test_policy_has_language_and_answer_focus_rules(self):
        text = _policy("Test Clinic", "0211111111")
        self.assertIn("Language (hard rule)", text)
        self.assertIn("Roman Urdu", text)
        self.assertIn("Answer focus", text)
        self.assertIn("Match the latest patient message", text)
        self.assertNotIn("Mirror the patient's language", text)

    def test_policy_has_booking_honesty_rules(self):
        text = _policy("Test Clinic", "0211111111")
        self.assertIn("One active appointment", text)
        self.assertIn("Ask before scheduling", text)
        self.assertIn("Exact times only", text)
        self.assertIn("No invented booking state", text)
        self.assertIn("one consultation fee", text)

    def test_policy_has_roman_urdu_and_date_phrasing_rules(self):
        text = _policy("Test Clinic", "0211111111")
        self.assertIn("Pakistani Roman Urdu", text)
        self.assertIn("sambandit", text)
        self.assertIn("Patient-facing dates", text)
        self.assertIn("Never show bare YYYY-MM-DD", text)
        self.assertIn("weekday", text)
        self.assertIn("date_label", text)
        self.assertIn("tool calls only", text)

    def test_roman_urdu_tokens_not_extended(self):
        self.assertIn("hai", _ROMAN_URDU_TOKENS)
        self.assertNotIn("khidmat", _ROMAN_URDU_TOKENS)
        self.assertNotIn("duphare", _ROMAN_URDU_TOKENS)


class BuildSystemPromptLanguageHintTests(TestCase):
    def test_appends_roman_urdu_hint(self):
        clinic = make_clinic("Hint Clinic")
        config = enable_assistant(clinic)
        ctx = ClinicContext(
            clinic=clinic,
            config=config,
            plan=config.plan,
            phone="923001111111",
        )
        prompt = build_system_prompt(
            ctx,
            {},
            latest_user_text="Assalam o alaikum, dentist ke bare mein batao",
        )
        self.assertIn("Reply language for this turn: Roman Urdu", prompt)
        self.assertIn("Language (hard rule)", prompt)
        self.assertIn("Answer focus", prompt)

    def test_appends_english_hint(self):
        clinic = make_clinic("Hint Clinic EN")
        config = enable_assistant(clinic)
        ctx = ClinicContext(
            clinic=clinic,
            config=config,
            plan=config.plan,
            phone="923001111112",
        )
        prompt = build_system_prompt(
            ctx,
            {},
            latest_user_text="Hi, tell me about the dentist",
        )
        self.assertIn("Reply language for this turn: English", prompt)
