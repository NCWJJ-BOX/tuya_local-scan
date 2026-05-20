#!/usr/bin/env python3
"""
Tuya Realtime Monitor — local LAN polling with parallel persistent connections.
Usage: python monitor.py [interval_seconds]
"""

import json
import os
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import tinytuya

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DP_SWITCH = "1"
DP_ENERGY = "17"
DP_CURRENT = "18"
DP_POWER = "19"
DP_VOLTAGE = "20"


def load_devices():
    """Load device list from cloud API using config credentials."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    cloud_cfg = config["tuya_cloud"]
    cloud = tinytuya.Cloud(
        apiRegion=cloud_cfg["api_region"],
        apiKey=cloud_cfg["api_key"],
        apiSecret=cloud_cfg["api_secret"],
    )

    devices = cloud.getdevices()
    result = []
    for dev in devices:
        result.append({
            "name": dev["name"],
            "dev_id": dev["id"],
            "key": dev["key"],
            "ip": None,
            "category": dev.get("category", ""),
        })
    return result


def resolve_ips(devices):
    """Resolve device IPs via LAN scan."""
    scanned = tinytuya.deviceScan(verbose=False, maxretry=2)
    id_to_ip = {}
    for ip, info in scanned.items():
        gw = info.get("id", "")
        if gw:
            id_to_ip[gw] = ip

    for dev in devices:
        if dev["dev_id"] in id_to_ip:
            dev["ip"] = id_to_ip[dev["dev_id"]]
    return devices


def connect(devices):
    """Create persistent connections to all devices."""
    conns = []
    for dev in devices:
        if not dev["ip"]:
            continue
        d = tinytuya.OutletDevice(
            dev_id=dev["dev_id"],
            address=dev["ip"],
            local_key=dev["key"],
            version=3.5,
            persist=True,
        )
        d.set_socketTimeout(3)
        conns.append((dev, d))
    for dev, d in conns:
        try:
            d.status()
        except Exception:
            pass
    return conns


def poll_one(item):
    dev, d = item
    try:
        data = d.status()
        return {"dev": dev, "dps": data.get("dps", {}), "ok": True}
    except Exception as e:
        return {"dev": dev, "dps": {}, "ok": False, "err": str(e)}


def display(results, elapsed_ms):
    now = datetime.now().strftime("%H:%M:%S")
    print("\033[2J\033[H", end="")
    print(f"  Tuya Realtime Monitor  |  {now}  |  {elapsed_ms:.0f}ms")
    print(f"  {'='*60}")

    total_w = 0
    for r in results:
        dev = r["dev"]
        dps = r["dps"]
        sw = dps.get(DP_SWITCH, False)
        status = "ON" if sw else "OFF"
        online = "OK" if r["ok"] else f"ERR: {r.get('err', '')}"
        has_meter = dev["category"] == "cz"

        print(f"\n  [{dev['name']}] {dev['ip']}  —  {status}  ({online})")

        if has_meter and sw:
            power = dps.get(DP_POWER, 0) / 10
            voltage = dps.get(DP_VOLTAGE, 0) / 10
            current = dps.get(DP_CURRENT, 0)
            energy = dps.get(DP_ENERGY, 0)
            total_w += power
            print(f"    Power:    {power:>8.1f} W")
            print(f"    Voltage:  {voltage:>8.1f} V")
            print(f"    Current:  {current:>8d} mA")
            print(f"    Energy:   {energy:>8d} Wh")

    print(f"\n  {'='*60}")
    print(f"  Total power:  {total_w:.1f} W")
    print(f"  Press Ctrl+C to stop")


def main():
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0

    print("Loading devices from cloud...")
    devices = load_devices()
    print(f"Found {len(devices)} devices, resolving IPs...")

    devices = resolve_ips(devices)
    online = [d for d in devices if d["ip"]]
    print(f"{len(online)} devices online, connecting...")

    conns = connect(devices)
    pool = ThreadPoolExecutor(max_workers=len(conns))
    print(f"Monitoring {len(conns)} devices (interval={interval}s)\n")

    try:
        while True:
            t0 = time.monotonic()
            results = list(pool.map(poll_one, conns))
            elapsed = (time.monotonic() - t0) * 1000
            display(results, elapsed)
            time.sleep(max(0, interval - elapsed / 1000))
    except KeyboardInterrupt:
        pool.shutdown(wait=False)
        print("\nStopped.")


if __name__ == "__main__":
    main()
