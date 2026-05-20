"""
Tuya Local Control — Flask Web Server + SocketIO
Main entry point. Run: python app.py
"""

import json
import os
import threading
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from core import scanner, controller

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.config["SECRET_KEY"] = "tuya-local-control-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ───── Pages ─────

@app.route("/")
def index():
    return render_template("index.html")


# ───── API: Devices ─────

@app.route("/api/devices", methods=["GET"])
def api_get_devices():
    devices = scanner.load_devices()
    return jsonify({"success": True, "devices": devices})


@app.route("/api/devices/<device_id>", methods=["GET"])
def api_get_device(device_id):
    devices = scanner.load_devices()
    dev = next((d for d in devices if d["id"] == device_id), None)
    if not dev:
        return jsonify({"success": False, "error": "Device not found"}), 404
    return jsonify({"success": True, "device": dev})


@app.route("/api/devices/<device_id>", methods=["PATCH"])
def api_update_device(device_id):
    """Update device metadata (name, type, local_key)."""
    devices = scanner.load_devices()
    dev = next((d for d in devices if d["id"] == device_id), None)
    if not dev:
        return jsonify({"success": False, "error": "Device not found"}), 404

    data = request.get_json()
    for key in ["name", "type", "local_key", "ip", "version"]:
        if key in data:
            dev[key] = data[key]

    scanner.save_devices(devices)
    socketio.emit("device_updated", dev)
    return jsonify({"success": True, "device": dev})


@app.route("/api/devices/<device_id>", methods=["DELETE"])
def api_delete_device(device_id):
    devices = scanner.load_devices()
    devices = [d for d in devices if d["id"] != device_id]
    scanner.save_devices(devices)
    controller.clear_cache(device_id)
    socketio.emit("device_removed", {"id": device_id})
    return jsonify({"success": True})


# ───── API: Scanning ─────

@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Start a LAN scan in background thread, emit results via SocketIO."""
    maxretry = CONFIG.get("scan", {}).get("max_retries", 3)

    def _do_scan():
        socketio.emit("scan_started")
        try:
            found = scanner.scan_network(maxretry=maxretry)
            existing = scanner.load_devices()
            merged = scanner.merge_scan_results(existing, found)
            scanner.save_devices(merged)
            socketio.emit("scan_complete", {
                "found": len(found),
                "total": len(merged),
                "devices": merged
            })
        except Exception as e:
            socketio.emit("scan_error", {"error": str(e)})

    t = threading.Thread(target=_do_scan, daemon=True)
    t.start()
    return jsonify({"success": True, "message": "Scan started"})


# ───── API: Import wizard JSON ─────

@app.route("/api/import", methods=["POST"])
def api_import():
    """Import devices from tinytuya wizard JSON (uploaded file or path)."""
    if "file" in request.files:
        file = request.files["file"]
        import tempfile
        tmp = os.path.join(os.path.dirname(__file__), "data", "_import_tmp.json")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        file.save(tmp)
        filepath = tmp
    elif request.json and "path" in request.json:
        filepath = request.json["path"]
    else:
        return jsonify({"success": False, "error": "No file provided"}), 400

    try:
        imported = scanner.import_tinytuya_json(filepath)
        existing = scanner.load_devices()
        merged = scanner.merge_scan_results(existing, imported)
        scanner.save_devices(merged)
        socketio.emit("devices_imported", {
            "imported": len(imported),
            "total": len(merged),
            "devices": merged
        })
        return jsonify({"success": True, "imported": len(imported), "total": len(merged)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ───── API: Device Control ─────

def _find_device(device_id: str):
    devices = scanner.load_devices()
    return next((d for d in devices if d["id"] == device_id), None)


@app.route("/api/control/<device_id>/status", methods=["GET"])
def api_device_status(device_id):
    dev = _find_device(device_id)
    if not dev:
        return jsonify({"success": False, "error": "Device not found"}), 404
    if not dev.get("local_key"):
        return jsonify({"success": False, "error": "No local_key — import wizard JSON first"}), 400

    result = controller.get_status(dev)
    # Update stored DPS
    if result.get("success"):
        devices = scanner.load_devices()
        for d in devices:
            if d["id"] == device_id:
                d["dps"] = result.get("dps", {})
                d["online"] = True
                break
        scanner.save_devices(devices)
    return jsonify(result)


@app.route("/api/control/<device_id>/on", methods=["POST"])
def api_device_on(device_id):
    dev = _find_device(device_id)
    if not dev:
        return jsonify({"success": False, "error": "Device not found"}), 404
    switch_id = request.json.get("switch", 1) if request.json else 1
    result = controller.turn_on(dev, switch_id)
    socketio.emit("device_state_changed", {"id": device_id, "action": "on", "switch": switch_id})
    return jsonify(result)


@app.route("/api/control/<device_id>/off", methods=["POST"])
def api_device_off(device_id):
    dev = _find_device(device_id)
    if not dev:
        return jsonify({"success": False, "error": "Device not found"}), 404
    switch_id = request.json.get("switch", 1) if request.json else 1
    result = controller.turn_off(dev, switch_id)
    socketio.emit("device_state_changed", {"id": device_id, "action": "off", "switch": switch_id})
    return jsonify(result)


@app.route("/api/control/<device_id>/toggle", methods=["POST"])
def api_device_toggle(device_id):
    dev = _find_device(device_id)
    if not dev:
        return jsonify({"success": False, "error": "Device not found"}), 404
    switch_id = request.json.get("switch", 1) if request.json else 1
    result = controller.toggle(dev, switch_id)
    socketio.emit("device_state_changed", {"id": device_id, "result": result})
    return jsonify(result)


@app.route("/api/control/<device_id>/set", methods=["POST"])
def api_device_set(device_id):
    dev = _find_device(device_id)
    if not dev:
        return jsonify({"success": False, "error": "Device not found"}), 404
    data = request.get_json()
    dps_id = data.get("dps_id")
    value = data.get("value")
    if dps_id is None:
        return jsonify({"success": False, "error": "dps_id required"}), 400
    result = controller.set_value(dev, str(dps_id), value)
    return jsonify(result)


@app.route("/api/control/<device_id>/colour", methods=["POST"])
def api_device_colour(device_id):
    dev = _find_device(device_id)
    if not dev:
        return jsonify({"success": False, "error": "Device not found"}), 404
    data = request.get_json()
    r, g, b = data.get("r", 255), data.get("g", 255), data.get("b", 255)
    result = controller.set_colour(dev, r, g, b)
    return jsonify(result)


@app.route("/api/control/<device_id>/brightness", methods=["POST"])
def api_device_brightness(device_id):
    dev = _find_device(device_id)
    if not dev:
        return jsonify({"success": False, "error": "Device not found"}), 404
    data = request.get_json()
    brightness = data.get("brightness", 500)
    result = controller.set_brightness(dev, brightness)
    return jsonify(result)


# ───── SocketIO Events ─────

@socketio.on("connect")
def handle_connect():
    devices = scanner.load_devices()
    emit("init_devices", {"devices": devices})


@socketio.on("request_status")
def handle_request_status(data):
    device_id = data.get("id")
    dev = _find_device(device_id)
    if dev and dev.get("local_key"):
        result = controller.get_status(dev)
        emit("device_status", {"id": device_id, **result})
    else:
        emit("device_status", {"id": device_id, "success": False, "error": "Not configured"})


@socketio.on("request_all_status")
def handle_request_all_status():
    """Poll status of all devices with local_key configured."""
    devices = scanner.load_devices()
    for dev in devices:
        if dev.get("local_key"):
            result = controller.get_status(dev)
            emit("device_status", {"id": dev["id"], **result})


# ───── Main ─────

if __name__ == "__main__":
    server_cfg = CONFIG.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = server_cfg.get("port", 5000)
    debug = server_cfg.get("debug", True)

    print(f"\n  [*] Tuya Local Control Dashboard")
    print(f"  --> http://localhost:{port}")
    print(f"  --> http://0.0.0.0:{port}\n")

    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
