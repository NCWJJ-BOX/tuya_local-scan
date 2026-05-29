# Tuya Local Scan

Local LAN control dashboard for Tuya smart home devices. Discover, monitor, and control Tuya devices over the network without cloud dependency.

## Features

- **LAN Discovery** — UDP broadcast scan for Tuya devices on local network
- **Cloud Key Sync** — Fetch device keys and metadata from Tuya Cloud API
- **Web Dashboard** — Flask + SocketIO real-time control interface
- **Device Control** — On/off, toggle, brightness, colour, colour temperature, arbitrary DPS
- **Power Monitor** — Terminal-based real-time polling for smart plugs (voltage, current, energy)
- **Connection Pool** — Persistent connections with 5-minute TTL cache
- **Device Types** — Auto-detect switch/light/cover/sensor/fan/lock

## Architecture

```
tuya_local-scan/
├── app.py              # Flask + SocketIO web server
├── monitor.py          # Terminal real-time power monitor
├── pull_keys.py        # Fetch device keys from Tuya Cloud
├── test_plug.py        # Quick device connectivity test
├── core/
│   ├── scanner.py      # LAN UDP discovery + cloud enrichment
│   └── controller.py   # Device control (tinytuya wrapper)
├── web/
│   ├── templates/      # HTML templates
│   └── static/         # CSS, JS
└── config.json         # Configuration (copy from config.json.example)
```

## Prerequisites

- Python 3.10+
- Tuya Cloud API credentials (from [iot.tuya.com](https://iot.tuya.com))

## Setup

```bash
pip install flask flask-socketio tinytuya

cp config.json.example config.json
# Edit config.json with your Tuya Cloud API credentials
```

## Configuration

`config.json`:

```json
{
    "tuya_cloud": {
        "api_region": "sg",
        "api_key": "YOUR_API_KEY",
        "api_secret": "YOUR_API_SECRET"
    },
    "server": {
        "host": "0.0.0.0",
        "port": 5000,
        "debug": true
    },
    "scan": {
        "timeout": 10,
        "max_retries": 3
    }
}
```

## Usage

### Web Dashboard

```bash
python app.py
# Open http://localhost:5000
```

### Terminal Power Monitor

```bash
python monitor.py [interval_seconds]
# Live polling of smart plug power readings
```

### Pull Cloud Keys

```bash
python pull_keys.py
# Saves device keys to data/cloud_devices.json
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/devices` | List all devices |
| GET | `/api/devices/:id` | Get device status |
| PUT | `/api/devices/:id` | Update device (on/off, DPS) |
| DELETE | `/api/devices/:id` | Remove device |
| POST | `/api/scan` | Trigger LAN scan |
| POST | `/api/import` | Import tinytuya wizard JSON |

## Notes

- Devices must be registered in Tuya Smart/Smart Life app first
- LAN control requires devices to be on the same network segment
- Cloud API keys are from Tuya IoT Platform (not the consumer app)
