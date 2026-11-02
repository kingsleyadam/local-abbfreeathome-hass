---
applyTo: "custom_components/**/*.json,custom_components/**/services.yaml"
---

## Strings, translations, and icons

- Every user-facing string lives in three files that must keep identical key
  sets: `strings.json`, `translations/en.json`, and `translations/de.json`.
  Home Assistant loads only `translations/*.json` for custom integrations, so a
  key missing there shows as a raw key to users; nothing generates these files.
- `strings.json` is the source and may use Home Assistant references such as
  `[%key:common::config_flow::data::host%]` or
  `[%key:component::sensor::entity_component::temperature::name%]`.
  `en.json` is the same content with every reference replaced by its English
  text. `de.json` holds the German translation; write natural German rather than
  leaving English, and use the same terms as the existing entries.
- Entity names live under `entity.<platform>.<translation_key>.name`, matching
  the `translation_key` in the platform's description table. Names may use the
  `{channel_id}` placeholder. Enum-like values are translated under `state`:
  select `options` and enum sensor values under
  `entity.<platform>.<key>.state`, and event types under
  `entity.event.<key>.state_attributes.event_type.state`. Keys are the
  lowercase enum names the code produces.
- Service fields and sections in `services.yaml` need matching `name` and
  `description` entries under `services.<service>.fields` and `.sections` in all
  three files; service errors use keys under `exceptions`.
- Config flow steps, fields, errors, and aborts live under `config`; add
  strings for every new step, field, error, and abort reason.
- `icons.json` maps `entity.<platform>.<translation_key>` to a `default` icon and
  optional `state` icons. Only use `mdi:` icons, only for translation keys that
  exist in `strings.json`, and only use states that `strings.json` declares.
  Binary sensor entries must include an `on` state icon so the device-class
  icon still reflects the alarm. `tests/test_icons.py` enforces these rules.
- Keep JSON formatting consistent with the existing files (two-space indent, no
  reordering of existing keys) so diffs stay small. `hassfest` validates these
  files in CI.
