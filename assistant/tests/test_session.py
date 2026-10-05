from unittest.mock import patch

from django.test import TestCase

from assistant import session_store as store
from assistant.tests.helpers import fake_redis_client


class SessionStoreTests(TestCase):
    def test_append_and_compaction(self):
        with fake_redis_client():
            session = store.new_session(1, "923001234567")
            for i in range(16):
                store.append_message(session, "user", f"u{i}")
                store.append_message(session, "assistant", f"a{i}")
            # 32 messages; force compact like engine does when > 15
            self.assertTrue(len(session["messages"]) > 15)
            with patch(
                "assistant.summarizer.summarize_messages",
                return_value="summary text",
            ):
                from assistant.summarizer import summarize_messages
                from assistant import settings_access as sa

                keep = sa.keep_after_compact()
                older = session["messages"][:-keep]
                summary = summarize_messages("", older)
                store.compact_messages(session, summary)
            self.assertEqual(session["summary"], "summary text")
            self.assertEqual(len(session["messages"]), 6)

    def test_pending_survives_compaction(self):
        with fake_redis_client():
            session = store.new_session(1, "923001234567")
            store.set_pending(
                session,
                {"type": "booking", "doctor_id": 1, "prepared_at_turn": 1},
            )
            for i in range(20):
                store.append_message(session, "user", f"m{i}")
            store.compact_messages(session, "x")
            self.assertEqual(session["pending"]["type"], "booking")

    def test_load_save_roundtrip(self):
        with fake_redis_client():
            session = store.new_session(5, "923001234567", patient_name="Ali")
            store.append_message(session, "user", "hello")
            store.save_session(session)
            loaded = store.load_session(5, "923001234567")
            self.assertEqual(loaded["patient_name"], "Ali")
            self.assertEqual(len(loaded["messages"]), 1)
