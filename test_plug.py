import tinytuya
import json
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DEV_ID = "a3cdeab120fc305ab8pqmx"
DEV_IP = "192.168.0.242"
# Note: backtick ` not apostrophe ' as 4th char
DEV_KEY = "zVP`/8DAoV^K'5z("

print(f"[*] Smart Plug T @ {DEV_IP}")
print(f"[*] Key: {repr(DEV_KEY)} (len={len(DEV_KEY)})")

for ver in [3.5, 3.4, 3.3]:
    print(f"\n[*] Trying version {ver}...")
    d = tinytuya.OutletDevice(DEV_ID, DEV_IP, DEV_KEY)
    d.set_version(ver)
    d.set_socketTimeout(5)
    d.set_socketRetryLimit(1)
    result = d.status()
    print(f"    Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
    if result and "dps" in result:
        print(f"\n[+] SUCCESS with version {ver}!")
        break
    try:
        d.close()
    except:
        pass
