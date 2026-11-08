---
name: add-entity
description: Expose a local-abbfreeathome channel, channel attribute, or function ID as Home Assistant entities in the ABB-free@home integration, covering platform choice, description tables, translations, icons, tests, and the README device table. Use when asked to support a new device, function ID, or channel feature in Home Assistant, or to add an entity or platform.
---

# Adding entities

Read `.github/instructions/entities.instructions.md`,
`.github/instructions/translations.instructions.md`, and
`.github/instructions/tests.instructions.md` first; this skill applies them.

## 1. Confirm the library supports it

The integration only maps library channel classes to entities; protocol and
datapoint handling belong in
[`local-abbfreeathome`](https://github.com/kingsleyadam/local-abbfreeathome).

1. Identify the function ID and the channel's data, typically from the user's
   integration diagnostics (`Download diagnostics` in Home Assistant) or a
   Device Support discussion.
2. With the virtual environment active, check the pinned library version maps
   that function ID to a class and exposes the attributes and commands needed:

   ```sh
   python -c "
   from abbfreeathome import const
   for m in (const.FUNCTION_CHANNEL_MAPPING, const.FUNCTION_VIRTUAL_CHANNEL_MAPPING):
       for f, c in m.items():
           if f.name == 'FID_...': print(c.__module__, c.__name__)"
   ```

3. If the class, attribute, or command is missing, stop: it must be added to the
   library (its `add-channel` skill), released, and pinned here first with the
   `bump-library` skill. If it exists only in a newer library release, bump the
   pin in a separate PR before this one.

To find library classes that no platform uses yet:

```sh
python - <<'EOF'
import ast, pathlib
from abbfreeathome import const
mapped = {c.__name__ for m in (const.FUNCTION_CHANNEL_MAPPING, const.FUNCTION_VIRTUAL_CHANNEL_MAPPING) for c in m.values()}
used = set()
for f in pathlib.Path("custom_components/abbfreeathome_ci").glob("*.py"):
    for n in ast.walk(ast.parse(f.read_text())):
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("abbfreeathome.channels"):
            used |= {a.name for a in n.names}
print(sorted(mapped - used))
EOF
```

## 2. Choose platforms and entities

Map each channel attribute to the Home Assistant platform that matches its
behavior, following the closest existing channel:

| Channel data | Platform | Example |
| --- | --- | --- |
| Controllable on/off output | `switch` (or `light`, `cover`, `valve`, `lock` by device type) | `SwitchActuator` |
| Read-only boolean alarm or state | `binary_sensor` | `WindowDoorSensor` |
| Measurement | `sensor` with device class and unit | `TemperatureSensor` |
| Read-only multi-valued state | `sensor` with `SensorDeviceClass.ENUM` | `HeatingCoolingSensor` (#291) |
| Selectable mode or forced position | `select` | forced-position entries in `select.py` |
| Settable value | `number` | `number.py` |
| Button press or incoming request | `event` (or `button` for commands) | `StaircaseLightSensor` (#255) |
| Thermostat | `climate` | `RoomTemperatureController` |

Virtual channels report requests from free@home and accept feedback from Home
Assistant, so they often need an `event` entity for requests plus a feedback
entity (see `VirtualDimmingActuator`, #288). The main feature of a channel
uses the channel name; secondary features get a `translation_key`. Consider
`entity_category` (`config` or `diagnostic`) for entities most users do not
need on dashboards. Confirm the mapping with the user when it is not obvious.

## 3. Implement

Prefer extending an existing platform:

1. Import the channel class (and any state enum) and add an entry to the
   platform's `*_DESCRIPTIONS` table, next to related entries. Keep existing
   keys unchanged; the key becomes part of the `unique_id`.
2. For enum values, build `options` or `event_types` from the library enum's
   `.name` values, as the existing entries do.
3. Add the class to the entity constructor's `channel` type union.
4. Only if the entity needs behavior the existing entity class cannot express
   through the table, extend that class with the smallest change.

A new platform also needs: a module following an existing one (table, a
`build_entities` passed to `async_setup_platform_entities()`, and an entity
subclassing `FreeAtHomeEntity`), an entry in `PLATFORMS` in `__init__.py`, and a
new `tests/test_<platform>.py`.

## 4. Strings and icons

For each new `translation_key`, add the name, plus `state` entries for enum
values or event types, to `strings.json`, `translations/en.json`, and
`translations/de.json`. Add an `icons.json` entry when the device-class icon
does not fit; binary sensors need an `on` state icon.

## 5. Tests

Extend `tests/test_<platform>.py` as described in `tests.instructions.md`:
build real library channels with `build_channel()` from the pairings and
parameters found in step 1, set up the entry with `setup_with_channels()`, and
test only through Home Assistant. Cover:

- The new entity in the platform's `snapshot_entities()` snapshot, which shows
  its unique ID, name, translation, device, and state; review the `.ambr` diff.
- No entity when the channel attribute is `None`.
- Each state value the SysAP reports (`channel.update_channel()`) maps to the
  expected state in `hass.states`, in a test without commands.
- Each service call sets the expected datapoints with
  `device.api.set_datapoint`.
- The device the entity belongs to, with and without `create_subdevices`.

```sh
python -m pytest --cov=. --cov-branch --cov-report=term-missing
ruff check . && ruff format --check .
```

Coverage must stay at 100%, and the changed platform module must appear in the
report; modules no test imports are not measured.

## 6. Documentation

Add or update the function's row in the "Device Support" table in `README.md`
(alphabetical by function name), listing all its platforms. Find the function
names for a class with:

```sh
python -c "
from abbfreeathome import const
from abbfreeathome.channels.<module> import <Class> as C
print([f.name for m in (const.FUNCTION_CHANNEL_MAPPING, const.FUNCTION_VIRTUAL_CHANNEL_MAPPING) for f, c in m.items() if c is C])"
```

Note any setup the user must do (for example a free@home option such as LED
mode) below the table, and consider release highlights in
`.github/release-notes/` for notable device support.

## 7. Open the PR

Use a `feat/<topic>-<issue>` branch, label `Semver-Minor` and `enhancement`
(`Semver-Patch` and `bug` if this fixes a wrong mapping), fill in
`.github/pull_request_template.md`, and link the issue or Device Support
discussion. Ask the reporter to confirm on real hardware when value meanings
were inferred.
