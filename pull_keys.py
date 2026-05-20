"""
Pull real local_key from Tuya Cloud API
"""
import tinytuya
import json
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_KEY = "YOUR_API_KEY"
API_SECRET = "YOUR_API_SECRET"
API_REGION = "sg"

print("[*] Connecting to Tuya Cloud API (Singapore)...")
c = tinytuya.Cloud(
    apiRegion=API_REGION,
    apiKey=API_KEY,
    apiSecret=API_SECRET,
)

print("[*] Fetching device list...")
devices = c.getdevices()
print(f"[*] Got {len(devices) if devices else 0} devices")

# Write full data to file
output_path = os.path.join(os.path.dirname(__file__), "data", "cloud_devices.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(devices, f, indent=2, ensure_ascii=False)
print(f"[*] Saved to {output_path}")

# Print just the key info we need
for dev in devices:
    did = dev.get("id", "?")
    name = dev.get("name", "?")
    key = dev.get("key", "NO KEY")
    print(f"  [{did}] name={name}  local_key={key}")

print("\n[*] Done.")
