# Temporary VirtualDimmingActuator hardware test

The Git dependency in `custom_components/abbfreeathome_ci/manifest.json` is
**temporary and only intended for local development and hardware testing**:

```text
local-abbfreeathome@git+https://github.com/r9fhd6cjnr-debug/local-abbfreeathome.git@virtual-dimming-actuator
```

Before an upstream pull request, replace it with a released, pinned PyPI version
that includes `VirtualDimmingActuator`. The released version `3.8.2` does not provide
this class. JSON does not support comments, so this note documents the temporary
manifest change without adding unsupported manifest fields.

On the test installation:

- Confirm Home Assistant successfully installs the Git requirement and loads the
  new class. The installation environment needs Git and access to GitHub. A branch
  reference is mutable; record the tested library commit and verify the installed
  revision when retesting after branch updates.
- Enable virtual devices in the integration options. Place the channel on the
  SysAP floor plan or enable orphan channels as appropriate.
- Confirm the SysAP configuration reports function `0012`, input pairing `1`
  (`AL_SWITCH_ON_OFF`) and input pairing `16`
  (`AL_RELATIVE_SET_VALUE_CONTROL`). The observed telegrams alone do not contain
  these identifiers.
- Check that exactly one event entity exposes `On`, `Off`, `longpress_up`,
  `longpress_up_release`, `longpress_down`, and `longpress_down_release`.
- Test press/release in both directions, repeated commands, and switching plus
  dimming in the same WebSocket message. Each callback writes its event immediately;
  the entity state shows the latest event while automations can observe each write.
- Unknown dimming commands and an uninitialized switching request are ignored.
  No brightness calculation or automatic Home Assistant light control is added.
- Reload the integration and verify callbacks are removed and re-registered once.

## Debug logs to share

Enable the following logger in Home Assistant (merge with an existing `logger`
section if present):

```yaml
logger:
  default: warning
  logs:
    custom_components.abbfreeathome_ci.event: debug
```

Alternatively, enable the same logger at runtime via `logger.set_level`:

```yaml
action: logger.set_level
data:
  custom_components.abbfreeathome_ci.event: debug
```

After reloading the integration, test On, Off, hold up/release, hold down/release,
then rapid repetitions. Copy the `Virtual dimmer <serial>/<channel>` log lines,
any exception traceback, the Home Assistant version, and the entity's
`event_types` / `event_type` attributes. Expected messages include:

```text
Virtual dimmer 6000F66D1DA7/ch0000: requested_state=True -> On
Virtual dimmer 6000F66D1DA7/ch0000: requested_state=False -> Off
Virtual dimmer 6000F66D1DA7/ch0000: requested_dimming_state='longpress_up' -> event longpress_up
Virtual dimmer 6000F66D1DA7/ch0000: requested_dimming_state='longpress_up_release' -> event longpress_up_release
Virtual dimmer 6000F66D1DA7/ch0000: requested_dimming_state='unknown' -> ignored
```

To check event delivery as well as decoding, listen to `state_changed` in
Developer Tools and inspect messages for the event entity. Its state is the
timestamp of the most recent event, and `event_type` identifies the command.
The two inputs produce separate state writes, even within one WebSocket message.

## Automated tests on a Linux development machine

Use a separate Python 3.13 environment, as in the repository's CI workflow:

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install 'local-abbfreeathome@git+https://github.com/r9fhd6cjnr-debug/local-abbfreeathome.git@virtual-dimming-actuator'
python -m pip install -r dev-requirements.txt ruff
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

For detailed output from the new tests, run
`python -m pytest -v tests/test_virtual_dimming_event.py`. Share the summary and
complete failure tracebacks if any tests fail. Do not install the development
dependencies into the running Home Assistant environment.
