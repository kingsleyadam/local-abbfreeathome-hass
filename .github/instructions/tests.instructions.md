---
applyTo: "tests/**"
---

## Tests

Tests run with `pytest-homeassistant-custom-component` on the pinned Home
Assistant version, or with Home Assistant's own `pytest-homeassistant` on HA dev
and newer releases. Both load as pytest plugins automatically. Import their
helpers, such as `MockConfigEntry`, from `tests/common.py`, which picks the
installed plugin; add further helpers there as needed. `tests/conftest.py` has an
autouse fixture that enables custom integrations. Import the integration as
`custom_components.abbfreeathome_ci.*`. `asyncio_mode = "auto"`,
so async tests and fixtures need no `asyncio` marker. Use the `hass` fixture for a
real Home Assistant instance. Name test files after the module under test
(`test_<platform>.py`).

Shared fixtures in `tests/conftest.py`:

- `mock_config_entry`: a `MockConfigEntry` at the current config-entry version
  with every option set; keep it in sync with `config_flow.py`.
- `mock_free_at_home_settings` and `mock_free_at_home_api`: patch the library
  classes used by `config_flow.py`.
- `mock_setup_entry`: patches `async_setup_entry` for config-flow tests.

Patterns:

- Platform tests build channels with `Mock`/`MagicMock`, setting the
  identifiers entities read (`device_serial`, `channel_id`, `channel_name`,
  `room_name`, `device_name`, and `device.is_multi_device`), the state
  attributes, `AsyncMock` command methods, and `Mock` `register_callback` /
  `remove_callback`. Use `Mock(spec=[...])` when a test depends on attributes
  being absent. Instantiate the entity directly to test properties and
  commands, and assert the channel methods were awaited with the right values.
- To test a platform's `async_setup_entry()`, put a mock `FreeAtHome` with
  `get_channels_by_class` into `hass.data[DOMAIN][entry.entry_id]` and pass a
  `Mock` as `async_add_entities`.
- End-to-end and runtime lifecycle tests in `tests/test_init.py` set up the
  entry through `hass.config_entries.async_setup()` with patched
  `FreeAtHomeSettings`, `FreeAtHome`, `FreeAtHomeApi`, and
  `async_get_clientsession`, and may use real library `Device` and channel
  objects. Restrict loaded platforms with `monkeypatch` on `PLATFORMS` when only
  a few are needed.
- Cover the `create_subdevices` branch of `device_info`, `None` attribute
  handling, and callback registration and removal for new entities; CI requires
  100% line and branch coverage.
