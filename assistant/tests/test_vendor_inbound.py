"""Vendor inbound /ai-reply contract tests — engines mocked; assistants unchanged."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from assistant.context import TurnResult
from assistant.tests import factories as f
from assistant.tests.helpers import fake_redis_client
from assistant.vendor.normalize import normalize_incoming_messages, parse_clinic_id
from assistant.vendor.signature import SignatureError, verify_gateway_signature

PARENT_SECRET = "whsec_test_parent_secret"
CLINIC_SECRET = "whsec_test_clinic_secret"


def _sign(secret: str, raw: bytes, ts: int | None = None) -> tuple[int, str]:
    timestamp = int(time.time()) if ts is None else ts
    sig = hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + raw,
        hashlib.sha256,
    ).hexdigest()
    return timestamp, f"v1={sig}"


def _post(client: Client, path: str, body: dict, secret: str, *, ts: int | None = None):
    raw = json.dumps(body, separators=(",", ":")).encode()
    timestamp, signature = _sign(secret, raw, ts=ts)
    return client.post(
        path,
        data=raw,
        content_type="application/json",
        HTTP_X_GATEWAY_TIMESTAMP=str(timestamp),
        HTTP_X_GATEWAY_SIGNATURE=signature,
        HTTP_X_REQUEST_ID=body.get("requestId", "req-1"),
        HTTP_X_CONTRACT_VERSION="1",
    )


@override_settings(
    VENDOR_PARENT_BOT_SECRET=PARENT_SECRET,
    VENDOR_CLINIC_BOT_SECRET=CLINIC_SECRET,
    VENDOR_PARENT_BOT_SECRET_OLD="",
    VENDOR_CLINIC_BOT_SECRET_OLD="",
)
class VendorSignatureHelperTests(TestCase):
    def test_valid_signature(self):
        raw = b'{"a":1}'
        ts, header = _sign(PARENT_SECRET, raw)
        verify_gateway_signature(
            [PARENT_SECRET],
            timestamp_header=str(ts),
            signature_header=header,
            raw_body=raw,
        )

    def test_bad_signature(self):
        raw = b'{"a":1}'
        ts, _ = _sign(PARENT_SECRET, raw)
        with self.assertRaises(SignatureError):
            verify_gateway_signature(
                [PARENT_SECRET],
                timestamp_header=str(ts),
                signature_header="v1=deadbeef",
                raw_body=raw,
            )

    def test_stale_timestamp(self):
        raw = b'{"a":1}'
        ts, header = _sign(PARENT_SECRET, raw, ts=int(time.time()) - 400)
        with self.assertRaises(SignatureError):
            verify_gateway_signature(
                [PARENT_SECRET],
                timestamp_header=str(ts),
                signature_header=header,
                raw_body=raw,
            )


class VendorNormalizeTests(TestCase):
    def test_combine_three_texts(self):
        n = normalize_incoming_messages(
            [
                {"text": "Hi", "timestamp": "19:30:01", "media": None},
                {"text": "Cardiologist", "timestamp": "19:30:04", "media": None},
                {"text": "Please", "timestamp": "19:30:06", "media": None},
            ]
        )
        self.assertEqual(n.text, "Hi\nCardiologist\nPlease")
        self.assertIsNone(n.short_circuit_replies)

    def test_large_file_short_circuit(self):
        n = normalize_incoming_messages(
            [
                {
                    "text": "",
                    "timestamp": "19:45:00",
                    "media": {
                        "hasMedia": True,
                        "mediaType": "document",
                        "base64Data": None,
                        "skippedLargeFile": True,
                    },
                }
            ]
        )
        self.assertTrue(n.short_circuit_replies)
        self.assertIn("bari", n.short_circuit_replies[0].lower())

    def test_parse_clinic_id(self):
        self.assertEqual(parse_clinic_id({"clinicId": 9}), 9)
        self.assertEqual(parse_clinic_id({"clinicId": "5"}), 5)
        self.assertIsNone(parse_clinic_id({}))
        self.assertIsNone(parse_clinic_id({"clinic_id": 9}))


@override_settings(
    VENDOR_PARENT_BOT_SECRET=PARENT_SECRET,
    VENDOR_CLINIC_BOT_SECRET=CLINIC_SECRET,
    VENDOR_PARENT_BOT_SECRET_OLD="",
    VENDOR_CLINIC_BOT_SECRET_OLD="",
)
class VendorInboundAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.clinic = f.make_clinic(name="Vendor Clinic")
        f.enable_assistant(self.clinic)
        self.other = f.make_clinic(name="Other Clinic")
        f.enable_assistant(self.other)

    def _parent_body(self, **overrides):
        body = {
            "contractVersion": 1,
            "requestId": "parent-req-1",
            "chatId": "923001234567@c.us",
            "chatTitle": "Sara",
            "senderName": "Sara",
            "senderNumber": "+923001234567",
            "isSaved": False,
            "incomingMessages": [
                {"text": "Karachi dentist", "timestamp": "19:30:12", "media": None}
            ],
            "chatHistory": [],
            "vendorContext": {},
        }
        body.update(overrides)
        return body

    def _clinic_body(self, **overrides):
        body = {
            "contractVersion": 1,
            "requestId": "clinic-req-1",
            "chatId": "923001234567@c.us",
            "chatTitle": "Sara",
            "senderName": "Sara",
            "senderNumber": "+923001234567",
            "isSaved": False,
            "incomingMessages": [
                {"text": "Hi", "timestamp": "19:30:01", "media": None},
                {"text": "Cardiologist chahiye", "timestamp": "19:30:04", "media": None},
            ],
            "chatHistory": [],
            "vendorContext": {"clinicId": self.clinic.id},
        }
        body.update(overrides)
        return body

    def test_signed_parent_returns_replies(self):
        with fake_redis_client():
            with patch(
                "assistant.vendor.views.run_parent_turn",
                return_value=TurnResult(reply="Parent hello", outcome="ok"),
            ) as mock_run:
                res = _post(
                    self.client,
                    "/api/vendor/parent/ai-reply/",
                    self._parent_body(),
                    PARENT_SECRET,
                )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["replies"], ["Parent hello"])
        mock_run.assert_called_once()
        inbound = mock_run.call_args.args[0]
        self.assertEqual(inbound.text, "Karachi dentist")

    def test_parent_accepts_path_without_trailing_slash(self):
        """Vendor often omits trailing slash; must not APPEND_SLASH 500."""
        with fake_redis_client():
            with patch(
                "assistant.vendor.views.run_parent_turn",
                return_value=TurnResult(reply="noslash ok", outcome="ok"),
            ):
                res = _post(
                    self.client,
                    "/api/vendor/parent/ai-reply",
                    self._parent_body(requestId="noslash-1"),
                    PARENT_SECRET,
                )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["replies"], ["noslash ok"])

    def test_signed_clinic_uses_clinic_id(self):
        with fake_redis_client():
            with patch(
                "assistant.vendor.views.run_turn",
                return_value=TurnResult(reply="Clinic hello", outcome="ok"),
            ) as mock_run:
                res = _post(
                    self.client,
                    "/api/vendor/clinic/ai-reply/",
                    self._clinic_body(),
                    CLINIC_SECRET,
                )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["replies"], ["Clinic hello"])
        inbound = mock_run.call_args.args[0]
        self.assertEqual(inbound.clinic_id, self.clinic.id)
        self.assertEqual(inbound.text, "Hi\nCardiologist chahiye")

    def test_wrong_signature_401(self):
        with fake_redis_client():
            res = _post(
                self.client,
                "/api/vendor/clinic/ai-reply/",
                self._clinic_body(),
                "whsec_wrong",
            )
        self.assertEqual(res.status_code, 401)

    def test_stale_timestamp_401(self):
        with fake_redis_client():
            res = _post(
                self.client,
                "/api/vendor/parent/ai-reply/",
                self._parent_body(),
                PARENT_SECRET,
                ts=int(time.time()) - 400,
            )
        self.assertEqual(res.status_code, 401)

    def test_crossed_secret_401(self):
        """Parent secret must not unlock clinic URL."""
        with fake_redis_client():
            res = _post(
                self.client,
                "/api/vendor/clinic/ai-reply/",
                self._clinic_body(),
                PARENT_SECRET,
            )
        self.assertEqual(res.status_code, 401)

    def test_clinic_missing_context_400(self):
        with fake_redis_client():
            res = _post(
                self.client,
                "/api/vendor/clinic/ai-reply/",
                self._clinic_body(vendorContext={}),
                CLINIC_SECRET,
            )
        self.assertEqual(res.status_code, 400)

    def test_clinic_wrong_key_name_400(self):
        with fake_redis_client():
            res = _post(
                self.client,
                "/api/vendor/clinic/ai-reply/",
                self._clinic_body(vendorContext={"clinic_id": self.clinic.id}),
                CLINIC_SECRET,
            )
        self.assertEqual(res.status_code, 400)

    def test_three_messages_one_engine_call(self):
        body = self._clinic_body(
            incomingMessages=[
                {"text": "A", "timestamp": "1", "media": None},
                {"text": "B", "timestamp": "2", "media": None},
                {"text": "C", "timestamp": "3", "media": None},
            ]
        )
        with fake_redis_client():
            with patch(
                "assistant.vendor.views.run_turn",
                return_value=TurnResult(reply="ok", outcome="ok"),
            ) as mock_run:
                res = _post(
                    self.client,
                    "/api/vendor/clinic/ai-reply/",
                    body,
                    CLINIC_SECRET,
                )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_run.call_count, 1)
        self.assertEqual(mock_run.call_args.args[0].text, "A\nB\nC")

    def test_large_file_no_engine(self):
        body = self._clinic_body(
            incomingMessages=[
                {
                    "text": "",
                    "timestamp": "19:45:00",
                    "media": {
                        "hasMedia": True,
                        "mediaType": "document",
                        "base64Data": None,
                        "skippedLargeFile": True,
                    },
                }
            ]
        )
        with fake_redis_client():
            with patch("assistant.vendor.views.run_turn") as mock_run:
                res = _post(
                    self.client,
                    "/api/vendor/clinic/ai-reply/",
                    body,
                    CLINIC_SECRET,
                )
        self.assertEqual(res.status_code, 200)
        mock_run.assert_not_called()
        self.assertTrue(res.json()["replies"])

    def test_request_id_cache_second_call_skips_engine(self):
        with fake_redis_client():
            with patch(
                "assistant.vendor.views.run_turn",
                return_value=TurnResult(reply="first", outcome="ok"),
            ) as mock_run:
                r1 = _post(
                    self.client,
                    "/api/vendor/clinic/ai-reply/",
                    self._clinic_body(requestId="same-id"),
                    CLINIC_SECRET,
                )
                r2 = _post(
                    self.client,
                    "/api/vendor/clinic/ai-reply/",
                    self._clinic_body(requestId="same-id"),
                    CLINIC_SECRET,
                )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()["replies"], r2.json()["replies"])
        self.assertEqual(mock_run.call_count, 1)

    def test_parent_ignores_clinic_id_in_context(self):
        with fake_redis_client():
            with patch(
                "assistant.vendor.views.run_parent_turn",
                return_value=TurnResult(reply="parent", outcome="ok"),
            ) as mock_parent:
                with patch("assistant.vendor.views.run_turn") as mock_clinic:
                    res = _post(
                        self.client,
                        "/api/vendor/parent/ai-reply/",
                        self._parent_body(vendorContext={"clinicId": self.clinic.id}),
                        PARENT_SECRET,
                    )
        self.assertEqual(res.status_code, 200)
        mock_parent.assert_called_once()
        mock_clinic.assert_not_called()

    def test_notice_becomes_extra_bubble(self):
        with fake_redis_client():
            with patch(
                "assistant.vendor.views.run_turn",
                return_value=TurnResult(
                    reply="Hello", notice="Quota notice", outcome="ok"
                ),
            ):
                res = _post(
                    self.client,
                    "/api/vendor/clinic/ai-reply/",
                    self._clinic_body(),
                    CLINIC_SECRET,
                )
        self.assertEqual(res.json()["replies"], ["Quota notice", "Hello"])
