"""
LAN Device Scanner — discovers Tuya devices on the local network.
Uses tinytuya's built-in scanner + cloud key retrieval via wizard data.
"""

import json
import os
import threading
import tinytuya

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

def _get_cloud_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("tuya_cloud", {})
    except:
        return {}


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def scan_network(maxretry: int = 3) -> list[dict]:
    """
    Broadcast UDP scan for Tuya devices on the LAN.
    Returns list of discovered device dicts with ip, gwId, version, etc.
    """
    devices = tinytuya.deviceScan(verbose=False, maxretry=maxretry)
    
    # Try to fetch cloud data to get local_keys and names
    cloud_data = {}
    cloud_cfg = _get_cloud_config()
    api_key = cloud_cfg.get("api_key")
    api_secret = cloud_cfg.get("api_secret")
    api_region = cloud_cfg.get("api_region")
    
    if api_key and api_secret and api_region:
        try:
            print("[*] Fetching device metadata from Tuya Cloud...")
            c = tinytuya.Cloud(apiRegion=api_region, apiKey=api_key, apiSecret=api_secret)
            cloud_devices = c.getdevices()
            if cloud_devices:
                print(f"[*] Got {len(cloud_devices)} devices from Cloud")
                for cd in cloud_devices:
                    cloud_data[cd["id"]] = cd
            else:
                print("[!] Cloud returned empty device list")
        except Exception as e:
            try:
                print(f"[!] Failed to fetch cloud keys: {repr(e)}")
            except:
                pass

    result = []
    for dev_key, info in devices.items():
        real_id = info.get("gwId") or info.get("id") or dev_key
        cd = cloud_data.get(real_id, {})
        name = cd.get("name") or info.get("name") or f"Device_{real_id[:8]}"
        local_key = cd.get("key", "")
        product_id = cd.get("product_id") or info.get("productKey", "")
        mac = cd.get("mac", "")
        model = cd.get("model", "")
        category = cd.get("category", "")
        
        # Determine type
        dev_type = "unknown"
        if cd:
            dev_type = _guess_device_type(cd)
        
        result.append({
            "id": real_id,
            "ip": info.get("ip", dev_key),
            "version": str(info.get("version", "3.3")),
            "name": name,
            "product_id": product_id,
            "local_key": local_key,
            "type": dev_type if dev_type != "unknown" else "switch",
            "model": model,
            "category": category,
            "mac": mac,
            "dps": {},
            "online": True
        })
    return result


def load_devices() -> list[dict]:
    _ensure_data_dir()
    if not os.path.exists(DEVICES_FILE):
        return []
    with open(DEVICES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_devices(devices: list[dict]):
    _ensure_data_dir()
    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(devices, f, indent=2, ensure_ascii=False)


def merge_scan_results(existing: list[dict], scanned: list[dict]) -> list[dict]:
    """
    Merge scanned devices into existing list.
    Preserves local_key and custom names from existing entries.
    Updates IP and online status from scan.
    """
    existing_map = {d["id"]: d for d in existing}

    for dev in scanned:
        if dev["id"] in existing_map:
            old = existing_map[dev["id"]]
            old["ip"] = dev["ip"]
            old["version"] = dev["version"]
            old["online"] = True
            if not old.get("local_key"):
                old["local_key"] = dev.get("local_key", "")
        else:
            existing_map[dev["id"]] = dev

    # Mark devices not found in scan as offline
    scanned_ids = {d["id"] for d in scanned}
    for dev_id, dev in existing_map.items():
        if dev_id not in scanned_ids:
            dev["online"] = False

    return list(existing_map.values())


def import_tinytuya_json(filepath: str) -> list[dict]:
    """
    Import devices from a tinytuya wizard-generated devices.json.
    This file contains local_key which is essential for local control.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        raw = json.load(f)

    devices = []
    for entry in raw:
        devices.append({
            "id": entry.get("id", ""),
            "ip": entry.get("ip", ""),
            "version": str(entry.get("version", "3.3")),
            "name": entry.get("name", f"Device_{entry.get('id', 'unknown')[:8]}"),
            "product_id": entry.get("product_id", ""),
            "local_key": entry.get("key", ""),
            "type": _guess_device_type(entry),
            "dps": {},
            "online": False
        })
    return devices


def _guess_device_type(entry: dict) -> str:
    """Guess device type from category or name."""
    name = (entry.get("name", "") + entry.get("category", "")).lower()
    if any(k in name for k in ["switch", "plug", "outlet", "socket"]):
        return "switch"
    if any(k in name for k in ["light", "bulb", "lamp", "led"]):
        return "light"
    if any(k in name for k in ["cover", "curtain", "blind", "shade"]):
        return "cover"
    if any(k in name for k in ["sensor", "temp", "humidity", "motion"]):
        return "sensor"
    if any(k in name for k in ["fan"]):
        return "fan"
    if any(k in name for k in ["lock"]):
        return "lock"
    return "switch"  # Default to switch
