# Eightree/Tuya Local Smart Plug Control

Control your Eightree or Tuya-based smart outlets **locally** from your command line, without relying on the cloud. This is perfect for privacy-focused users and smart home enthusiasts.

## Prerequisites

- Python 3.9+
- Install requirements:

  ```
  pip install -r requirements.txt
  ```

## Fetching `tuya-raw.json` (LocalKey and Device Info)

To control your plug locally, you need the `tuya-raw.json` containing your device's `local_key` and other info. Follow these steps:

1. **Create a Cloud Project in Tuya IoT Platform**
    - Go to [Tuya IoT Platform](https://iot.tuya.com/).
    - Register and **create a cloud project**.
    - Authorize your Tuya Smart app account to the project.

2. **Collect Your Device(s)**
    - Link your Tuya devices to your Tuya Smart app (if not already).
    - In the Tuya IoT Cloud project, go to the Devices tab and **link your devices** to the project.

3. **Set Your Network to Use IPv4**
   - Ensure your network interface is using an IPv4 address (not IPv6!), or discovery won't work.
   - Most routers default to IPv4, but check your system settings if discovery doesn’t work.

4. **Run the CLI to Fetch Device Info**
    - Use [tinytuya's CLI tools](https://github.com/jasonacox/tinytuya) to generate `tuya-raw.json`:
    - Run:
      ```
      python3 -m tinytuya scan
      ```
    - This will:
        - Discover devices via local broadcast.
        - Display the device info needed for local control.

# tinytuya_micropython
