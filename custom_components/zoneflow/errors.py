"""One place for the translated errors ZoneFlow's services raise."""
from __future__ import annotations

from typing import Any

from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN


def service_error(key: str, **placeholders: Any) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders or None)
