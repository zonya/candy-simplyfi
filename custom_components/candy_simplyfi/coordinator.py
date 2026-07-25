"""DataUpdateCoordinator for Candy Simply-Fi."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CandyApiError, CandyAuthError, CandySimplyFiClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class CandyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls one appliance's status document from the cloud."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: CandySimplyFiClient,
        appliance_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{appliance_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.appliance_id = appliance_id

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_appliance(self.appliance_id)
        except CandyAuthError as err:
            raise UpdateFailed(f"Auth error: {err}") from err
        except CandyApiError as err:
            raise UpdateFailed(f"API error: {err}") from err
