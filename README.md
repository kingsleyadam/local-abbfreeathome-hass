# Home Assistant Integration - ABB Free@Home via Local Api

This is a custom component to integrate with [Home Assistant](https://www.home-assistant.io/) for the Busch Jaeger/ABB Free@Home system over the **local api server**.

The primary goal of this repository is to provide initial testing for the integration into Home Assistant. The ultimate goal of this integration is to be merged into the Home Assistant code as a built-in integration.

Because of this, the integration will adhere to the strict [styling and code guidelines](https://developers.home-assistant.io/docs/development_guidelines/) provided by Home Assistant.

## Device Support

The current list of supported devices by function are:

| Function | Platform(s)
|--|--|
| FID_SWITCH_ACTUATOR | `Switch` |
| FID_SWITCH_SENSOR | `Binary Sensor`, `Event` |
| FID_MOVEMENT_DETECTOR | `Binary Sensor`, `Sensor` |
| FID_DIMMING_ACTUATOR | `Light` |
| FID_WINDOW_DOOR_SENSOR | `Binary Sensor` |
| FID_WINDOW_DOOR_POSITION_SENSOR | `Binary Sensor`, `Sensor` |
| FID_SMOKE_DETECTOR | `Binary Sensor` |
| FID_CARBON_MONOXIDE_SENSOR | `Binary Sensor` |


### Additional Devices

This is a new repo written from the ground up in tandem with the PyPi Package [local-abbfreeathome](https://pypi.org/project/local-abbfreeathome/#description) in order to communicate with the ABB Free@Home System over the **local** api. **The list of supported functions may not include your device.** If you expect a device to appear and don't, please open a new issues and include the device configuration. To fetch your device configuration download the integration [diagnostics](#download-diagnostics).

I (kingsleyadam) don't have access to the number of different ABB devices and would rely on others to either provide configurations, or contribute code directly in order to add additional device support.

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

#### Configuration Options

The config setup will include some options to help configure the integration.

| Configuration | Description |
| ----------- | ----------- |
| Hostname | **Only available in Manual (User) Setup.** The full hostname including schema of the ABB Free@Home SysAP endpoint. |
| Username | The **api** username, likely different from your normal login username. |
| Password | The password for logging into the SysAP. |
| Include channels NOT on the Free@Home floorplan? | Whether to include channels that are not located on the Free@Home floorplan. |

###### Example

- **Hostname**: `http://192.168.1.100`
- **Username**: `installer`
- **Password**: `<password>`
- **Include channels NOT on the Free@Home floorplan?**: False

> Note: Support for SSL is not provided yet. For a valid SSL connection a cert pulled from the SysAP must be provided, research to be done to know if Home Assistant supports such a scenario.

#### SysAP Discovery

In most installations the integration will find your Free@Home SysAP automatically on the network. After you've installed the integration and restarted Home Assistant you should see your SysAP as a new device to be setup. The hostname will automatically be discovered, you just need to enter your **api** username, password, and whether to include channels not in the floorplan to confirm the setup.

#### Manual (User) Setup

If the SysAP is not found automatically you can add it manually. Add this integration by searching for and clicking on `Busch Jaeger/ABB Free@Home (Local API)`.

When adding the integration manually you'll be prompted with all fields. The hostname must be the fully resolvable hostname with protocol (e.g. http). Adding the integration will fail if you just provide the IP address or hostname.

### Automatic Area Discovery

When adding the integration it'll automatically add devices to different `Areas` in Home Assistant. The areas will be pulled from your ABB Free@Home Configuration/Floorplan. When prompted to add the devices double check the area for each.

## Events

### Switch Sensor

The Switch Sensors can be deceiving. These are additional On/Off sensors associated with a switching device. If you physically toggle the switch sensor (On or Off), the status of the switch sensor will be updated in Home Assistant accordingly.

However, if you turn off the light using Home Assistant, the Free@Home app, or any other non-physical method, the switch sensor will not be updated to reflect the light's status.

This discrepancy can cause issues when automating a light. If the light is already turned off via Home Assistant, but the switch sensor still indicates an `On` state, you won't be able to turn the light on using the switch sensor.

>**It is best to associate a switch directly with a light in the Free@Home configuration whenever possible. For example, if you have a Philips Hue bulb, it's advisable to set up Philips Hue lights within Free@Home and associate a switch with it directly. This approach avoids using Home Assistant entirely, making the setup much more straightforward and responsive.**

If you want to control a device or a set of devices using the switch sensor in Home Assistant, it's best to use emitted events. The `SwitchSensor` class will emit an event when pressed.

These will be visible as events within the devices that support it. Using these events you can create automations to control devices accordingly.

#### Example Automation

```yaml
alias: Test Trigger Sensor Event
description: This will turn off/on a light based on the Switch Sensor event.
triggers:
  - trigger: state
    entity_id:
      - event.study_area_rocker_switch_event
    to: "Off"
    attribute: event_type
    id: study_area_event_off
  - trigger: state
    entity_id:
      - event.study_area_rocker_switch_event
    attribute: event_type
    to: "On"
    id: study_area_event_on
conditions: []
actions:
  - choose:
      - conditions:
          - condition: trigger
            id:
              - study_area_event_off
        sequence:
          - action: switch.turn_off
            target:
              device_id:
                - 615bdcd2980a3a2a341488f50b7d8aea
      - conditions:
          - condition: trigger
            id:
              - study_area_event_on
        sequence:
          - action: switch.turn_on
            target:
              device_id: 615bdcd2980a3a2a341488f50b7d8aea
mode: single
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