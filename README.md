# BPHUB — Bypass Hub

**Satu pintu untuk enam layanan bypass shortlink.** BPHUB menggabungkan enam modul bypass yang tadinya berdiri sendiri-sendiri di Termux Command Center menjadi satu hub web lokal: tempel tautan, layanan terdeteksi otomatis dari domainnya, antrean campuran banyak tautan sekaligus, dan hasil bisa dioper ke modul downloader.

*One local web hub for six shortlink bypass services — paste links, the service is auto-detected from the domain, mixed batches run in one queue, and results can be chained to downloader modules.*

## Layanan / Services

| Kode | Layanan | Domain | Mesin |
|------|---------|--------|-------|
| cuty | Cuty.io | cuty.io / cutty.io | Browser (Chromium) |
| shrme | ShrinkMe | shrinkme.click / shrinkme.io | Browser (Chromium) |
| srnky | ShrinkEarn | shrinkearn.com | Browser (Chromium) |
| clk | clk.sh | clk.sh / clk.asia murni | Browser (Chromium) |
| ez4 | Ez4short | ez4short.com | HTTP murni |
| dplink | DropLink | droplink.co | HTTP murni |

## Fitur / Features

- Deteksi layanan otomatis dari domain + paksa layanan manual per kartu adapter / *auto-detect with manual override per adapter card*
- Antrean batch campuran (banyak tautan, beda layanan, satu kali jalan) / *mixed batch queue*
- Telemetri langsung per tautan (SSE): status, log, durasi, bilah kemajuan / *live per-link telemetry*
- Hasil per tautan: salin, buka, atau oper ke downloader (rantai TBDL/ICY di Termux) / *copy, open, or chain the result*
- Panel kesehatan per adapter — hub tetap hidup walau satu mesin belum siap / *per-adapter health panel*
- Tanpa akun, tanpa kunci API / *no accounts, no API keys*

## Instalasi Desktop (Windows / Linux / macOS)

Butuh Python 3.10+.

```bash
pip install -r requirements.txt
playwright install chromium
python desktop/run_desktop.py
```

Lalu buka `http://127.0.0.1:5049/` (peluncur mencoba membukanya otomatis).

Di desktop, empat adapter browser berjalan di atas **Playwright resmi** lewat berkas jembatan `desktop/playwright_termux.py` — adapter-adapter-nya sendiri tidak diubah sama sekali.

## Instalasi Termux (Android)

1. Ekstrak folder `bphub` ke folder projekmu (paket ini dirancang untuk tata letak `~/storage/shared/Termux/Projek/bphub`).
2. Pasang peluncurnya:

```bash
cp bphub/bin/bphub bphub/bin/bphubstop $PREFIX/bin/
chmod +x $PREFIX/bin/bphub $PREFIX/bin/bphubstop
```

3. Jalan & berhenti:

```bash
bphub       # server di http://127.0.0.1:5049
bphubstop
```

Di Termux, adapter browser memakai modul `playwright_termux` + Chromium Termux seperti biasa; folder `desktop/` tidak digunakan.

## Privasi / Privacy

- BPHUB **tidak menyimpan akun, kata sandi, atau kunci apa pun** — memang tidak ada.
- Token/cookie yang muncul selama proses adalah **token sesi milik situs target** (Turnstile/CSRF), dibuat baru setiap proses, hidup hanya di memori, dan tidak pernah ditulis ke berkas.
- Satu-satunya berkas yang ditulis adalah log server lokal (`logs/bphub_server.log`) di mesinmu sendiri. Folder `logs/` dan cache Python sudah dikecualikan lewat `.gitignore` — jangan unggah log pribadi ke repo publik.

## Catatan / Notes

- Alat ini dibuat untuk **pemakaian pribadi** pada tautan milik sendiri. Hormati syarat layanan situs tujuan.
- Hasil bypass bergantung pada situs tujuan; gerbang/iklan yang berubah bisa membuat satu layanan perlu penyesuaian.
- UI "Blueprint Control Deck"; mesin hub, adapter, dan perbaikan stabilitas (penutup generator bersih, percobaan ulang DropLink, penghenti server berbasis pindai proses) adalah bagian dari paket yang sama.

---

BPHUB — digabung, dirapikan, dan dirawat dari enam modul Termux Command Center milik **Agung Ariestya** ([setyas-cloud](https://github.com/setyas-cloud)).
