"""Config flow for Candy Simply-Fi (Cloud)."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    CandyApiError,
    CandyAuthError,
    CandyLoginError,
    CandySimplyFiClient,
    async_login_with_password,
)
from .const import (
    CONF_API_ENDPOINT,
    CONF_APPLIANCE_ID,
    CONF_APPLIANCE_NAME,
    CONF_AUTH_ENDPOINT,
    CONF_CLIENT_ID,
    CONF_REFRESH_TOKEN,
    DEFAULT_API_ENDPOINT,
    DEFAULT_AUTH_ENDPOINT,
    DEFAULT_CLIENT_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class CandyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Two-step flow: enter credentials, then pick an appliance."""

    VERSION = 1

    def __init__(self) -> None:
        self._creds: dict[str, str] = {}
        self._appliances: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                # exchange email + password for a long-lived refresh_token
                refresh_token = await async_login_with_password(
                    user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
                creds = {
                    CONF_AUTH_ENDPOINT: DEFAULT_AUTH_ENDPOINT,
                    CONF_API_ENDPOINT: DEFAULT_API_ENDPOINT,
                    CONF_CLIENT_ID: DEFAULT_CLIENT_ID,
                    CONF_REFRESH_TOKEN: refresh_token,
                }
                client = CandySimplyFiClient(
                    async_get_clientsession(self.hass),
                    api_endpoint=creds[CONF_API_ENDPOINT],
                    auth_endpoint=creds[CONF_AUTH_ENDPOINT],
                    client_id=creds[CONF_CLIENT_ID],
                    refresh_token=creds[CONF_REFRESH_TOKEN],
                )
                await client.async_refresh_token()
                self._appliances = await client.async_list_appliances()
            except CandyLoginError:
                errors["base"] = "auth"
            except CandyAuthError:
                errors["base"] = "auth"
            except CandyApiError:
                errors["base"] = "cannot_connect"
            else:
                if not self._appliances:
                    errors["base"] = "no_appliances"
                else:
                    # store only the token, never the password
                    self._creds = creds
                    return await self.async_step_appliance()

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_appliance(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # Build a friendly {id: label} map from the discovered appliances.
        options: dict[str, str] = {}
        for appl in self._appliances:
            appl_id = str(appl.get("id"))
            label = (
                appl.get("nickname")
                or appl.get("name")
                or appl.get("appliance_model")
                or appl.get("model")
                or appl.get("appliance_type")
                or "Candy appliance"
            )
            options[appl_id] = f"{label} ({appl_id[:8]})"

        if user_input is not None:
            appliance_id = user_input[CONF_APPLIANCE_ID]
            await self.async_set_unique_id(appliance_id)
            self._abort_if_unique_id_configured()
            data = {
                **self._creds,
                CONF_APPLIANCE_ID: appliance_id,
                CONF_APPLIANCE_NAME: options.get(appliance_id, appliance_id),
            }
            return self.async_create_entry(
                title=options.get(appliance_id, f"Candy {appliance_id}"),
                data=data,
            )

        schema = vol.Schema(
            {vol.Required(CONF_APPLIANCE_ID): vol.In(options)}
        )
        return self.async_show_form(step_id="appliance", data_schema=schema)
