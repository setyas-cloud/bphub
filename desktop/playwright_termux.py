# playwright_termux.py — jembatan desktop untuk BPHUB.
#
# Di Termux, modul `playwright_termux` menyediakan kelas Chromium
# pembungkus Chromium lokal. Di desktop modul itu tidak ada, jadi berkas
# ini menyamar dengan nama & bentuk yang sama, tetapi isinya Playwright
# resmi (pip install playwright && playwright install chromium).
#
# Permukaan API yang ditiru persis seperti yang dipakai adapter BPHUB:
#   Chromium(headless=True)            -> objek mesin
#   .launch()                          -> browser (dipakai shrme)
#   with Chromium(...) as browser      -> browser (dipakai cuty/clk/srnky)
#   browser.new_page()                 -> page
#   page.goto / page.evaluate / page.url / ...  (terusan Playwright)
#   page.session.on(event, handler)    -> sesi CDP (event mentah)
#   page.session.send(method, params)  -> perintah CDP, mis.
#                                         "Network.getResponseBody"
#   page.network.on_response(handler)  -> page.on("response", handler)
#
# Peluncur desktop (desktop/run_desktop.py) menaruh folder ini paling
# depan di sys.path, jadi adapter mengimpor berkas ini. Di Termux
# folder ini tidak pernah masuk sys.path — modul aslinya yang dipakai.

import os
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def _proxy_from_env():
    # Hormati proxy standar dari lingkungan (HTTPS_PROXY dsb.) —
    # Playwright tidak membacanya sendiri. Di mesin pengguna biasa
    # variabel ini umumnya tidak ada, jadi tidak berpengaruh.
    raw = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
           or os.environ.get("ALL_PROXY") or os.environ.get("all_proxy"))
    if not raw:
        return None
    u = urlparse(raw)
    if not u.hostname:
        return None
    server = f"{u.scheme or 'http'}://{u.hostname}"
    if u.port:
        server += f":{u.port}"
    proxy = {"server": server}
    if u.username:
        proxy["username"] = u.username
    if u.password:
        proxy["password"] = u.password
    bypass = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    if bypass:
        proxy["bypass"] = bypass
    return proxy


class _SessionProxy:
    """Bungkus CDPSession Playwright menyerupai page.session bawaan
    playwright_termux: .on(event, handler) & .send(method, params)."""

    def __init__(self, page):
        self._raw_page = page
        self._cdp = None

    def _ensure(self):
        if self._cdp is None:
            self._cdp = self._raw_page.context.new_cdp_session(self._raw_page)
            try:
                # playwright_termux mengaktifkan domain Network secara
                # implisit; samakan perilakunya supaya event
                # Network.loadingFinished mengalir.
                self._cdp.send("Network.enable")
            except Exception:
                pass
        return self._cdp

    def on(self, event, handler):
        return self._ensure().on(event, handler)

    def send(self, method, params=None):
        if params is None:
            return self._ensure().send(method)
        return self._ensure().send(method, params)

    def __getattr__(self, name):
        return getattr(self._ensure(), name)


class _NetworkFacade:
    """page.network ala playwright_termux di atas page.on Playwright."""

    def __init__(self, page):
        self._page = page

    def on_response(self, handler):
        return self._page.on("response", handler)

    def on_request(self, handler):
        return self._page.on("request", handler)


class _PageProxy:
    def __init__(self, page):
        self._page = page
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = _SessionProxy(self._page)
        return self._session

    @property
    def network(self):
        return _NetworkFacade(self._page)

    def __getattr__(self, name):
        return getattr(self._page, name)


class _BrowserProxy:
    def __init__(self, browser):
        self._browser = browser

    def new_page(self, **kwargs):
        return _PageProxy(self._browser.new_page(**kwargs))

    def new_context(self, **kwargs):
        return self._browser.new_context(**kwargs)

    def close(self):
        return self._browser.close()

    def __getattr__(self, name):
        return getattr(self._browser, name)


class Chromium:
    """Setara kelas Chromium milik playwright_termux, di atas
    Playwright resmi. Mendukung pola pakai ganda:
      - konteks manajer:  with Chromium(headless=True) as browser:
      - manual (shrme):   ctx = Chromium(headless=True);
                          browser = ctx.launch(); ...; ctx.close()
    """

    def __init__(self, headless=True, **kwargs):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._proxy = None

    def launch(self):
        if self._proxy is None:
            self._pw = sync_playwright().start()
            launch_kwargs = {"headless": self.headless}
            proxy = _proxy_from_env()
            if proxy:
                launch_kwargs["proxy"] = proxy
            self._browser = self._pw.chromium.launch(**launch_kwargs)
            self._proxy = _BrowserProxy(self._browser)
        return self._proxy

    def new_page(self, **kwargs):
        return self.launch().new_page(**kwargs)

    def close(self):
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._pw = None
        self._proxy = None

    def __enter__(self):
        return self.launch()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
