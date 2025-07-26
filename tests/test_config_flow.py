"""Test the abbfreeathome_ci config flow."""

from unittest.mock import patch

from custom_components.abbfreeathome_ci.const import DOMAIN
from homeassistant import config_entries, setup


async def test_form(hass):
    """Test we get the form."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}
