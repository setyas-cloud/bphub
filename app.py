#!/usr/bin/env python3
"""BPHUB — Bypass Hub: gabungan 6 modul bypass Termux Command Center.

Satu server, satu port (5049), enam adapter:
  cuty (Cuty.io) - shrme (ShrinkMe) - srnky (ShrinkEarn)
  ez4 (Ez4short) - dplink (DropLink) - clk (clk.sh)

Alur: tempel link (boleh banyak & campur layanan) -> hub mengenali
domainnya -> adapter yang cocok memproses -> SSE event seragam:
  {"type":"log","msg":...,"level":...,"service":...}
  {"type":"result","url":...,"service":...}
  {"type":"error","msg":...,"service":...}
"""
import importlib
import json
import time
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, render_template, request

from adapters import SERVICES

app = Flask(__name__)
PORT = 5049

_adapters = {}
_adapter_errors = {}


def load_adapter(name):
    """Impor adapter saat dibutuhkan; kegagalan satu adapter tidak
    menjatuhkan hub (adapter lain tetap bisa dipakai)."""
    if name in _adapters:
        return _adapters[name]
    if name in _adapter_errors:
        return None
    try:
        mod = importlib.import_module(f"adapters.{name}")
        _adapters[name] = mod
        return mod
    except Exception as e:  # dependensi adapter belum ada di perangkat
        _adapter_errors[name] = f"{type(e).__name__}: {e}"
        return None


def detect_service(raw_url):
    """Kenali layanan dari host URL. Kembalikan key adapter atau None."""
    value = (raw_url or "").strip()
    if not value:
        return None
    if "://" not in value:
        value = "https://" + value
    host = (urlparse(value).hostname or "").lower()
    if not host:
        return None
    for name, meta in SERVICES.items():
        for domain in meta["hosts"]:
            if host == domain or host.endswith("." + domain):
                return name
    return None


def sse(event):
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def api_health():
    services = {}
    for name, meta in SERVICES.items():
        mod = load_adapter(name)
        services[name] = {
            "label": meta["label"],
            "hosts": meta["hosts"],
            "ready": mod is not None,
            "error": _adapter_errors.get(name),
        }
    return jsonify({
        "status": "ok",
        "service": "BPHUB",
        "port": PORT,
        "time": time.strftime("%H:%M:%S"),
        "services": services,
    })


@app.route("/api/detect")
def api_detect():
    url = request.args.get("url", "")
    name = detect_service(url)
    return jsonify({
        "url": url,
        "service": name,
        "label": SERVICES[name]["label"] if name else None,
    })


@app.route("/stream")
def stream():
    target_url = request.args.get("url", "").strip()
    override = request.args.get("service", "").strip().lower()

    def generate():
        if not target_url:
            yield sse({"type": "error", "msg": "URL target tidak boleh kosong!", "service": None})
            return
        name = override if override in SERVICES else detect_service(target_url)
        if not name:
            yield sse({
                "type": "error",
                "msg": "Domain tidak dikenali. Pilih layanannya manual atau periksa link-nya.",
                "service": None,
            })
            return
        label = SERVICES[name]["label"]
        yield sse({
            "type": "log",
            "msg": f"[BPHUB] Layanan terdeteksi: {label} ({name}) — memproses {target_url}",
            "level": "info",
            "service": name,
        })
        mod = load_adapter(name)
        if mod is None:
            yield sse({
                "type": "error",
                "msg": f"Adapter {label} belum siap di perangkat ini: {_adapter_errors.get(name)}",
                "service": name,
            })
            return
        agen = None
        selesai = False
        try:
            agen = mod.resolve(target_url)
            for event in agen:
                event = dict(event)
                event.setdefault("service", name)
                yield sse(event)
                if event.get("type") in ("result", "error"):
                    selesai = True
                    break
        except Exception as e:
            yield sse({
                "type": "error",
                "msg": f"Kendala eksekusi hub: {type(e).__name__}: {e}",
                "service": name,
            })
            selesai = True
        finally:
            # Tutup generator adapter secara eksplisit & senyap: sisa
            # generator yang dibiarkan menggantung memicu
            # "RuntimeError: generator ignored GeneratorExit" di log
            # (adapter browser punya bare-except di loop polling-nya).
            if agen is not None:
                try:
                    agen.close()
                except Exception:
                    pass
        if not selesai:
            yield sse({
                "type": "error",
                "msg": "Proses selesai tanpa hasil (adapter berhenti tanpa event penutup).",
                "service": name,
            })

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    print("=" * 60)
    print("BPHUB - Bypass Hub Aktif! (Port 5049)")
    print("Buka di browser: http://127.0.0.1:5049")
    print("Layanan: " + " - ".join(m["label"] for m in SERVICES.values()))
    print("=" * 60)
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
