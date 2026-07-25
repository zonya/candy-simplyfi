"""Sensors for Candy Simply-Fi (Cloud) — read-only statistics."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_APPLIANCE_ID,
    CONF_APPLIANCE_NAME,
    DOMAIN,
    MACHINE_STATE,
    PROGRAM_STATE,
)
from .coordinator import CandyCoordinator


def _params(data: dict[str, Any]) -> dict[str, Any]:
    """Return the current_status_parameters dict from the status document."""
    return data.get("current_status_parameters", {}) or {}


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stats(data: dict[str, Any]) -> dict[str, Any]:
    """Return the parsed ``statistics`` object.

    In the cloud response ``statistics`` is a JSON-encoded *string* holding
    ``{"lastUpdate": ..., "statusCounters": {...}}``. It only changes when the
    phone syncs the appliance over NFC, so for NFC machines this is the real
    (cumulative) data — the live ``current_status_parameters`` stays empty.
    """
    raw = data.get("statistics")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


def _counters(data: dict[str, Any]) -> dict[str, Any]:
    return _stats(data).get("statusCounters", {}) or {}


def _total_cycles(data: dict[str, Any]) -> int | None:
    """Total wash cycles = sum of the temperature buckets (reliable count)."""
    c = _counters(data)
    keys = [k for k in c if k.startswith("Temp")]
    if not keys:
        return None
    total = 0
    for k in keys:
        v = _as_int(c.get(k))
        if v is not None:
            total += v
    return total


def _stats_last_update(data: dict[str, Any]) -> datetime | None:
    raw = _stats(data).get("lastUpdate")
    if not raw:
        return None
    return dt_util.parse_datetime(raw)


@dataclass(frozen=True, kw_only=True)
class CandySensorDescription(SensorEntityDescription):
    """Describes a Candy sensor and how to extract its value."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSORS: tuple[CandySensorDescription, ...] = (
    CandySensorDescription(
        key="machine_state",
        name="Machine state",
        icon="mdi:washing-machine",
        value_fn=lambda d: MACHINE_STATE.get(
            _as_int(_params(d).get("MachMd")), "Unknown"
        ),
    ),
    CandySensorDescription(
        key="program_phase",
        name="Program phase",
        icon="mdi:progress-clock",
        value_fn=lambda d: PROGRAM_STATE.get(
            _as_int(_params(d).get("PrPh")), "Unknown"
        ),
    ),
    CandySensorDescription(
        key="remaining_minutes",
        name="Remaining time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        icon="mdi:timer-sand",
        value_fn=lambda d: (
            round(v / 60)
            if (v := _as_int(_params(d).get("RemTime"))) is not None
            else None
        ),
    ),
    CandySensorDescription(
        key="temperature",
        name="Target temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _as_int(_params(d).get("Temp")),
    ),
    CandySensorDescription(
        key="spin_speed",
        name="Spin speed",
        native_unit_of_measurement="rpm",
        icon="mdi:rotate-3d-variant",
        value_fn=lambda d: (
            v * 100
            if (v := _as_int(_params(d).get("SpinSp"))) is not None
            else None
        ),
    ),
    CandySensorDescription(
        key="program",
        name="Program number",
        icon="mdi:numeric",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _as_int(
            _params(d).get("Pr", _params(d).get("PrNm"))
        ),
    ),
    CandySensorDescription(
        key="fill_percent",
        name="Fill level",
        native_unit_of_measurement="%",
        icon="mdi:water-percent",
        value_fn=lambda d: _as_int(_params(d).get("FillR")),
    ),
    CandySensorDescription(
        key="remote_control",
        name="Remote control",
        icon="mdi:remote",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: "On"
        if _params(d).get("WiFiStatus") == "1"
        else "Off",
    ),
)

# Statistics sensors. These read the cumulative `statistics` object, which is
# what NFC appliances expose (they have no live status). The full per-program /
# per-temperature counter map is attached as attributes on "total cycles".
STATS_SENSORS: tuple[CandySensorDescription, ...] = (
    CandySensorDescription(
        key="total_cycles",
        name="Total cycles",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="cycles",
        value_fn=_total_cycles,
        attrs_fn=lambda d: {
            **{f"counter_{k}": v for k, v in _counters(d).items()},
        },
    ),
    CandySensorDescription(
        key="stats_last_update",
        name="Statistics last synced",
        icon="mdi:nfc",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_stats_last_update,
    ),
    CandySensorDescription(
        key="washes_cold",
        name="Washes 0-30°C",
        icon="mdi:snowflake",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="cycles",
        value_fn=lambda d: _as_int(_counters(d).get("Temp0to30")),
    ),
    CandySensorDescription(
        key="washes_warm",
        name="Washes 40°C",
        icon="mdi:thermometer",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="cycles",
        value_fn=lambda d: _as_int(_counters(d).get("Temp40")),
    ),
    CandySensorDescription(
        key="washes_hot",
        name="Washes 60-90°C",
        icon="mdi:thermometer-high",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="cycles",
        value_fn=lambda d: _as_int(_counters(d).get("Temp60to90")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Candy Simply-Fi sensors from a config entry."""
    coordinator: CandyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CandySensor(coordinator, entry, description)
        for description in (*SENSORS, *STATS_SENSORS)
    )


class CandySensor(CoordinatorEntity[CandyCoordinator], SensorEntity):
    """A single read-only sensor backed by the polling coordinator."""

    entity_description: CandySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CandyCoordinator,
        entry: ConfigEntry,
        description: CandySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        appliance_id = entry.data[CONF_APPLIANCE_ID]
        self._attr_unique_id = f"{appliance_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, appliance_id)},
            name=entry.data.get(CONF_APPLIANCE_NAME, f"Candy {appliance_id}"),
            manufacturer="Candy / Haier",
            model="Simply-Fi",
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data or {})
