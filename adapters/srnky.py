# Adapter bphub: SRNKY (shrinkearn) — transplant verbatim dari app_shrinkearn.py modul srnky (port asli 5034).
# Mesin: browser playwright_termux Chromium. Interface: resolve(url) -> event seragam.
import time
import json

try:
    from playwright_termux import Chromium
except Exception:
    Chromium = None

def _raw_stream(target_url):
    def send(msg, level="info"):
        return f"data: {json.dumps({'type': 'log', 'msg': msg, 'level': level})}\n\n"

    yield send(f"Membuka target: {target_url}...", "info")

    with Chromium(headless=True) as browser:
        page = browser.new_page()

        # Step 1: Buka Halaman
        try:
            page.goto(target_url, timeout=20000)
        except Exception:
            pass

        page.evaluate("document.cookie = 'ab=2; path=/; domain=srnky.com';")
        page.evaluate("window.open = () => null;")

        # Step 2: Turnstile
        yield send("Menunggu Cloudflare Turnstile diselesaikan...", "warn")
        ts_ok = False
        for _ in range(30):
            time.sleep(1)
            try:
                ts = page.evaluate("() => { const el = document.querySelector('[name=\"cf-turnstile-response\"]'); return el && el.value ? el.value.length : 0; }")
                if ts > 0:
                    yield send(f"Turnstile Lolos ({ts} karakter token)!", "success")
                    ts_ok = True
                    break
            except: pass

        if not ts_ok:
            yield send("Turnstile gagal diselesaikan atau kehabisan waktu.", "error")
            return

        # Step 3: Klik Step 1
        yield send("Memicu tombol Step 1 menuju pos sponsor...", "info")
        page.evaluate("""
        () => {
            window.open = () => null;
            const btn = document.querySelector('#continue') || document.querySelector('button[type="submit"]');
            if (btn) btn.click();
        }
        """)

        # Step 4: Loanbixby Pos 1
        yield send("Mengawal pendaratan di Sponsor Pos 1...", "info")
        landed_pos1 = False
        for _ in range(25):
            time.sleep(1)
            try:
                if "loanbixby.com" in page.evaluate("() => location.href"):
                    yield send("Sukses mendarat di Sponsor Pos 1!", "success")
                    landed_pos1 = True
                    break
            except: pass

        if not landed_pos1:
            yield send("Gagal mendarat di Pos 1 (mungkin terkena pengalihan liar).", "error")
            return

        for sec in range(15, 0, -3):
            yield send(f"Timer Pos 1: berjalan mundur ({sec}s)...", "info")
            time.sleep(3)

        yield send("Menyerahkan form #getmylink menuju Pos 2...", "info")
        page.evaluate("""
        () => {
            window.open = () => null;
            const btn = document.querySelector('#getnewlink');
            const form = document.querySelector('#getmylink') || document.querySelector('form[action*="loanbixby"]');
            if (btn) btn.click();
            else if (form) form.requestSubmit ? form.requestSubmit() : HTMLFormElement.prototype.submit.call(form);
        }
        """)

        # Step 5: Loanbixby Pos 2
        yield send("Mengawal pendaratan di Sponsor Pos 2...", "info")
        landed_pos2 = False
        for _ in range(25):
            time.sleep(1)
            try:
                if page.evaluate("() => !!document.querySelector('#nextpage')"):
                    yield send("Form verifikasi #nextpage terdeteksi di Pos 2!", "success")
                    landed_pos2 = True
                    break
            except: pass

        if not landed_pos2:
            yield send("Form #nextpage tidak ditemukan di Pos 2.", "error")
            return

        for sec in range(15, 0, -3):
            yield send(f"Timer Pos 2: berjalan mundur ({sec}s)...", "info")
            time.sleep(3)

        yield send("Menyerahkan 5 tiket verifikasi sponsor kembali ke srnky.com...", "info")
        page.evaluate("""
        () => {
            window.open = () => null;
            const btn = document.querySelector('#getnewlink');
            const form = document.querySelector('#nextpage') || document.querySelector('form[action*="srnky"]');
            if (btn) btn.click();
            else if (form) form.requestSubmit ? form.requestSubmit() : HTMLFormElement.prototype.submit.call(form);
        }
        """)

        # Step 6: Final Page & ad_form_data
        yield send("Menunggu token ad_form_data dicetak server CakePHP...", "warn")
        ad_ok = False
        for _ in range(25):
            time.sleep(1)
            try:
                has_ad = page.evaluate("() => !!document.querySelector('input[name=\"ad_form_data\"]')")
                if has_ad:
                    yield send("Jackpot! Token rahasia ad_form_data resmi dilahirkan!", "success")
                    page.evaluate("""
                    () => {
                        window.open = () => null;
                        const f = document.querySelector('#go-link');
                        if (f) f.onsubmit = (e) => { if (e) e.preventDefault(); return false; };
                    }
                    """)
                    ad_ok = True
                    break
            except: pass

        if not ad_ok:
            yield send("Token ad_form_data gagal dimuat di halaman final.", "error")
            return

        yield send("Menunggu cooldown server 16 detik (dengan sinyal keep-alive)...", "info")
        for sec in range(16, 0, -2):
            yield send(f"Cooldown Akhir: {sec}s tersisa...", "info")
            time.sleep(2)
            try: page.evaluate("() => 1")
            except: pass

        yield send("Menembakkan permintaan AJAX POST ke /links/go...", "warn")
        res_final = page.evaluate("""
        () => {
            const el = document.querySelector('input[name="ad_form_data"]');
            const adData = el ? el.value : '';
            return fetch('/links/go', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: '_method=POST&ad_form_data=' + encodeURIComponent(adData)
            }).then(r => r.json()).catch(e => ({status: 'error', error: e.toString()}));
        }
        """)

        if res_final and res_final.get("status") == "success" and res_final.get("url"):
            final_url = res_final.get("url")
            yield f"data: {json.dumps({'type': 'result', 'url': final_url})}\n\n"
        else:
            err_msg = res_final.get("message") if res_final else "Respons tidak dikenal"
            yield f"data: {json.dumps({'type': 'error', 'msg': err_msg})}\n\n"

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
