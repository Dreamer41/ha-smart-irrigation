"""Looking up a zone's device in the device registry."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry

from .const import DOMAIN


def zone_device(registry: DeviceRegistry, entry_id: str) -> DeviceEntry | None:
    """The device a zone's (or area's) config entry made.

    Newer Home Assistant wants the lookup to name the config entry, because a
    device identifier is only unique within one; older ones only have the plain
    lookup, which is fine here (the identifier is the entry's own id)."""
    by_entry = getattr(registry, "async_get_device_by_identifier", None)
    if by_entry is not None:
        return by_entry((DOMAIN, entry_id), entry_id)
    return registry.async_get_device(identifiers={(DOMAIN, entry_id)})
