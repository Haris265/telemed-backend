"""Quiet expected request/engine noise when running assistant.tests."""

from __future__ import annotations

import logging

for _name in ("django.request", "django.server", "assistant.engine"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)
