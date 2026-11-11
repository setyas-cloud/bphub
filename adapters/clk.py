# Adapter bphub: CLK (clk.sh / clksz.com) — transplant verbatim dari app.py modul clk (port asli 5019).
# Mesin: browser playwright_termux Chromium. Interface: resolve(url) -> event seragam.
import time
import json
import os
import threading

try:
    from playwright_termux import Chromium
except Exception:
    Chromium = None

def _raw_stream(target_url):
    def send(msg, level="info"):
        return f"data: {json.dumps({'type': 'log', 'msg': msg, 'level': level})}\n\n"

    yield send(f"Membuka target: {target_url}...", "info")

    try:
        with Chromium(headless=True) as browser:
            page = browser.new_page()

            try:
                page.goto(target_url, timeout=25000)
            except Exception:
                pass

            page.evaluate("document.cookie = 'ab=2; path=/; domain=clksz.com';")
            page.evaluate("window.open = () => null;")

            # Step 1: Validasi Cloudflare Turnstile
            yield send("Menunggu Cloudflare Turnstile diselesaikan...", "warn")
            ts_ok = False
            for _ in range(35):
                time.sleep(1)
                try:
                    ts = page.evaluate("() => { const el = document.querySelector('[name=\"cf-turnstile-response\"]'); return el && el.value ? el.value.length : 0; }")
                    if ts > 0:
                        yield send(f"Turnstile Lolos ({ts} karakter token)!", "success")
                        ts_ok = True
                        break
                except:
                    pass

            if not ts_ok:
                yield send("Turnstile gagal diverifikasi atau waktu habis.", "error")
                return

            # Step 2: Memicu form Step 1 (#continue)
            yield send("Memicu tombol verifikasi #continue...", "info")
            page.evaluate("""
            () => {
                window.open = () => null;
                const btn = document.querySelector('#continue') || document.querySelector('button[name="submit"]');
                if (btn) {
                    btn.disabled = false;
                    btn.click();
                }
            }
            """)

            # Step 3: Mengawal Pendaratan di Sponsor Pos 1
            time.sleep(4)
            current_url = page.evaluate("() => location.href")
            yield send(f"Mendarat di Pos 1: {current_url[:60]}...", "info")

            yield send("Menjalankan timer Pos 1 (15 detik)...", "info")
            for sec in range(15, 0, -3):
                yield send(f"Cooldown Pos 1: {sec}s tersisa...", "info")
                time.sleep(3)
                try: page.evaluate("() => 1")
                except: pass

            # Step 4: Menyerahkan Tiket Menuju Sponsor Pos 2
            yield send("Memicu tombol transisi menuju Sponsor Pos 2...", "warn")
            page.evaluate("""
            () => {
                window.open = () => null;
                const btn = document.querySelector('#getnewlink') || 
                            document.querySelector('#btn-main') || 
                            document.querySelector('.btn-captcha') || 
                            document.querySelector('form button[type="submit"]');
                const form = document.querySelector('#getmylink') || 
                             document.querySelector('form[action*="financeguidz"]') || 
                             document.querySelector('form');
                if (btn) btn.click();
                else if (form) form.requestSubmit ? form.requestSubmit() : HTMLFormElement.prototype.submit.call(form);
            }
            """)

            # Step 5: Mengawal Pendaratan di Sponsor Pos 2
            time.sleep(4)
            current_url2 = page.evaluate("() => location.href")
            yield send(f"Mendarat di Pos 2: {current_url2[:60]}...", "info")

            yield send("Menjalankan timer Pos 2 (15 detik)...", "info")
            for sec in range(15, 0, -3):
                yield send(f"Cooldown Pos 2: {sec}s tersisa...", "info")
                time.sleep(3)
                try: page.evaluate("() => 1")
                except: pass

            # Step 6: Menyerahkan Tiket Pos 2 untuk Pulang ke clksz.com
            yield send("Memicu tombol pengembalian sesi menuju domain utama...", "warn")
            page.evaluate("""
            () => {
                window.open = () => null;
                const btn = document.querySelector('#getnewlink') || 
                            document.querySelector('#nextpage button') ||
                            document.querySelector('form[action*="clksz"] button') ||
                            document.querySelector('form button[type="submit"]') ||
                            document.querySelector('.btn-captcha');
                const form = document.querySelector('#nextpage') || 
                             document.querySelector('form[action*="clksz"]') ||
                             document.querySelector('form[action*="clk"]');
                if (btn) btn.click();
                else if (form) form.requestSubmit ? form.requestSubmit() : HTMLFormElement.prototype.submit.call(form);
            }
            """)

            # Step 7: Menunggu Kepulangan ke clksz.com dan Memindai ad_form_data
            time.sleep(3)
            yield send("Menunggu kepulangan ke clksz.com & memindai ad_form_data...", "warn")
            ad_ok = False
            for _ in range(30):
                time.sleep(1)
                try:
                    curr = page.evaluate("() => location.href")
                    has_ad = page.evaluate("() => !!document.querySelector('input[name=\"ad_form_data\"]')")
                    if has_ad:
                        yield send("Jackpot! Token ad_form_data resmi ditemukan di clksz.com!", "success")
                        page.evaluate("""
                        () => {
                            window.open = () => null;
                            const f = document.querySelector('#go-link');
                            if (f) f.onsubmit = (e) => { if (e) e.preventDefault(); return false; };
                        }
                        """)
                        ad_ok = True
                        break
                except:
                    pass

            if not ad_ok:
                curr_fail = page.evaluate("() => location.href")
                yield send(f"Token ad_form_data belum ditemukan (URL saat ini: {curr_fail[:60]}...).", "error")
                return

            # Step 8: Cooldown Akhir Sebelum AJAX POST
            yield send("Menunggu cooldown final server (15 detik)...", "info")
            for sec in range(15, 0, -3):
                yield send(f"Cooldown akhir: {sec}s tersisa...", "info")
                time.sleep(3)
                try: page.evaluate("() => 1")
                except: pass

            # Step 9: Tembakan Pamungkas ke /links/go
            yield send("Menembakkan AJAX POST ke /links/go...", "warn")
            res_final = page.evaluate("""
            () => {
                const el = document.querySelector('input[name=\"ad_form_data\"]');
                const adData = el ? el.value : '';
                return fetch('/links/go', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: '_method=POST&ad_form_data=' + encodeURIComponent(adData)
                })
                .then(r => r.json())
                .catch(e => ({status: 'error', message: e.toString()}));
            }
            """)

            if res_final and res_final.get("status") == "success" and res_final.get("url"):
                final_url = res_final.get("url")
                yield f"data: {json.dumps({'type': 'result', 'url': final_url})}\n\n"
            else:
                err_msg = res_final.get("message") or res_final.get("error") or "Respons server kosong"
                yield f"data: {json.dumps({'type': 'error', 'msg': err_msg})}\n\n"

    except Exception as e:
        yield send(f"Kesalahan sistem peramban: {str(e)}", "error")

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
