# Adapter bphub: SHRME (shrinkme.click / shrinkme.io) — transplant verbatim dari app_shrinkme.py modul shrme (port asli 5035).
# Mesin: browser playwright_termux Chromium, emit-callback + thread/queue. Interface: resolve(url) -> event seragam.
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from urllib.parse import urlparse, urljoin

try:
    from playwright_termux import Chromium
except Exception:
    Chromium = None

ALLOWED_HOSTS = {
    "shrinkme.click", "www.shrinkme.click", "shrinkme.io", "www.shrinkme.io",
    "en.mrproblogger.com",
}
FINAL_HOST = "kenhlink.vip"
FINAL_PATH_RE = re.compile(r"^/notes/([A-Za-z0-9_-]+)/?$")


def emit_log(emit, msg, level="info", phase="", detail=False):
    stamp = time.strftime("%H:%M:%S")
    event = {"type": "log", "ts": stamp, "msg": str(msg),
             "level": level, "phase": phase}
    if detail:
        event["detail"] = True
    try:
        print(f"[{stamp}] [SHRME/{level.upper()}]" + (f" [{phase}]" if phase else "") + f" {msg}", flush=True)
    except Exception:
        pass
    emit(event)


def emit_detail(emit, msg, level="info", phase=""):
    """Baris detail internal: hanya tampil di UI bila mode debug aktif.

    Di mode default, hub (app.py) menahan event ini dari SSE; baris tetap
    tercatat di stdout/log server lokal untuk keperluan debug.
    """
    emit_log(emit, msg, level, phase, detail=True)


def emit_status(emit, state, label, stage=None):
    event = {"type": "status", "state": state, "label": label}
    if stage is not None:
        event["stage"] = stage
    emit(event)


def emit_error(emit, msg, code="RESOLVE_ERROR", phase="", url=""):
    emit_status(emit, "ERROR", "Terjadi kesalahan")
    emit_log(emit, f"{code}: {msg}", "error", phase)
    event = {"type": "error", "msg": str(msg), "code": code, "phase": phase}
    if url:
        # URL tujuan sempat tertangkap sebelum gagal: sertakan agar kartu
        # hasil tetap menampilkannya (dengan SALIN/BUKA).
        event["url"] = url
    emit(event)


def valid_target(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("Tempel URL ShrinkMe terlebih dahulu.")
    if "://" not in value:
        value = "https://shrinkme.click/" + value.strip("/")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        raise ValueError("Domain tidak dikenali. Gunakan URL shrinkme.click / shrinkme.io.")
    if not parsed.path.strip("/"):
        raise ValueError("Slug shortlink tidak ditemukan.")
    return value


def is_final_note_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (parsed.scheme == "https" and parsed.hostname == FINAL_HOST
                and FINAL_PATH_RE.fullmatch(parsed.path or "") is not None)
    except Exception:
        return False


def is_destination_url(url: str) -> bool:
    """URL tujuan akhir apa pun host-nya: cukup http(s) + hostname.

    Field `url` dari JSON /links/go sudah merupakan tautan tujuan akhir
    (file host mana pun) — tanpa asumsi host tertentu.
    """
    try:
        parsed = urlparse(url or "")
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except Exception:
        return False


def accept_captured_url(candidate: str) -> str:
    """Terima URL yang tertangkap dari /links/go sebagai hasil akhir.

    Kembalikan URL tujuan akhir, atau "" bila tidak ada yang bisa dipakai.
    Note kenhlink dinormalisasi seperti sebelumnya; URL lain (host apa pun)
    dipakai apa adanya.
    """
    candidate = (candidate or "").strip()
    if not candidate:
        return ""
    if is_final_note_url(candidate):
        parsed_candidate = urlparse(candidate)
        note_match = FINAL_PATH_RE.fullmatch(parsed_candidate.path or "")
        return f"https://{FINAL_HOST}/notes/{note_match.group(1)}"
    if is_destination_url(candidate):
        return candidate
    return ""


def inspect_page(page):
    return page.evaluate(r"""() => {
      const visible = (el) => {
        if (!el) return false;
        const s = getComputedStyle(el), r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
      };
      const controls = Array.from(document.querySelectorAll(
        'button, input[type="submit"], input[type="button"], a.btn, a.button, [role="button"]'
      )).filter(visible).map((el, i) => ({
        index: i,
        tag: el.tagName.toLowerCase(),
        id: el.id || '',
        text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 140),
        disabled: !!el.disabled
      }));
      const cf = document.querySelector('[name="cf-turnstile-response"]');
      const form = document.querySelector('#link-view, #go-link, form');
      const av = window.app_vars || window.appVars || {};
      return {
        url: location.href,
        title: document.title || '',
        host: location.hostname.toLowerCase(),
        text: (document.body?.innerText || '').slice(0, 1400),
        controls,
        tokenLength: cf && cf.value ? cf.value.length : 0,
        formId: form ? (form.id || '') : '',
        hasAdFormData: !!document.querySelector('input[name="ad_form_data"]'),
        counter: Number(av.counter_value || av.counterValue || 0),
        captchaType: String(av.captcha_type || ''),
        captchaEnabled: String(av.enable_captcha || '')
      };
    }""")


def continuation_signature(state: dict) -> tuple:
    """Stable signature of visible continuation controls, excluding unrelated UI."""
    rows = []
    pattern = re.compile(
        r"click\s*to\s*verify|continue|verify|next|proceed|get\s*link|generate\s*link|unlock",
        re.I,
    )
    for item in state.get("controls", []) or []:
        label = str(item.get("text", "") or "").strip()
        if pattern.search(label):
            rows.append((
                str(item.get("tag", "")),
                str(item.get("id", "")),
                label,
                bool(item.get("disabled", False)),
            ))
    return tuple(rows)


def countdown(emit, stage: int, label: str, seconds: int, total_seconds: int = 40,
              stage_base: int = 0):
    seconds = max(0, int(seconds))
    emit_status(emit, "RUNNING", label, stage)
    emit_detail(emit, f"Timer dimulai: {label}, durasi {seconds} detik.", "info", label)
    for remaining in range(seconds, 0, -1):
        elapsed_here = seconds - remaining
        pct = min(99, int(((stage_base + elapsed_here) / max(1, total_seconds)) * 100))
        emit({"type": "progress", "stage": stage, "label": label,
              "remaining": remaining, "total": seconds, "percent": pct})
        if remaining in {10, 5, 3, 2, 1} or remaining == seconds:
            emit_detail(emit, f"{label}: {remaining} detik tersisa.", "info", label)
        time.sleep(1)
    emit({"type": "progress", "stage": stage, "label": label,
          "remaining": 0, "total": seconds,
          "percent": min(99, int(((stage_base + seconds) / max(1, total_seconds)) * 100))})
    emit_detail(emit, f"Timer selesai: {label}.", "success", label)


def click_normal_continue(page, initial=False) -> dict:
    js = r"""() => {
      const initial = __INITIAL__;
      const visible = (el) => {
        if (!el) return false;
        const s = getComputedStyle(el), r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' &&
               r.width > 0 && r.height > 0;
      };
      const controls = Array.from(document.querySelectorAll(
        'button, input[type="submit"], input[type="button"], a.btn, a.button, [role="button"]'
      )).filter(visible).map(el => ({
        tag: el.tagName.toLowerCase(), id: el.id || '',
        text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0,100),
        disabled: !!el.disabled
      }));
      let el = null;
      if (initial) el = document.querySelector('#invisibleCaptchaShortlink');
      if (!visible(el) || el.disabled) el = null;
      if (!el) {
        const isNext = (x) => /click\s*to\s*verify|continue|verify|next|proceed|get\s*link|generate\s*link|unlock/i
          .test((x.innerText || x.value || x.getAttribute('aria-label') || '').trim());
        const candidates = controls.length ? Array.from(document.querySelectorAll(
          'button, input[type="submit"], input[type="button"], a.btn, a.button, [role="button"]'
        )).filter(x => visible(x) && !x.disabled && isNext(x)) : [];
        el = candidates.find(x => x.id !== 'smg-arm') || candidates[0] || null;
      }
      if (!el) return {clicked:false, reason:'Tidak menemukan tombol lanjut yang terlihat dan aktif', controls};
      const details = {
        tag: el.tagName.toLowerCase(), id: el.id || '',
        label: (el.innerText || el.value || el.getAttribute('aria-label') || el.id || '').trim().slice(0,100),
        disabled: !!el.disabled, type: el.getAttribute('type') || ''
      };
      try { el.click(); }
      catch (e) { return {clicked:false, reason:'DOM click melempar: ' + String(e), details, controls}; }
      return {clicked:true, reason:'click() dipanggil pada kontrol terlihat', details, controls};
    }""".replace('__INITIAL__', 'true' if initial else 'false')
    try:
        result = page.evaluate(js)
    except Exception as exc:
        return {"clicked": False, "uncertain": True,
                "reason": f"page.evaluate melempar {type(exc).__name__}: {exc}"}
    if isinstance(result, dict):
        return result
    return {"clicked": False, "reason": f"Hasil evaluate tidak berbentuk dict: {type(result).__name__} {result!r}"}


def live_page_url(page):
    try:
        value = page.evaluate("location.href")
        if isinstance(value, str) and value:
            return value
    except Exception:
        pass
    try:
        value = getattr(page, "url", "")
        return value if isinstance(value, str) else str(value or "")
    except Exception:
        return ""


def wait_for_page_change(page, before_url, before_text, seconds=5):
    for elapsed in range(1, seconds + 1):
        time.sleep(1)
        try:
            now_url = live_page_url(page)
            if now_url != before_url:
                return True, f"URL berubah setelah klik: {before_url} -> {now_url}"
            state = inspect_page(page)
            if state.get("text", "") != before_text:
                return True, f"Teks DOM berubah setelah klik ({elapsed}s)"
            controls_now = state.get("controls", [])
            if controls_now:
                return False, f"DOM diperiksa {elapsed}s; URL masih sama dan kontrol tetap tersedia"
        except Exception as exc:
            if elapsed in {1, 3, seconds}:
                last_reason = f"Pemeriksaan transisi {elapsed}s: {type(exc).__name__}: {exc}"
            else:
                last_reason = f"Pemeriksaan transisi: {type(exc).__name__}: {exc}"
    return False, locals().get("last_reason", f"Tidak ada perubahan URL/teks DOM setelah {seconds}s")


def run_browser_flow(target: str, emit) -> dict:
    emit_status(emit, "STARTING", "Memvalidasi tautan", 1)
    emit_detail(emit, "Memvalidasi format URL dan domain target.", "info", "VALIDATE")
    target = valid_target(target)
    parsed_target = urlparse(target)
    emit_log(emit, f"Validasi URL berhasil: host={parsed_target.hostname}, path={parsed_target.path}.", "success", "VALIDATE")
    emit_status(emit, "STARTING", "Menyiapkan Chromium", 1)
    emit_log(emit, f"Memulai Chromium headless untuk {target}", "info", "BROWSER")
    final_capture = {"url": "", "intermediate": ""}

    emit_detail(emit, "Menginisialisasi sesi Chromium...", "info", "BROWSER")
    try:
        browser_context = Chromium(headless=True)
    except Exception as exc:
        emit_log(emit, f"Gagal membuat Chromium: {type(exc).__name__}: {exc}", "error", "BROWSER_INIT")
        raise RuntimeError(f"Chromium gagal dibuat ({type(exc).__name__}): {exc}") from exc

    try:
        emit_detail(emit, "Memanggil Chromium.launch() agar koneksi CDP siap.", "info", "BROWSER")
        browser = browser_context.launch()
        if browser is None:
            browser = browser_context
        emit_detail(emit, "Chromium.launch() selesai; koneksi CDP disiapkan.", "success", "BROWSER")
        emit_detail(emit, "Membuka tab baru.", "info", "BROWSER")
        try:
            page = browser.new_page()
        except Exception as exc:
            emit_log(emit, f"Gagal membuat tab Chromium: {type(exc).__name__}: {exc}", "error", "NEW_PAGE")
            raise RuntimeError(f"Gagal membuat tab Chromium ({type(exc).__name__}): {exc}") from exc
        try:
            emit_detail(emit, f"Tab siap; URL awal={getattr(page, 'url', '(URL belum tersedia)')}.", "success", "NEW_PAGE")
        except Exception:
            emit_detail(emit, "Tab baru dibuat; properti URL belum bisa dibaca.", "warn", "NEW_PAGE")

        cdp_responses = []
        cdp_finished = []
        cdp_lock = threading.Lock()
        cdp_diag_seen = {}

        def _cdp_loading_finished(params):
            request_id = params.get("requestId")
            if request_id:
                with cdp_lock:
                    cdp_finished.append(request_id)

        page.session.on("Network.loadingFinished", _cdp_loading_finished)

        def _cdp_response_listener(response):
            try:
                from urllib.parse import urlparse
                parsed = urlparse(response.url or "")
                host = (parsed.hostname or "").lower()
                path = parsed.path.rstrip("/")
                if (
                    (host == "shrinkme.click" and path == "/links/go")
                    or (host == "themezon.net" and path == "/go")
                ):
                    with cdp_lock:
                        cdp_responses.append({
                            "request_id": response.params.get("requestId"),
                            "url": response.url,
                            "status": response.status,
                        })
                    emit_detail(
                        emit,
                        f"CDP respons {host}{parsed.path} terdeteksi, HTTP={response.status}.",
                        "success",
                        "NETWORK",
                    )
                else:
                    # Keep diagnostics focused on the resolver's own hosts.
                    # Ad networks and tracking endpoints otherwise flood the UI log.
                    if host not in {
                        "shrinkme.click", "www.shrinkme.click",
                        "shrinkme.io", "www.shrinkme.io", "themezon.net",
                    }:
                        return
                    if path == "/cdn-cgi/rum":
                        return
                    leaf = parsed.path.rsplit("/", 1)[-1].lower()
                    if leaf.endswith((
                        ".js", ".css", ".png", ".jpg", ".jpeg", ".gif",
                        ".webp", ".svg", ".ico", ".woff", ".woff2",
                        ".ttf", ".map",
                    )):
                        return
                    diag_key = (response.status, host, parsed.path)
                    with cdp_lock:
                        is_new = diag_key not in cdp_diag_seen
                        if is_new:
                            cdp_diag_seen[diag_key] = 1
                    if is_new:
                        emit_detail(
                            emit,
                            "CDP endpoint internal: "
                            f"HTTP={response.status} host={host} path={(parsed.path or '/')[:80]}",
                            "info",
                            "NETWORK",
                        )
            except Exception as exc:
                emit_detail(
                    emit,
                    f"CDP listener: {type(exc).__name__}: {exc}",
                    "warn",
                    "NETWORK",
                )

        try:
            page.network.on_response(_cdp_response_listener)
            emit_detail(emit, "CDP_DIRECT_CAPTURE_V1 aktif sebelum navigasi.", "success", "NETWORK")
        except Exception as exc:
            emit_log(
                emit,
                f"CDP listener gagal dipasang: {type(exc).__name__}: {exc}",
                "error",
                "NETWORK",
            )

        emit_log(emit, "API page.on tidak tersedia di playwright_termux ini; memakai URL/DOM dan instrumentasi halaman yang kompatibel.", "warn", "NETWORK")

        emit_status(emit, "RUNNING", "Membuka halaman ShrinkMe", 1)
        emit_log(emit, f"Memuat halaman target (timeout 30 detik): {target}", "info", "NAVIGATION")
        try:
            nav_response = page.goto(target, timeout=30)
            emit_detail(emit, f"Navigasi awal selesai; response={type(nav_response).__name__ if nav_response is not None else 'tidak tersedia'}; URL aktif={getattr(page, 'url', '(kosong)')}.", "success", "NAVIGATION")
        except Exception as exc:
            emit_log(emit, f"Navigasi awal melempar {type(exc).__name__}: {exc}; akan memeriksa URL/DOM yang tersisa.", "warn", "NAVIGATION")
            try:
                emit_detail(emit, f"URL setelah exception navigasi: {live_page_url(page)}", "info", "NAVIGATION")
            except Exception:
                emit_log(emit, "URL halaman tidak bisa dibaca setelah exception navigasi.", "error", "NAVIGATION")

        try:
            observer_script = r"""() => {
              if (window.__shrmeNetObserverInstalled) return true;
              window.__shrmeNetObserverInstalled = true;
              window.__shrmeNetEvents = [];
              const keep = (url, status, body) => {
                try {
                  const u = new URL(url, location.href);
                  if ((u.hostname === 'shrinkme.click' && u.pathname.replace(/\/$/, '') === '/links/go') ||
                      (u.hostname === 'themezon.net' && u.pathname.replace(/\/$/, '') === '/go')) {
                    window.__shrmeNetEvents.push({url:u.href,status,body:String(body || '').slice(0,3000),at:Date.now()});
                    window.__shrmeNetEvents = window.__shrmeNetEvents.slice(-20);
                  }
                } catch(e) {}
              };
              const oldFetch = window.fetch;
              window.fetch = function(...args) {
                return oldFetch.apply(this,args).then(async r => {
                  try { const clone = r.clone(); keep(r.url,r.status,await clone.text()); } catch(e) {}
                  return r;
                });
              };
              const oldOpen = XMLHttpRequest.prototype.open;
              const oldSend = XMLHttpRequest.prototype.send;
              XMLHttpRequest.prototype.open = function(method,url,...rest) {
                this.__shrmeUrl = url;
                return oldOpen.call(this,method,url,...rest);
              };
              XMLHttpRequest.prototype.send = function(...args) {
                this.addEventListener('load', function() {
                  try {
                    let body = '';
                    try {
                      body = this.responseType === 'json'
                        ? JSON.stringify(this.response ?? {})
                        : this.responseText;
                    } catch(e) {
                      try { body = JSON.stringify(this.response ?? {}); }
                      catch(_) { body = ''; }
                    }
                    keep(
                      this.responseURL || this.__shrmeUrl,
                      this.status,
                      body || ''
                    );
                  } catch(e) {}
                });
                return oldSend.apply(this,args);
              };
              return true;
            }"""
            page.evaluate(observer_script)
            emit_detail(emit, "Observer fetch/XHR kompatibel terpasang untuk endpoint Themezon /go/ dan ShrinkMe /links/go.", "success", "NETWORK")
        except Exception as exc:
            emit_log(emit, f"Observer fetch/XHR tidak dapat dipasang: {type(exc).__name__}: {exc}; lanjut dengan URL/DOM saja.", "warn", "NETWORK")

        start = time.monotonic()
        turnstile_seen = False
        initial_clicked = False
        themezon_steps = 0
        last_url = ""
        last_host = ""
        inspect_errors = 0
        main_timer_done = False
        final_submit_clicked = False

        def _consume_cdp_responses():
            with cdp_lock:
                ready = []
                expired = []
                for item in cdp_responses:
                    if item.get("_body_done"):
                        continue
                    if item.get("status") != 200:
                        continue
                    item["_body_attempts"] = int(item.get("_body_attempts", 0)) + 1
                    if item["_body_attempts"] <= 20:
                        ready.append(item)
                    else:
                        expired.append(item)
                if expired:
                    expired_ids = {id(item) for item in expired}
                    cdp_responses[:] = [
                        item for item in cdp_responses
                        if id(item) not in expired_ids
                    ]

            for item in ready:
                request_id = item.get("request_id")
                if not request_id:
                    continue
                try:
                    result = page.session.send(
                        "Network.getResponseBody",
                        {"requestId": request_id},
                    )
                except Exception as exc:
                    attempt = item.get("_body_attempts", 0)
                    if attempt in (1, 4, 8, 15):
                        emit_detail(
                            emit,
                            f"Body respons belum tersedia (percobaan {attempt}): {type(exc).__name__}: {exc}",
                            "info",
                            "CAPTURE",
                        )
                    continue

                with cdp_lock:
                    item["_body_done"] = True
                    cdp_responses[:] = [
                        entry for entry in cdp_responses
                        if entry is not item
                    ]

                try:
                    body = result.get("body", "")
                    if result.get("base64Encoded"):
                        import base64
                        body = base64.b64decode(body).decode("utf-8", "replace")

                    data = json.loads(body or "{}")
                    candidate = data.get("url", "") if isinstance(data, dict) else ""

                    accepted = accept_captured_url(candidate) if candidate else ""
                    if accepted:
                        final_capture["url"] = candidate
                        final_capture["intermediate"] = accepted
                        emit_log(
                            emit,
                            "URL tujuan berhasil diambil dari JSON respons dan lolos validasi.",
                            "success",
                            "CAPTURE",
                        )
                        return accepted

                    if candidate:
                        emit_detail(
                            emit,
                            "JSON berisi nilai url yang bukan URL tujuan yang valid.",
                            "warn",
                            "CAPTURE",
                        )
                    else:
                        shape = (
                            f"JSON keys={list(data.keys())}; "
                            if isinstance(data, dict)
                            else f"JSON type={type(data).__name__}; "
                        )
                        emit_detail(
                            emit,
                            f"Diagnostik body HTTP 200: {shape}body awal={body[:700]!r}",
                            "info",
                            "CAPTURE",
                        )
                except Exception as exc:
                    emit_detail(
                        emit,
                        f"Body respons tidak dapat diproses sebagai JSON: {type(exc).__name__}: {exc}",
                        "warn",
                        "CAPTURE",
                    )
            return ""

        while time.monotonic() - start < 210:
            with cdp_lock:
                finished_ids = set(cdp_finished)
                cdp_finished.clear()
                ready = [
                    item for item in cdp_responses
                    if item.get("request_id") in finished_ids
                ]
                cdp_responses[:] = [
                    item for item in cdp_responses
                    if item.get("request_id") not in finished_ids
                ]

            for item in ready:
                request_id = item.get("request_id")
                if not request_id or item.get("status") != 200:
                    continue
                try:
                    result = page.session.send(
                        "Network.getResponseBody",
                        {"requestId": request_id},
                    )
                    body = result.get("body", "")
                    if result.get("base64Encoded"):
                        import base64
                        body = base64.b64decode(body).decode("utf-8", "replace")
                    data = json.loads(body or "{}")
                    candidate = data.get("url", "") if isinstance(data, dict) else ""
                    if candidate:
                        final_capture["intermediate"] = candidate
                        emit_detail(
                            emit,
                            "Field url diterima dari respons JSON /links/go.",
                            "success",
                            "CAPTURE",
                        )
                except Exception as exc:
                    emit_detail(
                        emit,
                        f"Body /links/go belum dapat dibaca: {type(exc).__name__}: {exc}",
                        "warn",
                        "CAPTURE",
                    )
            try:
                current_url = live_page_url(page)
            except Exception:
                current_url = ""

            if is_final_note_url(current_url):
                emit_log(emit, "URL tujuan note terdeteksi. Tidak membaca isi note.", "success")
                return {"status": "success", "url": current_url}
            if final_capture.get("url") and is_final_note_url(final_capture["url"]):
                emit_log(emit, "URL tujuan note tertangkap dari navigasi. Tidak membaca isi note.", "success")
                return {"status": "success", "url": final_capture["url"]}
            candidate = final_capture.get("intermediate", "")
            if candidate:
                if is_final_note_url(candidate):
                    parsed_candidate = urlparse(candidate)
                    note_match = FINAL_PATH_RE.fullmatch(parsed_candidate.path or "")
                    slug = note_match.group(1)
                    normalized = f"https://{FINAL_HOST}/notes/{slug}"
                    emit_log(emit, "Respons akhir berisi slug note; menampilkan URL tujuan note tanpa membaca isinya.", "success")
                    return {"status": "success", "url": normalized}
                accepted = accept_captured_url(candidate)
                if accepted:
                    # Field url dari JSON /links/go sudah merupakan tautan
                    # tujuan akhir (host apa pun) — langsung sukses,
                    # jangan menunggu URL note lagi.
                    emit_log(emit, "URL tujuan diterima; menampilkan hasil akhir.", "success")
                    return {"status": "success", "url": accepted}

            try:
                net_events = page.evaluate("() => { const e = window.__shrmeNetEvents || []; const n = window.__shrmeNetLast || 0; window.__shrmeNetLast = e.length; return e.slice(n); }")
                for event in (net_events or []):
                    try:
                        u = urlparse(event.get("url", ""))
                        h = (u.hostname or "").lower()
                        path = u.path.rstrip("/")
                        emit_detail(emit, f"Respons halaman terpantau: {h}{u.path}; HTTP={event.get('status')}", "success" if int(event.get("status") or 0) < 400 else "warn", "NETWORK")
                        if h == "themezon.net" and path == "/go":
                            try:
                                data = json.loads(event.get("body") or "{}")
                                remaining = data.get("data", {}).get("remaining") if isinstance(data, dict) else None
                                emit_detail(emit, f"Themezon /go/ JSON: remaining={remaining if remaining is not None else 'tidak ada'}.", "info", "THEMEZON_NETWORK")
                            except Exception:
                                pass
                        if h == "shrinkme.click" and path == "/links/go":
                            try:
                                data = json.loads(event.get("body") or "{}")
                                iter_candidate = data.get("url", "") if isinstance(data, dict) else ""
                                if iter_candidate:
                                    final_capture["intermediate"] = iter_candidate
                                    emit_log(emit, f"URL tujuan diterima: {iter_candidate}", "success", "CAPTURE")
                            except Exception as exc:
                                emit_detail(emit, f"JSON /links/go gagal dibaca: {type(exc).__name__}: {exc}", "warn", "CAPTURE")
                    except Exception:
                        pass
            except Exception as exc:
                if not hasattr(run_browser_flow, "_net_warned"):
                    emit_detail(emit, f"Pembacaan observer jaringan gagal: {type(exc).__name__}: {exc}", "warn", "NETWORK")
                    run_browser_flow._net_warned = True
            try:
                state = inspect_page(page)
                inspect_errors = 0
            except Exception as exc:
                inspect_errors += 1
                if inspect_errors in {1, 3, 5}:
                    emit_detail(emit, f"DOM inspection gagal ({inspect_errors}x): {type(exc).__name__}: {exc}", "warn", "DOM_INSPECT")
                time.sleep(1)
                continue

            host = state.get("host", "")
            text = state.get("text", "")
            if host != last_host or current_url != last_url:
                if host in {"themezon.net", "shrinkme.click", "www.shrinkme.click"}:
                    try:
                        observer_ready = page.evaluate(observer_script)
                        if host == "themezon.net":
                            emit_detail(
                                emit,
                                f"Observer ThemeZon dipasang ulang; aktif={bool(observer_ready)}.",
                                "success" if observer_ready else "warn",
                                "NETWORK",
                            )
                    except Exception as exc:
                        emit_detail(
                            emit,
                            f"Observer gagal dipasang ulang: {type(exc).__name__}: {exc}",
                            "warn",
                            "NETWORK",
                        )
                emit_status(emit, "RUNNING", f"Halaman aktif: {host or current_url}", 1)
                emit_detail(emit, f"Perpindahan/halaman aktif terdeteksi: host={host or '(kosong)'}; URL={current_url or '(kosong)'}.", "info", "NAVIGATION")
                last_host, last_url = host, current_url
                controls = state.get("controls", [])[:8]
                control_summary = ", ".join(
                    (f"{item.get('tag')}#{item.get('id') or '-'}:{item.get('text') or '(tanpa label)'}" + (" [disabled]" if item.get("disabled") else ""))
                    for item in controls
                ) or "tidak ada kontrol terlihat"
                emit_detail(emit, f"Snapshot DOM: title={state.get('title') or '(kosong)'}; form={state.get('formId') or '(tidak ada)'}; kontrol={control_summary}.", "info", "DOM_SNAPSHOT")
                if host in {"shrinkme.click", "www.shrinkme.click"}:
                    emit_detail(emit, f"Konfigurasi halaman: captcha={state.get('captchaType') or '(tidak terdeteksi)'}; enabled={state.get('captchaEnabled') or '(tidak terdeteksi)'}; counter={state.get('counter')}; token_chars={state.get('tokenLength', 0)}; ad_form_data={state.get('hasAdFormData')}.", "info", "DOM_SNAPSHOT")

            if host in {"shrinkme.click", "www.shrinkme.click"} and state.get("formId") == "link-view" and not initial_clicked:
                emit_status(emit, "WAITING CAPTCHA" if not turnstile_seen else "RUNNING", "Gerbang awal ShrinkMe", 1)
                if not turnstile_seen:
                    emit({"type": "progress", "stage": 1, "label": "Menunggu verifikasi Turnstile normal", "remaining": -1, "total": 0, "percent": 2})
                    emit_log(emit, "Form #link-view terdeteksi. Menunggu token Turnstile asli dari halaman (batas 35 detik); token tidak akan dipalsukan.", "warn", "TURNSTILE")
                    token_deadline = time.monotonic() + 35
                    last_log_second = -5
                    while time.monotonic() < token_deadline:
                        try:
                            st = inspect_page(page)
                        except Exception:
                            st = {}
                        if is_final_note_url(live_page_url(page)):
                            return {"status": "success", "url": live_page_url(page)}
                        token_len = int(st.get("tokenLength", 0) or 0)
                        if token_len > 0:
                            turnstile_seen = True
                            emit_log(emit, f"Token Turnstile terdeteksi dari halaman ({token_len} karakter).", "success")
                            break
                        remain = max(0, int(token_deadline - time.monotonic()))
                        if remain // 5 != last_log_second // 5:
                            emit_log(emit, f"Menunggu verifikasi: {remain} detik tersisa.", "warn")
                            last_log_second = remain
                        time.sleep(1)
                    if not turnstile_seen:
                        emit_log(emit, "Timeout Turnstile: token tidak muncul dalam 35 detik. Tidak ada tombol/form yang dikirim.", "error", "TURNSTILE")
                        return {"status": "error", "message": "Turnstile belum menghasilkan token dalam 35 detik. Engine berhenti sebelum mengirim form; cek dukungan CAPTCHA pada sesi Chromium."}

                emit_status(emit, "RUNNING", "Menunggu timer gerbang awal", 1)
                wait_sec = int(state.get("counter", 10) or 10)
                wait_sec = min(30, max(0, wait_sec))
                emit_log(emit, f"Timer awal ShrinkMe: {wait_sec} detik.")
                countdown(emit, 1, "Gerbang awal ShrinkMe", wait_sec, 40, 0)
                emit_detail(emit, "Mencari tombol #invisibleCaptchaShortlink yang terlihat dan aktif.", "info", "INITIAL_CONTINUE")
                click_result = click_normal_continue(page, initial=True)
                if not click_result.get("clicked"):
                    emit_log(emit, f"Evaluasi klik awal tidak terkonfirmasi: {click_result.get('reason', 'alasan tidak tersedia')}", "warn", "INITIAL_CONTINUE")
                    emit_detail(emit, f"Detail klik awal: {json.dumps(click_result, ensure_ascii=False)[:900]}", "info", "INITIAL_CONTINUE")
                    changed, change_reason = wait_for_page_change(page, current_url, state.get("text", ""), seconds=5)
                    if not changed:
                        emit_log(emit, f"Tombol awal tidak terkonfirmasi dan tidak ada transisi: {change_reason}", "error", "INITIAL_CONTINUE")
                        return {"status": "error", "message": f"Klik tombol awal tidak terkonfirmasi. Detail: {click_result.get('reason', 'tidak diketahui')}. Observasi: {change_reason}. Periksa kontrol dan error evaluate pada log."}
                    emit_log(emit, f"Evaluate tidak mengembalikan konfirmasi klik, tetapi transisi teramati: {change_reason}.", "success", "INITIAL_CONTINUE")
                else:
                    _label = (click_result.get("details", {}) or {}).get("label") or "tombol lanjut"
                    emit_log(emit, f"Klik terkirim: {_label}", "success", "INITIAL_CONTINUE")
                    emit_detail(emit, f"Detail klik awal: {json.dumps(click_result.get('details', {}), ensure_ascii=False)}", "info", "INITIAL_CONTINUE")
                initial_clicked = True
                emit_detail(emit, "Menunggu navigasi atau perubahan DOM setelah Continue awal.", "info", "INITIAL_CONTINUE")
                time.sleep(2)
                continue

            # Perubahan Utama: ThemeZon bisa butuh lebih dari 3 klik (misal tombol "GET LINK" muncul belakangan)
            if host == "themezon.net" and themezon_steps < 5:
                step_no = themezon_steps + 1
                stage_idx = min(step_no + 1, 5)
                emit_status(emit, f"STEP {step_no}", f"Themezon Step {step_no}", stage_idx)
                emit_log(emit, f"Halaman Themezon terdeteksi sebagai step {step_no}; form dan kontrol dipantau.", "success", f"THEMEZON_STEP_{step_no}")
                
                # Timer utama dipertahankan untuk langkah 1-3; langkah akhir memakai
                # polling kontrol agar tombol disabled tidak memicu tunggu ganda.
                wait_sec = 10 if step_no <= 3 else 3
                countdown(emit, stage_idx, f"Themezon Step {step_no}", wait_sec, 50, 10 + themezon_steps * 10)

                click_before_url = live_page_url(page)
                try:
                    click_before_state = inspect_page(page)
                except Exception:
                    click_before_state = state
                before_cta = continuation_signature(click_before_state)

                click_result = click_normal_continue(page, initial=False)
                if not click_result.get("clicked"):
                    emit_log(emit, f"Klik Continue belum terkonfirmasi: {click_result.get('reason', 'alasan tidak tersedia')}", "warn", f"THEMEZON_STEP_{step_no}")
                    emit_detail(emit, f"Detail klik ThemeZon: {json.dumps(click_result, ensure_ascii=False)[:900]}", "info", f"THEMEZON_STEP_{step_no}")
                else:
                    _label = (click_result.get("details", {}) or {}).get("label") or "tombol lanjut"
                    emit_log(emit, f"Klik terkirim: {_label}", "success", f"THEMEZON_STEP_{step_no}")
                    emit_detail(emit, f"Detail klik ThemeZon: {json.dumps(click_result.get('details', {}), ensure_ascii=False)}", "info", f"THEMEZON_STEP_{step_no}")

                themezon_steps += 1
                emit_detail(emit, f"Memeriksa navigasi atau tombol lanjut yang baru aktif (batas 12 detik).", "info", f"THEMEZON_STEP_{step_no}")
                transition_seen = False
                before_cta_set = set(before_cta)
                for wait_sec_loop in range(1, 13):
                    time.sleep(1)
                    cdp_final = _consume_cdp_responses()
                    if cdp_final:
                        return {"status": "success", "url": cdp_final}
                    now_url = live_page_url(page)
                    if is_final_note_url(now_url):
                        emit_log(emit, "URL note muncul saat menunggu transisi ThemeZon.", "success", "CAPTURE")
                        return {"status": "success", "url": now_url}
                    try:
                        now_state = inspect_page(page)
                        net_events_inner = page.evaluate("() => { const e = window.__shrmeNetEvents || []; const n = window.__shrmeNetLast || 0; window.__shrmeNetLast = e.length; return e.slice(n); }")
                        for event in (net_events_inner or []):
                            try:
                                u = urlparse(event.get("url", ""))
                                h = (u.hostname or "").lower()
                                path = u.path.rstrip("/")
                                if h == "themezon.net" and path == "/go":
                                    try:
                                        payload = json.loads(event.get("body") or "{}")
                                        remaining = payload.get("data", {}).get("remaining")
                                        if remaining is not None:
                                            emit_detail(emit, f"ThemeZon timer terdeteksi: {remaining} detik tersisa.", "info", "THEMEZON_NETWORK")
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    except Exception as exc:
                        if wait_sec_loop in {1, 6, 12}:
                            emit_detail(emit, f"Pemeriksaan transisi ke-{wait_sec_loop}s gagal: {type(exc).__name__}: {exc}", "warn", "TRANSITION")
                        continue

                    if now_url != click_before_url:
                        emit_log(emit, f"Transisi URL terdeteksi setelah Continue: {click_before_url} -> {now_url}", "success", "TRANSITION")
                        transition_seen = True
                        break

                    current_cta = continuation_signature(now_state)
                    newly_enabled = [item for item in current_cta if not item[3] and item not in before_cta_set]
                    if newly_enabled:
                        emit_log(emit, f"Tombol lanjut baru siap: {newly_enabled[0][2]}.", "success", "TRANSITION")
                        transition_seen = True
                        break

                    if wait_sec_loop in {3, 6, 9, 12}:
                        emit_detail(emit, f"Menunggu navigasi/tombol aktif: {wait_sec_loop}/12 detik.", "warn" if wait_sec_loop == 12 else "info", "TRANSITION")

                if not transition_seen:
                    click_reason = click_result.get("reason", "klik normal terkonfirmasi")
                    emit_log(emit, f"Belum ada URL baru atau tombol lanjut baru yang aktif setelah ThemeZon Step {step_no}. Hasil klik={click_reason}.", "warn", "TRANSITION")
                    # Ulangi inspeksi halaman; jangan menganggap respons timer /go/ sebagai langkah selesai.
                    continue
                continue

            if host in {"shrinkme.click", "www.shrinkme.click"} and state.get("hasAdFormData") and not final_submit_clicked:
                emit_status(emit, "EXTRACTING URL", "Form final ShrinkMe terdeteksi", 5)
                wait_sec = int(state.get("counter", 10) or 10)
                wait_sec = min(30, max(0, wait_sec))
                emit_log(emit, f"Form final terdeteksi; menunggu {wait_sec} detik.", "success", "FINAL_FORM")
                countdown(emit, 5, "Mengambil URL tujuan", wait_sec, 40, 30)
                click_result = click_normal_continue(page, initial=False)
                if not click_result.get("clicked"):
                    emit_log(emit, f"Klik tombol final belum terkonfirmasi: {click_result.get('reason', 'alasan tidak tersedia')}", "warn", "FINAL_FORM")
                    emit_detail(emit, f"Detail klik final: {json.dumps(click_result, ensure_ascii=False)[:900]}", "info", "FINAL_FORM")
                    changed, change_reason = wait_for_page_change(page, current_url, state.get("text", ""), seconds=5)
                    if not changed:
                        emit_log(emit, f"Tidak ada transisi setelah percobaan submit final: {change_reason}", "error", "FINAL_FORM")
                        return {"status": "error", "message": f"Tombol final tidak terkonfirmasi. {click_result.get('reason', '')} {change_reason}"}
                    emit_log(emit, f"Transisi teramati meskipun evaluasi klik tidak terkonfirmasi: {change_reason}", "success", "FINAL_FORM")
                else:
                    _label = (click_result.get("details", {}) or {}).get("label") or "tombol lanjut"
                    emit_log(emit, f"Tombol final diklik: {_label}", "success", "FINAL_FORM")
                    emit_detail(emit, f"Detail klik final: {json.dumps(click_result.get('details', {}), ensure_ascii=False)}", "info", "FINAL_FORM")
                final_submit_clicked = True
                emit_log(emit, "Menunggu URL tujuan dari halaman final.", "info", "FINAL_FORM")
                continue

            candidate = final_capture.get("intermediate", "")
            if candidate:
                if is_final_note_url(candidate):
                    parsed_candidate = urlparse(candidate)
                    note_match = FINAL_PATH_RE.fullmatch(parsed_candidate.path or "")
                    slug = note_match.group(1)
                    normalized = f"https://{FINAL_HOST}/notes/{slug}"
                    emit_log(emit, "Respons akhir berisi slug note; menampilkan URL tujuan note tanpa membaca isinya.", "success")
                    return {"status": "success", "url": normalized}
                accepted = accept_captured_url(candidate)
                if accepted:
                    # Field url dari JSON /links/go sudah merupakan tautan
                    # tujuan akhir (host apa pun) — langsung sukses,
                    # jangan menunggu URL note lagi.
                    emit_log(emit, "URL tujuan diterima; menampilkan hasil akhir.", "success")
                    return {"status": "success", "url": accepted}

            if host in {"", "about:blank"} or current_url in {"", "about:blank"}:
                time.sleep(1)
                continue
            if host and host not in {"shrinkme.click", "www.shrinkme.click", "shrinkme.io", "www.shrinkme.io", "themezon.net", "en.mrproblogger.com"}:
                emit_status(emit, "ERROR", f"Berhenti di host {host}")
                emit_log(emit, f"Host yang tidak dikenal terdeteksi: {host}; URL={current_url}. Engine berhenti agar tidak mengambil isi/link dari halaman luar.", "error", "HOST_CHECK")
                return {"status": "error", "message": f"Alur berpindah ke host {host} sebelum URL tujuan terkonfirmasi. Periksa URL aktif di log; halaman luar tidak dipanen."}

            time.sleep(1)

        captured = final_capture.get("intermediate") or final_capture.get("url") or ""
        emit_log(emit, "Batas waktu total 210 detik tercapai tanpa URL tujuan yang terkonfirmasi.", "error", "TIMEOUT")
        error_result = {"status": "error", "message": "Timeout 210 detik: URL tujuan belum terkonfirmasi. Lihat log terakhir untuk mengetahui tahap macet."}
        if captured:
            # URL sempat tertangkap tapi alur kemudian gagal: sertakan agar
            # kartu hasil tetap menampilkannya.
            error_result["url"] = captured
        return error_result
    finally:
        try:
            browser_context.close()
        except Exception as exc:
            emit_log(emit, f"Penutupan Chromium: {type(exc).__name__}: {exc}", "warn", "CLEANUP")


def start_resolution(target: str, emit) -> None:
    phase = "START"
    emit_status(emit, "STARTING", "Memulai resolver", 1)
    emit_detail(emit, "Permintaan resolve diterima oleh Flask.", "info", phase)
    try:
        phase = "VALIDATE"
        emit_detail(emit, "Memeriksa URL input sebelum membuka browser.", "info", phase)
        target = valid_target(target)
        emit_detail(emit, f"Input lolos validasi; target={target}", "success", phase)
        phase = "BROWSER_FLOW"
        result = run_browser_flow(target, emit)
        if result.get("status") == "success":
            emit_status(emit, "SUCCESS", "URL tujuan berhasil ditangkap", 5)
            emit_log(emit, f"Resolusi berhasil; URL hasil={result.get('url')}. Isi halaman note tidak dibaca.", "success", "DONE")
            emit({"type": "result", "url": result["url"]})
        else:
            message = result.get("message", "Resolusi gagal tanpa pesan spesifik.")
            emit_error(emit, message, "FLOW_ERROR", phase, url=result.get("url") or "")
    except ValueError as exc:
        emit_error(emit, str(exc), "INPUT_VALIDATION", phase)
    except Exception as exc:
        import traceback
        trace = traceback.format_exc()
        try:
            print(trace, flush=True)
        except Exception:
            pass
        tail = " | ".join(line.strip() for line in trace.strip().splitlines()[-4:])
        emit_error(emit, f"{type(exc).__name__}: {exc}. Traceback akhir: {tail}", "UNHANDLED_EXCEPTION", phase)

# --- bphub: jembatan emit shrme -> generator event seragam (pola stream asli) ---
def resolve(target_url):
    """Interface seragam bphub: generator event {type,msg,level,url}."""
    events: queue.Queue = queue.Queue()
    finished = object()

    def push(event):
        events.put(event)

    def worker():
        try:
            start_resolution(target_url, push)
        except Exception as e:
            push({"type": "error", "msg": f"Kendala eksekusi adapter: {type(e).__name__}: {e}"})
        finally:
            events.put(finished)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        try:
            event = events.get(timeout=20)
        except queue.Empty:
            continue
        if event is finished:
            break
        t = event.get("type")
        if t == "result":
            yield {"type": "result", "url": event.get("url", "")}
        elif t == "error":
            err = {"type": "error", "msg": event.get("msg", "Gagal tanpa pesan.")}
            if event.get("url"):
                err["url"] = event["url"]
            yield err
        elif t == "progress":
            # Teruskan apa adanya: UI mengabaikan progress. Jangan ubah
            # menjadi log kosong (dulu jatuh ke else dan membanjiri log
            # dengan satu baris kosong tiap detik).
            yield {"type": "progress", "stage": event.get("stage"),
                   "label": event.get("label", ""), "remaining": event.get("remaining"),
                   "total": event.get("total"), "percent": event.get("percent")}
        elif t == "status":
            yield {"type": "log", "msg": event.get("label", ""), "level": "info"}
        else:
            log_ev = {"type": "log", "msg": event.get("msg", ""),
                      "level": event.get("level", "info")}
            if event.get("detail"):
                # Teruskan penanda detail agar hub bisa menahannya di mode default.
                log_ev["detail"] = True
            yield log_ev
