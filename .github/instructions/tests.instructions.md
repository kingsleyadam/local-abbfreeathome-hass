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
- `mock_free_at_home_settings`: the SysAP settings; it patches the class used by
  `config_flow.py` and is passed to `setup_with_channels()`.
- `mock_free_at_home_api`: patches `FreeAtHomeApi` in `config_flow.py`.
- `mock_setup_entry`: patches `async_setup_entry` for config-flow tests.
- `deprecation_log`: the deprecations logged so far; a test that triggers one
  on purpose takes it with `pop()` and asserts on it.
- `snapshot`: syrupy's snapshot with Home Assistant's extension, which stores
  snapshots in `tests/snapshots/`.

Helpers in `tests/common.py`:

- `setup_with_channels(hass, entry, settings, channels)`: sets up the config
  entry through `hass.config_entries.async_setup()` with only the SysAP
  connection mocked (`FreeAtHomeSettings`, `FreeAtHome`, `FreeAtHomeApi`, and
  `async_get_clientsession`), and returns the mock `FreeAtHome` that serves the
  channels. `devices=` adds devices without visible channels.
- `build_device()`: a real library `Device` whose `api` is a
  `MagicMock(spec=FreeAtHomeApi)`, so `api.set_datapoint` and
  `api.get_datapoint` are `AsyncMock`s.
- `build_channel(channel_class, device, channel_id, inputs=..., outputs=...,
  parameters=...)`: a real library channel added to the device. Inputs and
  outputs map `Pairing` members to datapoint values and get the IDs `idp0000`,
  `odp0000`, ... in order. A device without a room and with several channels is
  a multi-device.
- `build_trigger()`, `devices_changed()`, and `get_device_entry()` for runtime
  device changes.
- `snapshot_entities(hass, snapshot, entry_id)`: snapshots the registry entry
  and state of every entity of the entry, named by unique ID. It keeps only the
  fields the integration decides, so one snapshot fits every Home Assistant
  version in the matrix; do not use the plugin's `snapshot_platform()`, whose
  output differs between versions. Update snapshots with
  `python -m pytest --snapshot-update` and review the `.ambr` diff.

Platform tests:

- Test entities through Home Assistant, as core integrations do: build real
  library channels from the pairings and parameters the library reads, set up
  the entry with `setup_with_channels()`, restrict `PLATFORMS` to the platform
  under test with `monkeypatch`, and check the result only through Home
  Assistant: `snapshot_entities()` for the entities, `hass.states`, and the
  entity and device registries.
- Send commands with `hass.services.async_call(..., blocking=True)` and assert
  the datapoints the library sets with `device.api.set_datapoint`.
- Simulate the SysAP reporting a state with
  `channel.update_channel("<serial>/<channel>/<datapoint>", value)` and check
  `hass.states` after each report. Test reports in a test without commands: a
  command already changes the library's cached state, so only then does the
  state in Home Assistant prove the channel callback works.
- Cover every description or channel class the platform maps, `None` attribute
  handling, both `create_subdevices` cases, updates, and unloading the entry.
- Mock only what cannot be real, such as the SysAP connection. Instantiate an
  entity directly only for a branch Home Assistant cannot reach, and say why in
  the test's docstring.

Other patterns:

- Runtime lifecycle tests in `tests/test_init.py` and
  `tests/test_unresponsive.py` use `setup_with_channels()` as well, with real
  `Trigger` channels.
- CI requires 100% line and branch coverage; check that the platform module
  is covered by its own test file.
