# free@home scene request events

The integration creates an event entity for each discovered regular, all-off or
panic scene. Each live scene-control output emits `scene_requested`, including
identical repeated telegrams. Cached configuration values, learning commands and
malformed values do not produce events. A request does not confirm successful
execution by every target device.

The entity uses the scene's configured name. Event attributes include:

| Attribute | Meaning |
| --- | --- |
| `event_type` | `scene_requested` |
| `scene_id` | Stable free@home device serial, for example `FFFF4800000A` |
| `channel_id` | Scene channel, usually `ch0000` |
| `scene_name` | Scene name from the SysAP configuration |
| `scene_control` | Raw telegram value, retained as a string |

Scene identity is the device/channel, not the raw value. The observed value `2`
must not be interpreted as "scene 2" or as a count of physical clicks. The
integration observes the scene notification regardless of its source; it does
not claim that every request originated from a double-click.

## Activate a Hue scene in Home Assistant

Replace both entity IDs below with the actual IDs from your installation:

```yaml
alias: Activate Hue night lighting on a free@home scene request
triggers:
  # Watch the timestamp state, not the event_type attribute: its value stays
  # identical when the same scene is requested again.
  - trigger: state
    entity_id: event.flur_og_nachtlicht
conditions:
  # Ignore entity creation and unavailable/unknown states during reloads.
  - condition: template
    value_template: >-
      {{ trigger.from_state is not none
         and trigger.to_state is not none
         and trigger.from_state.state != 'unavailable'
         and trigger.to_state.state not in ['unknown', 'unavailable']
         and trigger.to_state.attributes.get('event_type') == 'scene_requested' }}
actions:
  - action: scene.turn_on
    target:
      entity_id: scene.hue_night_lighting
mode: queued
```

## Installation and hardware validation

Install both the updated Python library and the updated custom integration.
The integration requires a published `local-abbfreeathome` version containing
`Scene`. The manifest retains the upstream pin, `local-abbfreeathome==3.8.2`,
which does not contain this class and cannot load the new event platform.
Keep this integration pull request in draft until the companion scene library
changes are merged and released, then update the manifest to that published
version before merging or installing it.

For development before the library release, place a checkout containing the
scene library changes in a sibling directory named `local-abbfreeathome`.
Use an isolated Linux/Python 3.13 environment and run these commands from the
integration repository:

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install ../local-abbfreeathome
python -m pip install -r dev-requirements.txt ruff
```

Reload the integration after creating new scenes to fetch their current names
and channels. Place scenes on the floor plan or enable orphan channels. Existing
switch, dimmer and doorbell entities keep their event names and identifiers.

For the confirmed scene `FFFF4800000A` ("Flur OG Nachtlicht"):

1. Check that one scene event entity appears after installation and reload.
2. Confirm that startup does not fire a request, even with a cached output of `2`.
3. Double-click the configured sensor three times with a short pause between
   requests. Each request must update the event timestamp and run the automation.
4. Repeat a request while the target lights already have the requested values.
5. If supported by the SysAP, request the scene from the free@home app as well.
6. Reload the integration and confirm that callbacks are not duplicated.

Enable `custom_components.abbfreeathome_ci.event: debug` to see messages like:

```text
Scene FFFF4800000A/ch0000 (Flur OG Nachtlicht): scene_control='2' -> scene_requested
```

Automated HA tests use real library channels, platform setup and event state
writes. Run them in the repository's Linux/Python CI environment with the updated
library installed:

```sh
python -m pytest -q tests/test_scene_event.py tests/test_event.py tests/test_virtual_dimming_event.py
```
