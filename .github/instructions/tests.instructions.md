---
applyTo: "tests/**"
---

## Tests

Tests run with Home Assistant's own `pytest-homeassistant` on 2026.11 and newer,
including the version pinned for local development, or with
`pytest-homeassistant-custom-component` on the older releases in the CI matrix.
Both load as pytest plugins automatically. Import their helpers, such as
`MockConfigEntry`, from `tests/common.py`, which picks the installed plugin; add
further helpers there as needed. `tests/conftest.py` has an
autouse fixture that enables custom integrations. Import the integration as
`custom_components.abbfreeathome_ci.*`. `asyncio_mode = "auto"`,
so async tests and fixtures need no `asyncio` marker. Use the `hass` fixture for a
real Home Assistant instance. Name test files after the module under test
(`test_<platform>.py`).

A test fails when a deprecation is logged during it, including while its
fixtures are torn down: a `report_usage()` warning of Home Assistant, or another
warning that says something is deprecated or will stop working in Home
Assistant (`tests/deprecations.py`). Deprecated constants and enum members are
reported only while a module is imported, so `test_deprecations.py` also
imports every module of the integration in a fresh interpreter. To check the
hooks in `conftest.py` themselves, it runs `tests/deprecation_samples.py`, which
logs deprecations on purpose, in a separate pytest run. Adopt the
replacement rather than avoiding the warning, and keep the old code path behind
a compatibility marker while supported releases lack the replacement.

Shared fixtures in `tests/conftest.py`:

- `mock_config_entry`: a `MockConfigEntry` at the current config-entry version
  with every option set; keep it in sync with `config_flow.py`.
- `mock_free_at_home_settings` and `mock_free_at_home_api`: patch the library
  classes used by `config_flow.py`.
- `mock_setup_entry`: patches `async_setup_entry` for config-flow tests.
- `deprecation_log`: the deprecations logged so far; a test that triggers one
  on purpose takes it with `pop()` and asserts on it.

Patterns:

- Platform tests build channels with `Mock`/`MagicMock`, setting the
  identifiers entities read (`device_serial`, `channel_id`, `channel_name`,
  `room_name`, `device_name`, and `device.is_multi_device`), the state
  attributes, `AsyncMock` command methods, and `Mock` `register_callback` /
  `remove_callback`. Use `Mock(spec=[...])` when a test depends on attributes
  being absent. Instantiate the entity directly to test properties and
  commands, and assert the channel methods were awaited with the right values.
- To test an entity's state or services in Home Assistant, add the
  `mock_config_entry` to `hass` and the entity with
  `async_setup_entity_platform()` from `tests/common.py`. It adds entities on an
  entity platform of the config entry, which Home Assistant requires for
  entities with device info.
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
