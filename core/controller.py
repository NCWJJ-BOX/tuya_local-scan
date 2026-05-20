"""
Device Controller — handles all direct communication with Tuya devices over LAN.
Wraps tinytuya device objects with connection pooling and error handling.
"""

import tinytuya
import threading
import time

# Connection cache: device_id -> (device_obj, last_used_timestamp)
_device_cache: dict[str, tuple] = {}
_cache_lock = threading.Lock()
CACHE_TTL = 300  # 5 minutes


def _get_tinytuya_device(dev_info: dict):
    """
    Get or create a tinytuya device instance.
    Picks the right device class based on type.
    """
    dev_id = dev_info["id"]
    now = time.time()

    with _cache_lock:
        if dev_id in _device_cache:
            obj, ts = _device_cache[dev_id]
            if now - ts < CACHE_TTL:
                _device_cache[dev_id] = (obj, now)
                return obj
            # Stale — recreate
            del _device_cache[dev_id]

    dev_type = dev_info.get("type", "switch")
    ip = dev_info["ip"]
    local_key = dev_info["local_key"]
    version = float(dev_info.get("version", "3.3"))

    if dev_type == "light":
        d = tinytuya.BulbDevice(dev_id, ip, local_key)
    elif dev_type == "cover":
        d = tinytuya.CoverDevice(dev_id, ip, local_key) if hasattr(tinytuya, 'CoverDevice') else tinytuya.Device(dev_id, ip, local_key)
    else:
        d = tinytuya.OutletDevice(dev_id, ip, local_key)

    d.set_version(version)
    d.set_socketPersistent(True)
    d.set_socketTimeout(5)

    with _cache_lock:
        _device_cache[dev_id] = (d, now)

    return d


def get_status(dev_info: dict) -> dict:
    """Get full device status (all DPS values)."""
    try:
        d = _get_tinytuya_device(dev_info)
        data = d.status()
        if data and "dps" in data:
            return {"success": True, "dps": data["dps"], "online": True}
        if data and "Error" in data:
            return {"success": False, "error": data["Error"], "online": False}
        return {"success": False, "error": "No response", "online": False}
    except Exception as e:
        return {"success": False, "error": str(e), "online": False}


def turn_on(dev_info: dict, switch_id: int = 1) -> dict:
    """Turn device ON (DPS switch_id = True)."""
    try:
        d = _get_tinytuya_device(dev_info)
        d.turn_on(switch=switch_id)
        return {"success": True, "action": "on", "switch": switch_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


def turn_off(dev_info: dict, switch_id: int = 1) -> dict:
    """Turn device OFF (DPS switch_id = False)."""
    try:
        d = _get_tinytuya_device(dev_info)
        d.turn_off(switch=switch_id)
        return {"success": True, "action": "off", "switch": switch_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_value(dev_info: dict, dps_id: str, value) -> dict:
    """Set a specific DPS value."""
    try:
        d = _get_tinytuya_device(dev_info)
        d.set_value(int(dps_id), value)
        return {"success": True, "dps_id": dps_id, "value": value}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_colour(dev_info: dict, r: int, g: int, b: int) -> dict:
    """Set bulb color (RGB). Only works with BulbDevice."""
    try:
        d = _get_tinytuya_device(dev_info)
        if isinstance(d, tinytuya.BulbDevice):
            d.set_colour(r, g, b)
            return {"success": True, "color": {"r": r, "g": g, "b": b}}
        return {"success": False, "error": "Device is not a bulb"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_brightness(dev_info: dict, brightness: int) -> dict:
    """Set bulb brightness (10-1000). Only works with BulbDevice."""
    try:
        d = _get_tinytuya_device(dev_info)
        if isinstance(d, tinytuya.BulbDevice):
            d.set_brightness(brightness)
            return {"success": True, "brightness": brightness}
        return {"success": False, "error": "Device is not a bulb"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_colour_temp(dev_info: dict, temp: int) -> dict:
    """Set bulb color temperature (0-1000). Only works with BulbDevice."""
    try:
        d = _get_tinytuya_device(dev_info)
        if isinstance(d, tinytuya.BulbDevice):
            d.set_colourtemp(temp)
            return {"success": True, "colour_temp": temp}
        return {"success": False, "error": "Device is not a bulb"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def toggle(dev_info: dict, switch_id: int = 1) -> dict:
    """Toggle device state."""
    status = get_status(dev_info)
    if not status.get("success"):
        return status

    dps = status.get("dps", {})
    current = dps.get(str(switch_id), dps.get(switch_id, None))

    if current is None:
        return {"success": False, "error": f"DPS {switch_id} not found"}

    if current:
        return turn_off(dev_info, switch_id)
    else:
        return turn_on(dev_info, switch_id)


def clear_cache(device_id: str = None):
    """Clear device connection cache."""
    with _cache_lock:
        if device_id:
            _device_cache.pop(device_id, None)
        else:
            _device_cache.clear()
