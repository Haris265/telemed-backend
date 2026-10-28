"""Parent multi-clinic playground: discovery, bind, switch, API."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from langchain_core.messages import AIMessage
from rest_framework.test import APIClient

from assistant.parent_engine import ParentInboundMessage, run_parent_turn
from assistant.parent_session import (
    clear_clinic_pending,
    load_parent_session,
    save_parent_session,
    select_clinic_on_parent,
)
from assistant.session_store import load_session, save_session, set_pending
from assistant.tests import factories as f
from assistant.tests.helpers import fake_redis_client
from assistant.tests.scripted_model import ScriptedChatModel
from assistant.tools.parent_discovery import build_parent_discovery_tools


class ParentDiscoveryToolTests(TestCase):
    def setUp(self):
        self.clinic_a = f.make_clinic(name="Alpha Heart")
        self.clinic_b = f.make_clinic(name="Beta Skin")
        self.clinic_off = f.make_clinic(name="Off Clinic")
        f.enable_assistant(self.clinic_a)
        f.enable_assistant(self.clinic_b)
        # clinic_off has no enabled assistant

    def test_list_clinics_only_eligible(self):
        parent = {
            "phone": "923001234567",
            "refs": [],
            "selected_clinic_id": None,
        }
        tools = {t.name: t for t in build_parent_discovery_tools(parent)}
        raw = tools["list_clinics"].invoke({})
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        names = {c["name"] for c in data["data"]["clinics"]}
        self.assertIn("Alpha Heart", names)
        self.assertIn("Beta Skin", names)
        self.assertNotIn("Off Clinic", names)
        self.assertEqual(len(parent["refs"]), 2)

    def test_select_clinic_by_name_and_switch_clear(self):
        parent = {
            "phone": "923001234567",
            "refs": [],
            "selected_clinic_id": None,
        }
        tools = {t.name: t for t in build_parent_discovery_tools(parent)}
        tools["list_clinics"].invoke({})
        raw = tools["select_clinic"].invoke({"clinic_ref": "Alpha"})
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        self.assertEqual(parent["selected_clinic_id"], self.clinic_a.id)

        with fake_redis_client():
            sess = load_session(self.clinic_a.id, parent["phone"])
            set_pending(sess, {"type": "booking", "doctor_id": 1})
            save_session(sess)

            raw2 = tools["switch_clinic"].invoke({"clinic_ref": "clear"})
            data2 = json.loads(raw2)
            self.assertTrue(data2["ok"])
            self.assertIsNone(parent["selected_clinic_id"])
            cleared = load_session(self.clinic_a.id, parent["phone"])
            self.assertIsNone(cleared.get("pending"))


class ParentEngineTests(TestCase):
    def setUp(self):
        self.clinic_a = f.make_clinic(name="Alpha Heart")
        self.clinic_b = f.make_clinic(name="Beta Skin")
        f.enable_assistant(self.clinic_a)
        f.enable_assistant(self.clinic_b)

    def test_unbound_lists_via_scripted_tool_then_reply(self):
        model = ScriptedChatModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "list_clinics",
                            "args": {},
                            "id": "tc1",
                        }
                    ],
                ),
                AIMessage(content="Here are the clinics you can choose from."),
            ]
        )
        with fake_redis_client():
            with patch("assistant.parent_engine.get_chat_model", return_value=model):
                result = run_parent_turn(
                    ParentInboundMessage(
                        phone="03001234567",
                        message_id="p1",
                        kind="text",
                        text="show clinics",
                    )
                )
        self.assertEqual(result.status, 200)
        self.assertIn("clinics", result.reply.lower())
        self.assertIsNone(result.selected_clinic_id)

    def test_select_then_bound_turn_uses_clinic_quota(self):
        select_model = ScriptedChatModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "select_clinic",
                            "args": {"clinic_ref": str(self.clinic_a.id)},
                            "id": "tc1",
                        }
                    ],
                ),
                AIMessage(content="Alpha Heart selected. How can I help?"),
            ]
        )
        bound_model = ScriptedChatModel(
            [AIMessage(content="We have Cardiology available.")]
        )
        with fake_redis_client():
            with patch(
                "assistant.parent_engine.get_chat_model", return_value=select_model
            ):
                first = run_parent_turn(
                    ParentInboundMessage(
                        phone="03001234567",
                        message_id="p2",
                        kind="text",
                        text="select alpha",
                    )
                )
            self.assertEqual(first.selected_clinic_id, self.clinic_a.id)
            self.assertEqual(first.quota, {})

            with patch(
                "assistant.parent_engine.get_chat_model", return_value=bound_model
            ):
                second = run_parent_turn(
                    ParentInboundMessage(
                        phone="03001234567",
                        message_id="p3",
                        kind="text",
                        text="what specialities?",
                    )
                )
            self.assertEqual(second.status, 200)
            self.assertEqual(second.selected_clinic_id, self.clinic_a.id)
            self.assertIn("clinic_text_used_today", second.quota)
            self.assertGreaterEqual(second.quota["clinic_text_used_today"], 1)

    def test_switch_clears_pending_on_previous_clinic(self):
        phone = "923001112233"
        with fake_redis_client():
            parent = load_parent_session(phone)
            select_clinic_on_parent(parent, self.clinic_a.id)
            save_parent_session(parent)
            sess = load_session(self.clinic_a.id, phone)
            set_pending(sess, {"type": "booking", "doctor_id": 9})
            save_session(sess)

            clear_clinic_pending(self.clinic_a.id, phone)
            after = load_session(self.clinic_a.id, phone)
            self.assertIsNone(after.get("pending"))


@override_settings(DEBUG=True, ASSISTANT_PLAYGROUND_ENABLED=True)
class ParentPlaygroundAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.clinic = f.make_clinic(name="API Clinic")
        f.enable_assistant(self.clinic)

    def test_parent_page_ok(self):
        res = self.client.get("/api/assistant/parent/playground/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Parent Clinic Assistant")

    def test_parent_chat_no_clinic_id_required(self):
        model = ScriptedChatModel([AIMessage(content="Welcome to the parent assistant.")])
        with fake_redis_client():
            with patch("assistant.parent_engine.get_chat_model", return_value=model):
                res = self.client.post(
                    "/api/assistant/parent/chat/",
                    {
                        "phone": "03001234567",
                        "message": "hello",
                        "message_id": "api1",
                    },
                    format="json",
                )
        self.assertEqual(res.status_code, 200)
        self.assertIn("Welcome", res.data["reply"])
        self.assertIn("selected_clinic_id", res.data)

    def test_clinic_playground_still_works(self):
        model = ScriptedChatModel([AIMessage(content="Clinic-only hello")])
        with fake_redis_client():
            with patch("assistant.engine.get_chat_model", return_value=model):
                res = self.client.post(
                    "/api/assistant/chat/",
                    {
                        "clinic_id": self.clinic.id,
                        "phone": "03001234567",
                        "message": "hello",
                        "message_id": "clinic-still",
                    },
                    format="json",
                )
        self.assertEqual(res.status_code, 200)
        self.assertIn("Clinic-only", res.data["reply"])

    def test_parent_reset(self):
        with fake_redis_client():
            parent = load_parent_session("923001234567")
            select_clinic_on_parent(parent, self.clinic.id)
            save_parent_session(parent)
            res = self.client.post(
                "/api/assistant/parent/reset/",
                {"phone": "03001234567"},
                format="json",
            )
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.data["ok"])
            again = load_parent_session("923001234567")
            self.assertIsNone(again.get("selected_clinic_id"))
