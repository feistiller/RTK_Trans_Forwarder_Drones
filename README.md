# RTK LoRa Forwarder
用来转发网络CROS作为无人机RTK基站的小工具
This tool is designed to:
1. Act as an NTRIP client to connect to a network RTK service and receive RTCM3/RTCM32 correction data.
2. Forward the received data in real time to a UAV via a locally connected USB LoRa serial module (APM / ArduPilot / PX4, etc.).
3. Allow manual input of a known reference/approximate rover position (sending GGA to inform the caster of the current location), which helps the rover converge to RTK Fix/Float faster and more stably.
4. Provide a simple GUI with:
   - Serial port selection
   - NTRIP parameters (host, port, mountpoint, username, password)
   - Manual position (latitude, longitude, altitude)
   - Connect/Disconnect
   - Data rate/byte counters, log output

## Architecture Overview

Modules:
- `gga.py`: build `$GPGGA` sentences (with checksum).
- `ntrip_client.py`: maintain the TCP connection to the NTRIP caster, periodically send GGA, and continuously receive RTCM data.
- `serial_forwarder.py`: manage the serial port and forward binary RTCM data to the LoRa module.
- `config.py`: read/write configuration JSON.
- `app.py`: Tkinter GUI.

## Installation
Python 3.10+ is recommended.

```bash
pip install -r requirements.txt
```

## Run
```bash
python run_app.py
```

## Usage
1. Prepare your network RTK (NTRIP) account: `Host`, `Port`, `MountPoint`, username, and password.
2. Enter these parameters in the GUI.
3. Enter your current position (latitude, longitude, altitude). If precise altitude is unknown, use 0 or an approximate value and adjust later.
4. Connect and choose the correct serial port (after plugging in the USB LoRa module, click “Refresh” to list COM ports, e.g., `COM5`).
5. Set baud rate (must match the LoRa module and the FC port; common values: 57600 / 115200).
6. Click “Connect”. The log should show NTRIP connected, GGA being sent, and RTCM data being received.
7. On the flight controller (ArduPilot): set `GPS_TYPE=1 (u-blox)` or your actual GPS type; `SERIALx_PROTOCOL=5` to ensure the port receives RTCM; check `GPS_INJECT_TO` if needed. The status should gradually move to RTK Float/RTK Fixed.

## Configuration File
The program will create/update `config.json` in the current directory. Example:
```json
{
  "ntrip": {"host": "example.caster.com", "port": 2101, "mountpoint": "MOUNT", "username": "user", "password": "pass"},
  "position": {"lat": 31.123456, "lon": 121.123456, "alt": 12.3},
  "serial": {"port": "COM5", "baudrate": 57600}
}
```
Some commonly used locations (WGS84):
1. People’s Square, Shanghai: lat 31.230391, lon 121.473701, alt 10
2. Beijing (Tiananmen): lat 39.908722, lon 116.397499, alt 44
3. Shenzhen Civic Center: lat 22.543096, lon 114.057865, alt 20
4. Tianfu Square, Chengdu: lat 30.658601, lon 104.064856, alt 500
5. Tianhe Sports Center, Guangzhou: lat 23.132191, lon 113.327482, alt 20

## FAQ
| Issue | Possible Cause | Fix |
|------|-----------------|-----|
| NTRIP connection fails | Wrong mountpoint or no permission | Verify mountpoint with the provider |
| No data / RTCM bytes not increasing | Unauthorized, GGA not accepted, network blocked | Check account, network; try adjusting the position accuracy |
| Serial send failure | Port in use or disconnected | Re-plug the device and refresh the port list |
| FC not entering RTK | Insufficient data rate, LoRa packet loss, GPS Inject not enabled | Reduce correction rate or increase link bandwidth; verify FC params |
| High latency | LoRa air rate too low | Increase air rate or select a mountpoint with fewer constellations |

### Common reasons for dropping out of RTK+ (Fix/Float) and remedies
- Network jitter/packet loss:
  - Symptom: RTCM byte count stalls; frequent reconnects. Fix: stabilize the uplink, reduce GGA frequency, pick a closer mountpoint, optionally use a local relay.
- LoRa bandwidth or serial baud too low:
  - MSM7 full-constellation can be heavy. Fix: increase serial baud (e.g., 115200), increase LoRa air rate, or switch to a mountpoint with fewer constellations (or MSM4).
- Mountpoint does not output MSM observations:
  - Only see 1005/1006 in logs. Fix: use MSM4/MSM7 mountpoints or contact the provider.
- GGA not accepted (VRS/NEAR only):
  - No data or only a few header frames. Fix: ensure periodic GGA, reasonable position (not too far off), start with an approximate location if needed.
- Long baseline/poor observation environment:
  - Obstruction/multipath leads to unstable fixes. Fix: improve antenna environment; choose a closer base or VRS.
- FC parameters/firmware:
  - GPS Inject not enabled or mismatched baud rates. Fix: follow FC documentation to verify settings.

## Notes
- The LoRa module must be in transparent pass-through mode, and the baud rate must match the program.
- For ArduPilot, ensure `SERIALx_BAUD`, `SERIALx_PROTOCOL=5 (GPS)`, and connect to the correct GPS port.
- Ensure the LoRa frequency band and TX power comply with local regulations.

## License
MIT
