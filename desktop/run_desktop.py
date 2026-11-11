# run_desktop.py — peluncur BPHUB edisi desktop (Windows/Linux/macOS).
#
# Cara pakai:
#   pip install -r requirements.txt
#   playwright install chromium
#   python desktop/run_desktop.py
#
# Peluncur ini menaruh folder desktop/ PALING DEPAN di sys.path supaya
# `from playwright_termux import Chromium` di adapter mengimpor
# jembatan desktop, lalu menjalankan app.py apa adanya. Server hidup
# di http://127.0.0.1:5049 dan browser default dibuka otomatis.
import os
import runpy
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.chdir(ROOT)


def _open_browser():
    time.sleep(1.5)
    try:
        webbrowser.open("http://127.0.0.1:5049/")
    except Exception:
        pass


threading.Thread(target=_open_browser, daemon=True).start()
runpy.run_path(os.path.join(ROOT, "app.py"), run_name="__main__")
