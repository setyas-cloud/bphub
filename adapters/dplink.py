# Adapter bphub: DPLINK (droplink.co) — transplant verbatim dari app.py modul dplink (port asli 5013).
# Mesin: HTTP murni curl_cffi + BeautifulSoup. Interface: resolve(url) -> event seragam.
from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import time
import json
from urllib.parse import urlparse, parse_qs, unquote

def sse_pack(event_type, msg="", url="", color=""):
    payload = {"type": event_type, "msg": msg, "url": url, "color": color}
    return f"data: {json.dumps(payload)}\n\n"


def _get_tahan(session, url, counter, tries=3):
    """GET dengan ulang otomatis bila koneksi tersendat/timeout.
    counter[0] bertambah tiap pengulangan, pemanggil yang melaporkan ke log."""
    last = None
    for attempt in range(tries):
        try:
            return session.get(url, allow_redirects=True)
        except Exception as e:
            last = e
            if attempt < tries - 1:
                counter[0] += 1
                time.sleep(2)
    raise last

def _raw_stream(target_url):
    if not target_url:
        yield sse_pack("error", msg="URL target tidak boleh kosong!")
        return

    session = requests.Session(impersonate="chrome120")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    try:
        yield sse_pack("log", f"[*] [POS 0] Membuka target: {target_url}...")
        _rt = [0]
        res_safe1 = _get_tahan(session, target_url, _rt)
        if _rt[0]:
            yield sse_pack("log", f"[!] [POS 0] Koneksi tersendat, berhasil pada percobaan ke-{_rt[0] + 1}.")

        redir1 = re.search(r'(?:window\.location\.href|location\.replace)\s*=\s*["\']([^"\']+)["\']', res_safe1.text)
        if not redir1:
            yield sse_pack("error", msg="Gagal mendeteksi pengalihan Safe Gate 1!")
            return

        art1_url = unquote(parse_qs(urlparse(redir1.group(1)).query).get('url', [redir1.group(1)])[0])
        yield sse_pack("log", f"[+] [POS 1] Mendarat di Decoy 1: {art1_url[:55]}...", color="#38bdf8")

        # Kunjungi Decoy 1
        session.headers.update({"Referer": "https://www.google.com/"})
        res_art1 = session.get(art1_url, allow_redirects=True)

        # Ekstrak TP2 Dinamis dari Tag Form HTML
        soup_art1 = BeautifulSoup(res_art1.text, "html.parser")
        tp2_input = soup_art1.find("input", {"name": "tp2"})
        if tp2_input and tp2_input.get("value"):
            tp2_val = tp2_input.get("value")
        else:
            tp2_match = re.search(r'link=([a-zA-Z0-9]+)', res_safe1.url) or re.search(r'droplink\.[^/]+/([a-zA-Z0-9]+)', target_url)
            tp2_val = tp2_match.group(1) if tp2_match else "hXT68"

        yield sse_pack("log", f"[*] [POS 1] Menembakkan POST tiket tp2='{tp2_val}'...")
        session.headers.update({"Referer": res_art1.url, "Origin": "https://tech8s.net"})
        res_art2 = session.post(res_art1.url, data={"tp2": tp2_val}, allow_redirects=True)

        soup_art2 = BeautifulSoup(res_art2.text, "html.parser")
        btn_god2 = soup_art2.find("a", id="go_d2")
        if not btn_god2:
            yield sse_pack("error", msg="Tombol estafet go_d2 di Pos 1 tidak ditemukan!")
            return

        safe2_url = btn_god2.get("href")
        yield sse_pack("log", f"[+] [POS 2] Menuju Safe Gate Pos 2: {safe2_url}...", color="#38bdf8")

        # Safe Gate 2 (game5s.com)
        session.headers.update({"Referer": res_art1.url})
        _rt = [0]
        res_safe2 = _get_tahan(session, safe2_url, _rt)
        if _rt[0]:
            yield sse_pack("log", f"[!] [POS 2] Koneksi tersendat, berhasil pada percobaan ke-{_rt[0] + 1}.")
        redir2 = re.search(r'(?:window\.location\.href|location\.replace)\s*=\s*["\']([^"\']+)["\']', res_safe2.text)
        if not redir2:
            yield sse_pack("error", msg="Gagal mendeteksi pengalihan Safe Gate 2!")
            return

        art2_url = unquote(parse_qs(urlparse(redir2.group(1)).query).get('url', [redir2.group(1)])[0])
        yield sse_pack("log", f"[*] [POS 2] Membuka Decoy 2: {art2_url[:55]}...")

        session.headers.update({"Referer": "https://www.google.com/"})
        res_decoy2 = session.get(art2_url, allow_redirects=True)

        soup_decoy2 = BeautifulSoup(res_decoy2.text, "html.parser")
        final_return_btn = soup_decoy2.find("a", id="go_d2")
        return_url = final_return_btn.get("href") if final_return_btn else target_url

        yield sse_pack("log", f"[+] [GERBANG UTAMA] Meluncur balik ke markas: {return_url}...", color="#38bdf8")
        session.headers.update({
            "Referer": res_decoy2.url,
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document"
        })
        _rt = [0]
        res_gate = _get_tahan(session, return_url, _rt)
        if _rt[0]:
            yield sse_pack("log", f"[!] [GERBANG UTAMA] Koneksi tersendat, berhasil pada percobaan ke-{_rt[0] + 1}.")

        # Ambil Payload Form #go-link
        soup_gate = BeautifulSoup(res_gate.text, "html.parser")
        form_go = soup_gate.find("form", id="go-link")
        if not form_go:
            yield sse_pack("error", msg="Form verifikasi go-link belum tersedia di gerbang utama!")
            return

        go_payload = {inp.get("name"): inp.get("value", "") for inp in form_go.find_all("input") if inp.get("name")}
        yield sse_pack("log", "[+] Form go-link diamankan! Sinkronisasi countdown server...", color="#38bdf8")

        # Cooldown Wajib 6 Detik Penuh untuk Mematahkan Proteksi CakePHP Bad Request
        for sec in range(6, 0, -1):
            yield sse_pack("log", f"    ⏳ Sinkronisasi countdown server: {sec} detik...")
            time.sleep(1.05)

        # Header AJAX Resmi
        ajax_headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": "https://droplink.co",
            "Referer": res_gate.url,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty"
        }
        csrf_token = go_payload.get("_csrfToken") or session.cookies.get("csrfToken")
        if csrf_token:
            ajax_headers["X-CSRF-Token"] = csrf_token

        yield sse_pack("log", "[*] Mengirim verifikasi final ke https://droplink.co/links/go...")
        res_final = session.post("https://droplink.co/links/go", data=go_payload, headers=ajax_headers)

        data = res_final.json()
        if data.get("status") == "success" and data.get("url"):
            yield sse_pack("done", msg="🎉 BYPASS SUKSES TOTAL! TAUTAN BERHASIL DIAMBIL!", url=data["url"])
        else:
            yield sse_pack("error", msg=f"Gagal mengambil tautan: {data.get('message', 'Format respon tidak dikenal')}")

    except Exception as e:
        yield sse_pack("error", msg=f"Kendala eksekusi: {str(e)}")

# --- bphub: penormal SSE asli -> event seragam ---
def _norm(raw_gen):
    import json as _json
    for chunk in raw_gen:
        s = chunk.strip()
        if not s.startswith("data:"):
            continue
        try:
            d = _json.loads(s[5:].strip())
        except Exception:
            continue
        t = d.get("type")
        if t == "result":
            yield {"type": "result", "url": d.get("url", "")}
        elif t == "error":
            yield {"type": "error", "msg": d.get("msg", "Gagal tanpa pesan.")}
        elif t == "done":
            yield {"type": "log", "msg": d.get("msg", ""), "level": "success"}
            yield {"type": "result", "url": d.get("url", "")}
        elif d.get("level") == "error":
            yield {"type": "error", "msg": d.get("msg", "")}
        else:
            yield {"type": "log", "msg": d.get("msg", ""), "level": d.get("level", "info")}

def resolve(target_url):
    """Interface seragam bphub: generator event {type,msg,level,url}."""
    try:
        yield from _norm(_raw_stream(target_url))
    except Exception as e:
        yield {"type": "error", "msg": f"Kendala eksekusi adapter: {type(e).__name__}: {e}"}
