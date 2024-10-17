# Home Assistant Integration - ABB Free@Home via Local Api

This is a custom component to integrate with [Home Assistant](https://www.home-assistant.io/) for the Busch Jaeger/ABB Free@Home system over the **local api server**.

The primary goal of this repository is to provide initial testing for the integration into Home Assistant. The ultimate goal of this integration is to be merged into the Home Assistant code as a built-in integration.

Because of this, the integration will adhere to the strict [styling and code guidelines](https://developers.home-assistant.io/docs/development_guidelines/) provided by Home Assistant.

## Device Support

This is a new repo written from the ground up in tandem with the PyPi Package [local-abbfreeathome](https://pypi.org/project/local-abbfreeathome/#description) in order to communicate with the ABB Free@Home System over the **local** api. **The initial list of supported devices is 1 (Switch/Actuator).**

The initial goal is to thoroughly test the integration (and by proxy the PyPi package) to ensure there are no bugs within the code. It's also to ensure it's feature and code complete (e.g. ZeroConf, UnitTests).

Once this is feature and code complete it should provide a solid base as to which new devices can be integrated into. I (kingsleyadam) don't have access to the number of different ABB devices and would rely on others to either provide configurations, or contribute code directly in order to add additional device support. It'll be much easier long-term if the core code is stable.

> **If you need support for additional devices I'd strongly reccomend you check out the repo [here](https://github.com/jheling/freeathome). That repo has been around for a long time and provides support for a number of devices.**

### Additional Devices

If you would like your device supported in this integration, please start by opening a GitHub issue with the device configuration.

## Installation

### HACS

The easiest way to add this custom integration is via HACS which the repo has been setup to support. With HACS setup on your Home Assistant installation you'll need to add this repo it as a [custom repository](https://www.hacs.xyz/docs/faq/custom_repositories/).

Once added you'll be able to find it by searching for "Busch Jaeger/ABB Free@Home (Local API)".

### Manually

1. Clone the code locally and copy all the files in `custom_components/abbfreeathome_ci` to your Home Assistant directory `./config/custom_components/abbfreeathome_ci`
2. Restart Home Assistant
3. You should be able to add a new integration "Busch Jaeger/ABB Free@Home (Local API)".
4. Follow the UI configuration to add the integration to your instance.

## Configuration

### Local API, Credentials

Before you can setup this integration you must turn on the local API on your ABB Free@Home SysAP. More information about the local api can be found on the ABB site [here](https://developer.eu.mybuildings.abb.com/fah_local).

Navigate to: `SysAP Configuration` > `Settings` > `free@home - Settings` > `Local API` > `Activate Local API`

Copy the username listed within that window (usually `installer`) to be used when invoking the api. The password will be your personally set password to login to the app and web interface.

### Add Integration

#### SysAP Discovery

In most installations the integration will find your Free@Home SysAP automatically on the network. After you've installed the integration and restarted Home Assistant you should see your SysAP as a new device to be setup. You just need to enter your **api** username and password to confirm the setup.

#### Manual (User) Setup

If the SysAP is not found automatically you can add it manually. Add this integration by searching for and clicking on `Busch Jaeger/ABB Free@Home (Local API)`.

When adding the integration manually you'll be prompted for the `Hostname`, `Username`, and `Password`. The hostname must be the fully resolvable hostname with protocol (e.g. http). Adding the integration will fail if you just provide the IP address or hostname.

##### Example

- **Hostname**: `http://192.168.1.100`
- **Username**: `installer`
- **Password**: `<password>`

> Note: Support for SSL is not provided yet. For a valid SSL connection a cert pulled from the SysAP must be provided, research to be done to know if Home Assistant supports such a scenario.

### Automatic Area Discovery

When adding the integration it'll automatically add devices to different `Areas` in Home Assistant. The areas will be pulled from your ABB Free@Home Configuration/Floorplan. When prompted to add the devices double check the area for each.

## Events

### Switch Sensor

The Switch Sensor's can be deceiving. These are additional On/Off sensors that are associated with a switching device. If you physically hit the switch sensor (On or Off) the Switch sensor status will be updated in Home Assistant accordingly.

If you turn off the light either via Home Assistant, Free@Home App, or any other non-physical method, the Switch sensor will NOT be updated to match the lights status.

This can cause issues if you attempt to automate a light. If the light is already turned off via Home Assisant, and the Switch sensor is still in the `On` state, you won't be able to turn on the light by using the switch sensor.

>**It is best to associated a Switch directly with a Light in the Free@Home configuration if at all possible. E.g., if you have a Philips Hue Bulb, it's best to setup Philip Hue lights within Free@Home and associated a switch with it directly, avoiding Home Assistant completely, it'll be much more straight forward and responsive.**

If you want to control a device, or set of devices using the Switch Sensor in Home Assistant, it's best to use emmited events. The `SwitchSensor` class will emit an event when pressed.

The `event_type` will be `abbfreeathome_ci_event` and the `data.type` for a Switch Sensor will be `switch_sensor_triggered`. The `state` will be whether the sensor was triggered `On` (true) or `Off` (false).

With this, you can create an automation to control devices accordgingly.

#### Example Automation

```yaml
alias: Test Trigger Sensor Event
description: This will turn off/on a light based on the Switch Sensor event.
triggers:
  - trigger: event
    event_type: abbfreeathome_ci_event
    event_data:
      entity_id: binary_sensor.office_rocker_switch_sensor
      type: switch_sensor_triggered
conditions: []
actions:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.state == True }}"
        sequence:
          - action: switch.turn_on
            target:
              entity_id: switch.3rd_floor_landing_light
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.state == False }}"
        sequence:
          - action: switch.turn_off
            target:
              entity_id: switch.3rd_floor_landing_light
mode: single
```

#### Example Event

```yaml
event_type: abbfreeathome_ci_event
data:
  entity_id: binary_sensor.office_rocker_switch_sensor
  type: switch_sensor_triggered
  state: true
origin: LOCAL
time_fired: "2024-10-17T13:54:19.215731+00:00"
context:
  id: 01JADC40YFB37NS336PWZVJ1R2
  parent_id: null
  user_id: null
```

## Debugging

If you're having issues with the integration, maybe not all devices are showing up, or entities are not responding as you'd expect, you can do two things to help debug.

### Enable Verbose Logging

You can enable more verbose logging within your Home Assistant installation just for this integration by adding the following to your Home Assistant `configuration.yaml` file.

By default the Home Assistant default logger is `warning`, this configuration won't change that. But it'll create additional logs for both this integration and the PyPi module running a number of calls to the SysAP.


```yaml
logger:
  default: warning
  logs:
    abbfreeathome: debug
    custom_components.abbfreeathome_ci: debug
```

### Download Diagnostics

If you request help via GitHub [Discussions](https://github.com/kingsleyadam/local-abbfreeathome-hass/discussions) you will likely be asked to share the integration diagnostics.

The [diagnostics](https://www.home-assistant.io/docs/configuration/troubleshooting/#download-diagnostics) will share some information about your Home Assistant installation and this integration's installation.

To pull the diagnostics about this integration navigate to the integration under `Settings` --> `Devices & Services` --> `Busch Jaeger/ABB Free@Home (Local API)`. Click the 3 dots next to the integration entity and click `Download Diagnostics`. Private information should be redacted from the download, but it's always good to double check the output before sending.

Along with the `home_assistant` and `integration_manifest` you should also see `data` which includes your SysAP configuration and devices.