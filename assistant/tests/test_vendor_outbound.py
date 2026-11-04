"""Vendor outbound send-only client tests (no status poll)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from assistant.vendor.outbound import VendorOutboundError, send_vendor_message


@override_settings(
    VENDOR_GATEWAY_BASE_URL="https://vendor.test.example",
    VENDOR_PARENT_API_KEY="wab_test_parent",
    VENDOR_CLINIC_API_KEY="wab_test_clinic",
)
class VendorOutboundSendTests(SimpleTestCase):
    def test_parent_key_and_body(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "success": True,
            "jobId": "job_1",
            "status": "queued",
            "channelOnline": True,
        }
        with patch("assistant.vendor.outbound.requests.post", return_value=mock_resp) as post:
            result = send_vendor_message(
                channel="parent",
                number="03486102017",
                message="Hello",
                type="transactional",
            )
        self.assertEqual(result["jobId"], "job_1")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://vendor.test.example/v1/message-to-customer")
        self.assertEqual(kwargs["headers"]["X-API-Key"], "wab_test_parent")
        self.assertEqual(kwargs["json"]["number"], "03486102017")
        self.assertEqual(kwargs["json"]["message"], "Hello")
        self.assertEqual(kwargs["json"]["type"], "transactional")
        self.assertNotIn("Idempotency-Key", kwargs["headers"])

    def test_clinic_key(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {"jobId": "job_2", "status": "queued"}
        with patch("assistant.vendor.outbound.requests.post", return_value=mock_resp) as post:
            send_vendor_message(
                channel="clinic",
                number="923001234567",
                message="Clinic note",
            )
        self.assertEqual(
            post.call_args.kwargs["headers"]["X-API-Key"], "wab_test_clinic"
        )

    def test_otp_requires_idempotency_key(self):
        with patch("assistant.vendor.outbound.requests.post") as post:
            with self.assertRaises(VendorOutboundError):
                send_vendor_message(
                    channel="parent",
                    number="03486102017",
                    message="OTP 123",
                    type="otp",
                )
        post.assert_not_called()

    def test_otp_with_idempotency(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {"jobId": "job_otp", "status": "queued"}
        with patch("assistant.vendor.outbound.requests.post", return_value=mock_resp) as post:
            send_vendor_message(
                channel="parent",
                number="03486102017",
                message="OTP 482913",
                type="otp",
                ttl_seconds=300,
                idempotency_key="otp-order-9981",
            )
        headers = post.call_args.kwargs["headers"]
        body = post.call_args.kwargs["json"]
        self.assertEqual(headers["Idempotency-Key"], "otp-order-9981")
        self.assertEqual(body["ttlSeconds"], 300)
        self.assertEqual(body["type"], "otp")

    def test_http_error_mapped(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {
            "error": {"code": "INVALID_KEY", "message": "bad"}
        }
        with patch("assistant.vendor.outbound.requests.post", return_value=mock_resp):
            with self.assertRaises(VendorOutboundError) as ctx:
                send_vendor_message(
                    channel="parent",
                    number="03486102017",
                    message="Hi",
                )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_missing_gateway_url(self):
        with override_settings(VENDOR_GATEWAY_BASE_URL=""):
            with self.assertRaises(VendorOutboundError):
                send_vendor_message(
                    channel="parent",
                    number="03486102017",
                    message="Hi",
                )

    def test_no_get_status_call(self):
        """Send-only: requests.get must never be used by this helper."""
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {"jobId": "job_x", "status": "queued"}
        with patch("assistant.vendor.outbound.requests.post", return_value=mock_resp):
            with patch("assistant.vendor.outbound.requests.get") as get:
                send_vendor_message(
                    channel="parent",
                    number="03486102017",
                    message="Hi",
                )
                get.assert_not_called()
