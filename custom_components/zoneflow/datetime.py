"""Read/write "when did this last happen" entities.

Their main purpose is setup-time seeding: a brand-new zone starts with no
watering history at all, which (correctly) makes it look overdue and fire
on the very next scheduled time. For an already-established plant that's
been getting watered some other way until now, that's not what you want.
Setting these three lets you tell ZoneFlow "it was already deep-soaked 5
days ago" / "it rained heavily 2 days ago" etc. so the interval/dry-down
math starts from reality instead of a blank slate -- no need to actually
run a cycle just to seed the state. They're just as useful later on too,
e.g. correcting after a manual watering ZoneFlow didn't do itself.

These are thin views over ZoneFlowController's persisted state, not a
separate store of their own -- IrrigationStateStore is already the single
source of truth, and it's loaded (controller.async_setup()) before this
platform is set up (see __init__.async_setup_entry), so reading it here at
construction time is safe.
"""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from .const import DOMAIN

# (state field on IrrigationState, display name)
LAST_EVENT_FIELDS: list[tuple[str, str]] = [
    ("last_routine_ts", "Last Routine Irrigation"),
    ("last_deep_soak_ts", "Last Deep Soak"),
    ("last_significant_rain_ts", "Last Significant Rain"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ZoneFlowLastEventDateTime(entry, controller, field, name) for field, name in LAST_EVENT_FIELDS
    )


class ZoneFlowLastEventDateTime(DateTimeEntity):
    """Set at setup to seed history for an already-established plant, or any
    time after to correct it. Left unset ("unknown"), the matching gate
    behaves exactly as if it's never happened -- which is the honest,
    correct default for a genuinely brand-new setup."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, entry: ConfigEntry, controller, state_field: str, name: str) -> None:
        self._controller = controller
        self._state_field = state_field
        self._attr_unique_id = f"{entry.entry_id}_{state_field}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)

    @property
    def native_value(self) -> datetime | None:
        ts = getattr(self._controller.store.state, self._state_field)
        return dt_util.utc_from_timestamp(ts) if ts is not None else None

    async def async_set_value(self, value: datetime) -> None:
        setattr(self._controller.store.state, self._state_field, dt_util.as_utc(value).timestamp())
        await self._controller.store.async_save()
        self.async_write_ha_state()
