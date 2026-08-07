import logging
import mimetypes
from pathlib import Path
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MetaWhatsAppClient:
    def __init__(self):
        self.token = settings.META_WA_TOKEN
        self.phone_number_id = settings.META_WA_PHONE_NUMBER_ID
        self.graph_base = "https://graph.facebook.com/v21.0"
        self.base_url = f"{self.graph_base}/{self.phone_number_id}/messages"
        self.media_url = f"{self.graph_base}/{self.phone_number_id}/media"

    def get_display_phone_digits(self) -> str:
        """Return clinic WhatsApp digits (E.164 without +) from Meta phone number id."""
        if not self.token or not self.phone_number_id:
            return ""
        url = f"{self.graph_base}/{self.phone_number_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            resp = requests.get(
                url,
                headers=headers,
                params={"fields": "display_phone_number,verified_name"},
                timeout=15,
            )
            if not resp.ok:
                logger.error(
                    "Meta WA phone lookup failed (%s): %s",
                    resp.status_code,
                    resp.text[:500],
                )
                return ""
            display = (resp.json() or {}).get("display_phone_number") or ""
            return "".join(ch for ch in display if ch.isdigit())
        except Exception:
            logger.exception("Failed fetching Meta WA display phone")
            return ""

    def send_text(self, to: str, body: str) -> dict[str, Any]:
        if not self.token or not self.phone_number_id:
            logger.warning("Meta WA credentials missing; skipping send to %s: %s", to, body)
            return {"skipped": True, "to": to, "body": body}

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(self.base_url, json=payload, headers=headers, timeout=15)
            if not resp.ok:
                logger.error(
                    "Meta WA send failed (%s) to %s: %s",
                    resp.status_code,
                    to,
                    resp.text[:500],
                )
                resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception("Failed to send WhatsApp message to %s", to)
            return {"error": True, "to": to}

    def upload_media(self, file_path: str, mime_type: str = "") -> str | None:
        """Upload a local file to Meta and return media id."""
        if not self.token or not self.phone_number_id:
            logger.warning("Meta WA credentials missing; skipping media upload")
            return None
        path = Path(file_path)
        if not path.is_file():
            logger.error("Media file missing: %s", file_path)
            return None
        mime = mime_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            with path.open("rb") as fh:
                files = {
                    "file": (path.name, fh, mime),
                    "messaging_product": (None, "whatsapp"),
                    "type": (None, mime),
                }
                resp = requests.post(
                    self.media_url, headers=headers, files=files, timeout=60
                )
            if not resp.ok:
                logger.error(
                    "Meta WA media upload failed (%s): %s",
                    resp.status_code,
                    resp.text[:500],
                )
                return None
            media_id = (resp.json() or {}).get("id")
            return str(media_id) if media_id else None
        except Exception:
            logger.exception("Failed uploading WhatsApp media %s", file_path)
            return None

    def send_image(
        self,
        to: str,
        *,
        media_id: str | None = None,
        link: str | None = None,
        caption: str = "",
    ) -> dict[str, Any]:
        if not self.token or not self.phone_number_id:
            return {"skipped": True, "to": to}
        image: dict[str, Any] = {}
        if media_id:
            image["id"] = media_id
        elif link:
            image["link"] = link
        else:
            return {"error": True, "detail": "media_id or link required"}
        if caption:
            image["caption"] = caption[:1024]
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": image,
        }
        return self._post_message(to, payload)

    def send_audio(
        self,
        to: str,
        *,
        media_id: str | None = None,
        link: str | None = None,
    ) -> dict[str, Any]:
        if not self.token or not self.phone_number_id:
            return {"skipped": True, "to": to}
        audio: dict[str, Any] = {}
        if media_id:
            audio["id"] = media_id
        elif link:
            audio["link"] = link
        else:
            return {"error": True, "detail": "media_id or link required"}
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "audio",
            "audio": audio,
        }
        return self._post_message(to, payload)

    def _post_message(self, to: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(self.base_url, json=payload, headers=headers, timeout=30)
            if not resp.ok:
                logger.error(
                    "Meta WA media send failed (%s) to %s: %s",
                    resp.status_code,
                    to,
                    resp.text[:500],
                )
                return {"error": True, "to": to, "status": resp.status_code}
            return resp.json()
        except Exception:
            logger.exception("Failed to send WhatsApp media message to %s", to)
            return {"error": True, "to": to}
