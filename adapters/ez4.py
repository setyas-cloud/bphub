# Adapter bphub: EZ4 (ez4short.com) — transplant verbatim dari generate_events() app.py modul ez4 (port asli 5011).
# Mesin: HTTP murni requests + BeautifulSoup. Interface: resolve(url) -> event seragam.
import re
import time
import json
import base64
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

def _raw_events(raw_url):
    def emit(msg, color='#38bdf8'):
        payload = json.dumps({'status': 'log', 'message': msg, 'color': color})
        return f"data: {payload}\n\n"

    yield emit("Inisialisasi sesi penjelajah...", "#c084fc")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36",
        "Referer": "https://www.google.com/"
    })

    slug_match = re.search(r'(?:link=|ez4short\.com/)([a-zA-Z0-9_-]+)', raw_url)
    slug = slug_match.group(1) if slug_match else None

    if not slug:
        yield f"data: {json.dumps({'status': 'error', 'message': 'Slug tautan tidak valid!'})}\n\n"
        return

    yield emit(f"Slug kunci teridentifikasi: {slug}", "#facc15")

    # POS 1: tech8s.net
    yield emit("[Pos 1] Mengunjungi decoy blog tech8s.net...", "#60a5fa")
    try:
        safe1_url = f"https://tech8s.net/safe.php?link={slug}"
        res_safe1 = session.get(safe1_url, timeout=15)

        art1_url = None
        g_match = re.findall(r'url=(https://tech8s\.net/[^&"\']+)', res_safe1.text)
        if g_match:
            art1_url = unquote(g_match[0])
        else:
            d_match = re.findall(r'https://tech8s\.net/[a-zA-Z0-9\-_]+/', res_safe1.text)
            art1_url = d_match[0] if d_match else res_safe1.url

        yield emit(f"[Pos 1] Halaman artikel: {art1_url[:40]}...", "#94a3b8")
        session.get(art1_url, timeout=15)

        yield emit("[Pos 1] Bypass timer 8 detik (POST Form)...", "#f472b6")
        res_pos1 = session.post(art1_url, data={"newwpsafelink": slug}, timeout=15)
        soup1 = BeautifulSoup(res_pos1.text, "html.parser")

        next_link = None
        for a in soup1.find_all("a", href=True):
            if "safe.php?link=" in a['href'] or "game5s.com" in a['href']:
                next_link = a['href']
                break

        if not next_link:
            yield f"data: {json.dumps({'status': 'error', 'message': 'Tiket Pos 2 tidak ditemukan di Pos 1!'})}\n\n"
            return

        yield emit("[Pos 1] Berhasil ditembus! Tiket Pos 2 siap.", "#10b981")
    except Exception as e:
        yield f"data: {json.dumps({'status': 'error', 'message': f'Kendala Pos 1: {str(e)}'})}\n\n"
        return

    # POS 2: game5s.com
    yield emit("[Pos 2] Mengunjungi decoy blog game5s.com...", "#c084fc")
    try:
        res_safe2 = session.get(next_link, timeout=15)
        art2_url = None

        bing_match = re.search(r'[?&]u=a1([a-zA-Z0-9_-]+)', res_safe2.text)
        if bing_match:
            b64_str = bing_match.group(1)
            b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
            art2_url = base64.b64decode(b64_str).decode('utf-8', errors='ignore')
        else:
            g2_match = re.findall(r'url=(https://game5s\.com/[^&"\']+)', res_safe2.text)
            art2_url = unquote(g2_match[0]) if g2_match else res_safe2.url

        yield emit(f"[Pos 2] Halaman artikel: {art2_url[:40]}...", "#94a3b8")
        session.get(art2_url, timeout=15)

        yield emit("[Pos 2] Bypass timer 8 detik (POST Form)...", "#f472b6")
        res_pos2 = session.post(art2_url, data={"newwpsafelink": slug}, timeout=15)
        soup2 = BeautifulSoup(res_pos2.text, "html.parser")

        ez_target = None
        for a in soup2.find_all("a", href=True):
            if "ez4short.com" in a['href'] and slug in a['href']:
                ez_target = a['href']
                break
        if not ez_target:
            ez_target = f"https://ez4short.com/{slug}"

        yield emit("[Pos 2] Berhasil ditembus! Menuju Gerbang Akhir.", "#10b981")
    except Exception as e:
        yield f"data: {json.dumps({'status': 'error', 'message': f'Kendala Pos 2: {str(e)}'})}\n\n"
        return

    # POS FINAL: ez4short.com
    yield emit("[Final] Mengunjungi gerbang utama ez4short.com...", "#fb7185")
    try:
        session.headers.update({"Referer": art2_url})
        res_ez = session.get(ez_target, timeout=15)
        soup_ez = BeautifulSoup(res_ez.text, "html.parser")
        form = soup_ez.find("form", id="go-link")

        if not form:
            yield f"data: {json.dumps({'status': 'error', 'message': 'Formulir go-link tidak ditemukan!'})}\n\n"
            return

        payload = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}

        for s in range(5, 0, -1):
            yield emit(f"⏳ Cooldown sistem AdLinkFly: {s} detik...", "#facc15")
            time.sleep(1)

        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": "https://ez4short.com",
            "Referer": ez_target
        }
        csrf_cookie = session.cookies.get("csrfToken")
        if csrf_cookie:
            headers["X-CSRF-Token"] = csrf_cookie

        yield emit("[Final] Menembakkan AJAX POST ke /links/go...", "#38bdf8")
        res_final = session.post("https://ez4short.com/links/go", data=payload, headers=headers, timeout=15)
        data = res_final.json()

        if data.get("status") == "success" and data.get("url"):
            final_link = data['url']
            yield emit(f"Sukses besar! Tautan akhir didapatkan.", "#10b981")
            yield f"data: {json.dumps({'status': 'success', 'url': final_link})}\n\n"
        else:
            yield f"data: {json.dumps({'status': 'error', 'message': data.get('message', 'Gagal memproses URL')})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'status': 'error', 'message': f'Kendala Final: {str(e)}'})}\n\n"

# --- bphub: penormal dialek ez4 ({status,message,color} / {status,url}) -> event seragam ---
def resolve(target_url):
    """Interface seragam bphub: generator event {type,msg,level,url}."""
    try:
        for chunk in _raw_events(target_url):
            s = chunk.strip()
            if not s.startswith("data:"):
                continue
            try:
                d = json.loads(s[5:].strip())
            except Exception:
                continue
            st = d.get("status")
            if st == "success":
                yield {"type": "result", "url": d.get("url", "")}
            elif st == "error":
                yield {"type": "error", "msg": d.get("message", "Gagal tanpa pesan.")}
            else:
                yield {"type": "log", "msg": d.get("message", ""), "level": "info"}
    except Exception as e:
        yield {"type": "error", "msg": f"Kendala eksekusi adapter: {type(e).__name__}: {e}"}
