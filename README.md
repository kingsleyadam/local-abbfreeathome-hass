# Home Assistant Integration - ABB-free@home

[![Open in Dev Containers](https://img.shields.io/static/v1?label=Dev%20Containers&message=Open&color=blue)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/kingsleyadam/local-abbfreeathome-hass)
![GitHub Release](https://img.shields.io/github/v/release/kingsleyadam/local-abbfreeathome-hass) ![hassfest](https://github.com/kingsleyadam/local-abbfreeathome-hass/actions/workflows/hassfest.yaml/badge.svg) [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This is a custom component to integrate with [Home Assistant](https://www.home-assistant.io/) for the ABB-free@home system over the **local api server**.

The primary goal of this repository is to provide initial development for the integration into Home Assistant. The ultimate goal of this integration is to be merged into the Home Assistant code as a built-in integration.

Because of this, the integration will adhere to the strict [styling and code guidelines](https://developers.home-assistant.io/docs/development_guidelines/) provided by Home Assistant.

## Prerequisites

There are two main prerequisites before being able to use this integration.

- ABB-free@home System Access Point 2.0
- System Access Point running version 2.6.0 or newer

[ABB-free@home Local API Prerequisites](https://developer.eu.mybuildings.abb.com/fah_local/prerequisites)

> Note: Earlier hardware versions may also work, as reported [here](https://github.com/kingsleyadam/local-abbfreeathome-hass/discussions/148), if they are running firmware version 2.6.0 or newer. Your results may vary.

## Device Support

The current list of supported devices by function are:

| Function                                           | Platform(s)               |
| -------------------------------------------------- | ------------------------- |
| FID_ATTIC_WINDOW_ACTUATOR                          | `Cover`                   |
| FID_AWNING_ACTUATOR                                | `Cover`                   |
| FID_BLIND_ACTUATOR                                 | `Cover`                   |
| FID_BLIND_SENSOR                                   | `Event`                   |
| FID_BRIGHTNESS_SENSOR                              | `Binary Sensor`, `Sensor` |
| FID_CARBON_MONOXIDE_SENSOR                         | `Binary Sensor`           |
| FID_DES_DOOR_OPENER_ACTUATOR                       | `Lock`                    |
| FID_DES_DOOR_RINGING_SENSOR                        | `Event`                   |
| FID_DIMMING_ACTUATOR                               | `Light`                   |
| FID_DIMMING_SENSOR\*                               | `Event`, `Switch`         |
| FID_FORCE_ON_OFF_SENSOR                            | `Event`                   |
| FID_HEATING_ACTUATOR                               | `Valve`                   |
| FID_MOVEMENT_DETECTOR                              | `Binary Sensor`, `Sensor` |
| FID_MOVEMENT_DETECTOR_PYCUSTOM0                    | `Binary Sensor`, `Sensor` |
| FID_RAIN_SENSOR                                    | `Binary Sensor`           |
| FID_ROOM_TEMPERATURE_CONTROLLER_MASTER_WITHOUT_FAN | `Climate`                 |
| FID_SHUTTER_ACTUATOR                               | `Cover`                   |
| FID_SMOKE_DETECTOR                                 | `Binary Sensor`           |
| FID_SWITCH_ACTUATOR                                | `Switch`                  |
| FID_SWITCH_ACTUATOR_PYCUSTOM0                      | `Switch`                  |
| FID_SWITCH_SENSOR\*                                | `Event`, `Switch`         |
| FID_TEMPERATURE_SENSOR                             | `Binary Sensor`, `Sensor` |
| FID_TRIGGER                                        | `Button`                  |
| FID_WIND_SENSOR                                    | `Binary Sensor`, `Sensor` |
| FID_WINDOW_DOOR_SENSOR                             | `Binary Sensor`           |
| FID_WINDOW_DOOR_POSITION_SENSOR                    | `Binary Sensor`, `Sensor` |

\*FID_DIMMING_SENSOR and FID_SWITCH_SENSOR: The LED of these sensors can be controlled. The relevant switch only occurs, if the "LED mode" in F@H is set to "Status Indication" (HA needs to be restarted, if the mode is changed, to take it into account.)

### Additional Devices

This is a new repo written from the ground up in tandem with the PyPi Package [local-abbfreeathome](https://pypi.org/project/local-abbfreeathome/#description) in order to communicate with the ABB-free@home System over the **local** api. **The list of supported functions may not include your device.** If you expect a device to appear and don't, please open a new issues and include the device configuration. To fetch your device configuration download the integration [diagnostics](#download-diagnostics).

I (kingsleyadam) don't have access to the number of different ABB devices and would rely on others to either provide configurations, or contribute code directly in order to add additional device support.

## Installation

### HACS

The easiest way to add this custom integration is via [HACS](https://www.hacs.xyz/) which the repo has been setup to support. With HACS setup on your Home Assistant installation you'll need to add this repo it as a [custom repository](https://www.hacs.xyz/docs/faq/custom_repositories/).

Once added you'll be able to find it by searching for "ABB-free@home".

### Manually

1. Clone the code locally and copy all the files in `custom_components/abbfreeathome_ci` to your Home Assistant directory `./config/custom_components/abbfreeathome_ci`
2. Restart Home Assistant
3. You should be able to add a new integration "ABB-free@home".
4. Follow the UI configuration to add the integration to your instance.

## Configuration

### Local API, Credentials

Before you can setup this integration you must turn on the local API on your ABB-free@home SysAP. More information about the local api can be found on the ABB site [here](https://developer.eu.mybuildings.abb.com/fah_local).

Navigate to: `SysAP Configuration` > `Settings` > `free@home - Settings` > `Local API` > `Activate Local API`

Copy the username listed within that window (usually `installer`) to be used when invoking the api. The password will be your personally set password to login to the app and web interface.

### Add Integration

#### Configuration Options

The config setup will include some options to help configure the integration.

| Configuration                                    | Description                                                                                                                              |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Hostname                                         | **Only available in Manual (User) Setup.** The full hostname including schema of the ABB-free@home SysAP endpoint.                       |
| Username                                         | The **api** username, likely different from your normal login username.                                                                  |
| Password                                         | The password for logging into the SysAP.                                                                                                 |
| Include channels NOT on the free@home floorplan? | Whether to include channels that are not located on the free@home floorplan.                                                             |
| Include virtual devices?                         | Whether to include virtual devices or not.                                                                                               |
| Create Sub-Devices for each independent channel? | Wether to create sub-devices for each channel of a physical device, which can be placed independently on the free@home floorplan or not. |
| Verify SSL Certificate                           | Enable SSL certificate verification. When disabled, HTTPS connections will not verify the server certificate.                            |
| SSL Certificate File Path                        | File path to SSL certificate file to verify HTTPS/SSL connections.                                                                       |

###### Example

- **Hostname**: `http://192.168.1.100`
- **Username**: `installer`
- **Password**: `<password>`
- **Include channels NOT on the free@home floorplan?**: False
- **Include virtual devices?**: False
- **Create Sub-Devices for each independent channel?**: False
- **Verify SSL Certificate**: False
- **SSL Certificate File Path**: `../config/ssl/sysap.crt`

#### SSL Support

The integration supports SSL connections to the ABB-free@home SysAP. When setting up the integration, if you provide `https` schema in the `Hostname` field you will be prompted with some SSL options. You can disable SSL verification completely by unhecking `Verify SSL Certificate`. You will still have an SSL connection, but the endpoint/certificate will not be verified and the connection may be insecure. To enable SSL with certificate verification:

1. Set Verify SSL Certificate to true
2. Provide the path to your SSL certificate file in the "SSL Certificate File Path" field. The path will vary depending on your Home Assistant installation. With HAOS, if you place the ssl cert in your `config/` directory then the path would begin with `../config/`. This is the relative path to the Home Assistant installation directory.

This allows you to securely connect to your SysAP when using HTTPS URLs while providing the necessary certificate for verification.

##### Fetch SSL Certificate

The certificate required for SSL verification is provided by the SysAP.

- Navigate to your SysAP -> Settings --> free@home - Settings --> Local API
- Under `Connection` you'll have an option to `Download Certificate`
- Save the certificate to your Home Assistant server to be used by the integration for SSL verification

#### SysAP Discovery

In most installations the integration will find your free@home SysAP automatically on the network. After you've installed the integration and restarted Home Assistant you should see your SysAP as a new device to be setup. The hostname will automatically be discovered, you just need to enter your **api** username, password, and whether to include channels not in the floorplan to confirm the setup.

#### Manual (User) Setup

If the SysAP is not found automatically you can add it manually. Add this integration by searching for and clicking on `ABB-free@home`.

When adding the integration manually you'll be prompted with all fields. The hostname must be the fully resolvable hostname with protocol (e.g. http). Adding the integration will fail if you just provide the IP address or hostname.

##### Configuration.yaml

The integration also allows you to setup and configure the integration via YAML. For this, add the following to your `configuration.yaml` file.

```yaml
abbfreeathome_ci:
  host: http://<hostname or ip address>
  username: installer
  password: <password>
  include_orphan_channels: false
  include_virtual_devices: false
  create_subdevices: false
  ssl_cert_file_path: ../config/ssl/sysap.crt # optional
  verify_ssl: false # optional
```

**SSL Configuration Examples:**

**With SSL certificate verification:**

```yaml
abbfreeathome_ci:
  host: https://<hostname or ip address>
  username: installer
  password: <password>
  ssl_cert_file_path: ../config/ssl/sysap.crt
  verify_ssl: true
```

**HTTPS without SSL certificate (verification disabled with warning):**

```yaml
abbfreeathome_ci:
  host: https://<hostname or ip address>
  username: installer
  password: <password>
  verify_ssl: false
```

Each time Home Assistant is loaded, the `configuration.yaml` entry for `abbfreeathome_ci` will be checked, verified, and updated accordingly. This means that if you want to update your configuration, simply modify the `configuration.yaml` file and restart Home Assistant.

**Note:** If your configuration settings are invalid in the `configuration.yaml` file, you won’t see any changes in the Home Assistant interface. Instead, you’ll need to check the logs to identify any issues that occurred while adding the integration. For this reason, it’s recommended to set up the integration via the Home Assistant add integrations interface or through auto-discovery.

### Automatic Area Discovery

When adding the integration it'll automatically add devices to different `Areas` in Home Assistant. The areas will be pulled from your ABB-free@home Configuration/Floorplan. When prompted to add the devices double check the area for each.

## Events

### Switch Sensor

The Switch Sensors can be deceiving. These are additional On/Off sensors associated with a switching device. If you physically toggle the switch sensor (On or Off), the status of the switch sensor will be updated in Home Assistant accordingly.

However, if you turn off the light using Home Assistant, the free@home app, or any other non-physical method, the switch sensor will not be updated to reflect the light's status.

This discrepancy can cause issues when automating a light. If the light is already turned off via Home Assistant, but the switch sensor still indicates an `On` state, you won't be able to turn the light on using the switch sensor.

> **It is best to associate a switch directly with a light in the free@home configuration whenever possible. For example, if you have a Philips Hue bulb, it's advisable to set up Philips Hue lights within free@home and associate a switch with it directly. This approach avoids using Home Assistant entirely, making the setup much more straightforward and responsive.**

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
    to: 'Off'
    attribute: event_type
    id: study_area_event_off
  - trigger: state
    entity_id:
      - event.study_area_rocker_switch_event
    attribute: event_type
    to: 'On'
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

## Virtual Devices

Please check the [Wiki](https://github.com/kingsleyadam/local-abbfreeathome-hass/wiki/Virtual-Devices) for a detailed explanation of the virtual device support.

## Debugging

If you're having issues with the integration, maybe not all devices are showing up, or entities are not responding as you'd expect, you can do a few things to help debug.

### Gather Debug Logs

You can temporarily enable debug logs to be captured and downloaded, then shared. This is documented within the Home Assistant [documentation](https://www.home-assistant.io/docs/configuration/troubleshooting/#debug-logs-and-diagnostics). To do this navigate to the integration and click **Enable Debug Logging**.

While this is enabled, all logging events from this integration and the corresponding python package will be available in the home assistant core logs at `Settings` -> `System` -> `Logs`. Ensure `Home Assistant Core` logs are select in the top right (default) and then click the three dot menu and `Show raw logs`.

As log events come in you should see a mix of INFO (green) and DEBUG (blue) logs. You may have to trigger an event on the free@home system to view the logs (e.g. turn on a light switch).

You can filter the logs as well. You may want to filter on `Websocket Response` to view all events happening on the websocket. These are ALL events, even those that are NOT associated with a device or entity in Home Assistant.

**If you're requesting a new device added this this repository** we may ask you to run through the above steps and provide the logs for the specific device you want integrated. You'll want to trigger all of the different functions of the device (close and open curtain, tilt curtain, etc) to capture all events in the logs. You can filter the logs by the serial number (e.g. `ABB7F59C9F7C`) to reduce the amount of logs and easier sharing.

Once finished go back to the integration page and `Disable debug logging`. Once disabled you'll be greeted with a download of all the logs captured during this time.

### Enable Verbose Logging

You can enable more verbose logging permanently within your Home Assistant installation just for this integration by adding the following to your Home Assistant `configuration.yaml` file.

By default the Home Assistant default logger is `warning`, this configuration won't change that. But it'll create additional logs for both this integration and the PyPi module running a number of calls to the SysAP.

```yaml
logger:
  default: warning
  logs:
    abbfreeathome: info
    custom_components.abbfreeathome_ci: info
```

### Download Diagnostics

If you request help via GitHub [Discussions](https://github.com/kingsleyadam/local-abbfreeathome-hass/discussions) you will likely be asked to share the integration diagnostics.

The [diagnostics](https://www.home-assistant.io/docs/configuration/troubleshooting/#download-diagnostics) will share some information about your Home Assistant installation and this integration's installation.

To pull the diagnostics about this integration navigate to the integration under `Settings` --> `Devices & Services` --> `ABB-free@home`. Click the 3 dots next to the integration entity and click `Download Diagnostics`. Private information should be redacted from the download, but it's always good to double check the output before sending.

Along with the `home_assistant` and `integration_manifest` you should also see `data` which includes your SysAP configuration and devices.
