# Adapter bphub: CUTY (cuty.io) — transplant verbatim dari app_cuty.py modul cuty (port asli 5020).
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
    start_time = time.time()

    try:
        with Chromium(headless=True) as browser:
            page = browser.new_page()

            yield send("Menavigasi ke halaman safelink...", "info")
            try:
                page.goto(target_url, timeout=25000)
            except Exception:
                pass
            time.sleep(1.5)

            # Step 1: Inisialisasi Tombol Continue
            yield send("Memicu verifikasi Step 1 (#submit-button)...", "info")
            page.evaluate("""
            () => {
                const b = document.querySelector('#submit-button');
                if (b && !b.disabled) b.click();
            }
            """)

            # Step 2: Auto-solve Cloudflare Turnstile
            yield send("Menunggu Cloudflare Turnstile diselesaikan...", "warn")
            token_found = False
            for sec in range(1, 30):
                time.sleep(1)
                try:
                    status = page.evaluate("""
                    () => {
                        const t = document.querySelector('input[name="cf-turnstile-response"]');
                        const b = document.querySelector('#submit-button');
                        return {
                            len: t && t.value ? t.value.length : 0,
                            ready: b ? !b.disabled : false
                        };
                    }
                    """)
                    if status and status.get('len', 0) > 50 and status.get('ready', False):
                        yield send(f"Turnstile Lolos ({status['len']} karakter token) pada detik ke-{sec}!", "success")
                        token_found = True
                        break
                except:
                    pass

            if not token_found:
                yield send("Turnstile gagal diselesaikan atau batas waktu habis.", "error")
                return

            # Step 3: Membersihkan Overlay & Eksekusi Verifikasi
            yield send("Membersihkan layer overlay iklan & memicu Step 2...", "info")
            page.evaluate("""
            () => {
                const o = document.querySelector('#rcuba6n, [style*="2147483647"]');
                if (o) o.remove();
                const b = document.querySelector('#submit-button');
                if (b) b.click();
            }
            """)
            time.sleep(3)

            # Step 4: Memantau Siklus Hitung Mundur & Tombol Go
            yield send("Mengawal timer sesi dan menunggu tombol 'Go' aktif...", "info")
            clicked_go = False

            for loop in range(1, 35):
                time.sleep(1)
                try:
                    res = page.evaluate("""
                    () => {
                        const o = document.querySelector('#rcuba6n, [style*="2147483647"]');
                        if (o) o.remove();

                        const timerEl = document.querySelector('#timer, .timer');
                        const t = timerEl ? timerEl.innerText.trim() : '';

                        const cands = document.querySelectorAll(
                          '#submit-button, .get-link, button[type="submit"], a[href*="/go/"], form[action*="/go/"] button, form[action*="/go/"] a');
                        const texts = [];
                        for (const b of cands) {
                            const text = (b.innerText || b.value || '').trim();
                            if (text) texts.push(text);
                            const tl = text.toLowerCase();
                            const isGo = tl === 'go' || tl.startsWith('go ') ||
                                         tl.startsWith('go>') || tl.includes('get link');
                            if (isGo && !b.disabled) {
                                b.click();
                                return { clicked: true, text: text, timer: t };
                            }
                        }
                        return { clicked: false, text: texts.join(' | '), timer: t };
                    }
                    """)

                    if res:
                        t_val = res.get('timer')
                        btn_txt = res.get('text')
                        if t_val:
                            yield send(f"Timer berjalan: {t_val} | Status tombol: {btn_txt or 'Menunggu'}", "info")

                        if res.get("clicked"):
                            yield send(f"Jackpot! Tombol '{btn_txt}' berhasil disambar!", "success")
                            clicked_go = True
                            time.sleep(6)
                            break
                except:
                    pass

            if not clicked_go:
                yield send("Tombol 'Go' tidak sempat terpicu atau waktu habis.", "error")
                return

            # Step 5: Menangkap Pengalihan URL Tujuan Akhir
            yield send("Memindai rute pengalihan ke URL tujuan akhir...", "warn")
            for _ in range(12):
                time.sleep(1)
                try:
                    real_url = page.evaluate("() => location.href")
                    if (real_url and 
                        "about:blank" not in real_url and 
                        "cutty.io" not in real_url and 
                        "cuttty.com" not in real_url and 
                        "cuty.io" not in real_url):
                        yield send(f"Eksploitasi tuntas ({time.time() - start_time:.1f}s)!", "success")
                        yield f"data: {json.dumps({'type': 'result', 'url': real_url})}\n\n"
                        return
                except:
                    pass

            yield send("Gagal menangkap pengalihan URL tujuan akhir.", "error")

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
