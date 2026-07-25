"""The Candy Simply-Fi (Cloud) integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CandySimplyFiClient
from .const import (
    CONF_API_ENDPOINT,
    CONF_APPLIANCE_ID,
    CONF_AUTH_ENDPOINT,
    CONF_CLIENT_ID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)
from .coordinator import CandyCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Candy Simply-Fi from a config entry."""
    session = async_get_clientsession(hass)
    client = CandySimplyFiClient(
        session,
        api_endpoint=entry.data[CONF_API_ENDPOINT],
        auth_endpoint=entry.data[CONF_AUTH_ENDPOINT],
        client_id=entry.data[CONF_CLIENT_ID],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
    )
    coordinator = CandyCoordinator(hass, client, entry.data[CONF_APPLIANCE_ID])
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
