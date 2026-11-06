---
applyTo: "custom_components/**/*.py,tests/**/*.py"
---

## Entity and platform conventions

- Platforms are table-driven. Most modules define a `*_DESCRIPTIONS` dict whose
  keys become `entity_description.key` and whose values name the library
  `channel_class`, the channel attribute to read (`value_attribute` or a
  platform-specific equivalent), and `entity_description_kwargs` such as
  `device_class`, `translation_key`, or `options`. Add support for a channel by
  adding an entry before writing new entity code. Skip a channel when its
  attribute is `None`, as existing builders do, so unsupported features do not
  create dead entities.
- Each platform's `async_setup_entry()` defines a `build_entities(get_channels)`
  function and passes it to `async_setup_platform_entities()` in `entity.py`;
  do not call `async_add_entities` for channels directly. The same builder runs
  at startup and for channels added at runtime, so it must be idempotent and
  rely only on the channels returned by `get_channels`. Channel classes match by
  exact type, not subclass, so list subclasses such as `MWireSwitchActuator`
  explicitly. A new platform must also be added to `PLATFORMS` in `__init__.py`.
- Entities subclass `FreeAtHomeEntity` first, then the Home Assistant entity
  class, and set `self._channel`. Set `_attr_should_poll = False`. In
  `async_added_to_hass()`, call `super()` (it subscribes to device availability)
  and register `async_write_ha_state` with `channel.register_callback()` for
  every attribute the entity reads; remove the same callbacks in
  `async_will_remove_from_hass()`. Do not override `available` unless the entity
  can be unavailable for a reason other than an unresponsive device.
- Library commands run with `wait_for_result=False`, so state normally changes
  only when the WebSocket update arrives. Do not write optimistic state; the
  exception is virtual channels whose state the library updates locally (see
  `FreeAtHomeLightEntity` for `VirtualDimmingActuator`).
- Entity names use `has_entity_name=True` with `name=channel.channel_name` and
  `translation_placeholders={"channel_id": channel.channel_id}`. When an entity
  is a secondary feature of the channel, set a `translation_key`; the translated
  name then replaces the channel name. Every new `translation_key` needs entries
  in the JSON files covered by `translations.instructions.md`.
- `unique_id` is `<device_serial>_<channel_id>_<suffix>`, where the suffix is the
  description key or a fixed platform name such as `light` or `climate`. Several
  platforms keep legacy suffixes for backward compatibility (for example
  `switch.py`, and `lock.py`, which uses `_valve`); never change an existing
  entity's `unique_id`, description key, or suffix, because it orphans users'
  entities and history.
- `device_info` links entities to the device registry entry created in
  `__init__.py` with identifier `(DOMAIN, device_serial)`. When the entry's
  `create_subdevices` option is on and the device `is_multi_device`, entities
  instead belong to a `<device_serial>_<channel_id>` sub-device linked to the
  parent through `async_get_via_device_kwargs()`. Follow the existing platforms'
  `device_info` implementation.
- Keep Home Assistant version differences behind feature detection, preferably
  in `helpers.py`, rather than version checks. Mark every such block, and the
  tests that exist only to cover it, with a compatibility marker (see below).
- Config entry options live in `entry.data` with keys from `const.py`. Adding an
  option requires bumping `MINOR_VERSION` in `config_flow.py`, adding a step to
  `async_migrate_entry()` in `__init__.py` that fills a default, adding it to the
  YAML `CONFIG_SCHEMA`, and updating the `mock_config_entry` fixture in
  `tests/conftest.py` and the "Configuration Options" section of `README.md`.
- User-facing service errors raise `ServiceValidationError` with
  `translation_domain=DOMAIN` and a `translation_key` defined under `exceptions`
  in the translation files.
- Diagnostics must redact anything identifying the installation; extend
  `TO_REDACT` in `diagnostics.py` when exposing new fields.
- When an entity or platform is added for a new function ID, update the "Device
  Support" table in `README.md`.

## Compatibility markers

Code that exists only to support an older Home Assistant or library version
starts with a full-line marker comment:

```python
# compat: homeassistant<2026.8 - via_device_id replaced via_device
```

- The package is `homeassistant` or `local-abbfreeathome`, and the reason is
  required. The block is needed only while the minimum supported version is
  below the marker's version: `homeassistant` in `hacs.json`, or the library pin
  in `manifest.json`.
- Place the marker directly above the smallest block that is deleted once the
  minimum version passes it, such as a `try`, an `if`, an alias, a helper, or a
  test. Use the identical marker on every test or `parametrize` case that exists
  only to cover that block, so one search finds everything to remove. JSON
  cannot hold comments; name strings to delete in the reason of the marker on
  the Python code using them.
- Do not mark compatibility with users' existing data, such as legacy
  `unique_id` suffixes or event types; it does not depend on a version.
- `python .github/scripts/check_compat.py` fails on expired or malformed
  markers and runs in pre-commit and CI; `--list` lists all markers by version,
  and `--minimum 2026.8` previews what a minimum version would expire.
  After raising the minimum version, delete the code it reports together with
  its tests and any now-unused imports or strings.
