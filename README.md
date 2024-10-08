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