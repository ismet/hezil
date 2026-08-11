# Deployment — Build, Run and Publish on a Public IP

This guide explains how to build, run, and publish the Hezil HES dashboard so that it is reachable
over a **public IP address**.

---

## Table of contents

- [The two halves of the app](#the-two-halves-of-the-app)
- [Path A — Static-only publish (no Python server)](#path-a--static-only-publish-no-python-server)
- [Path B — Full app on a public IP (needs the Python backend)](#path-b--full-app-on-a-public-ip-needs-the-python-backend)
  - [1. Build on the target machine](#1-build-on-the-target-machine)
  - [2. Make the server reachable — code change required](#2-make-the-server-reachable--code-change-required)
  - [3. Run persistently (systemd)](#3-run-persistently-systemd)
  - [4. Open the firewall](#4-open-the-firewall)
  - [5. Recommended: reverse proxy + HTTPS](#5-recommended-reverse-proxy--https)
- [Security notes](#security-notes)

---

## The two halves of the app

| Part | What it is | Hosting need |
|---|---|---|
| `hezil_dashboard.html` | Single self-contained static file (data embedded, pure SVG + JS) | Any static file server — **no Python** |
| `pano_sunucu.py` (port 8765) | Python backend: serves the dashboard at `/`, solves operation studies live (`/api/isletme`, `/api/imalatci`, `/api/enkesit`), caches to `hezil_onbellek/` | A machine that can run Python + numpy/pandas/matplotlib |

There are **two publishing paths** with very different effort:

- **Path A** — static-only: fastest, but the live "operation study" feature won't work.
- **Path B** — full app behind a public IP: needs the Python backend, a firewall rule, and one
  small code change (`pano_sunucu.py` currently binds to `127.0.0.1`).

---

## Path A — Static-only publish (no Python server)

If the live-solve feature isn't critical, the dashboard is just a file:

```bash
# any static host works — e.g. GitHub Pages, nginx, Netlify, S3
python -m http.server 8000 --directory .   # quick local test
```

**Downside:** the "İşletme çalışması" (operation study) section then only shows the pre-embedded
optima (`DETAY_GOMME = "az"` in `dashboard.py`); clicking any other point shows the
"start the server" notice.

---

## Path B — Full app on a public IP (needs the Python backend)

### 1. Build on the target machine

Linux VPS recommended. From a fresh checkout:

```bash
git clone https://github.com/ismet/hezil.git
cd hezil
pip install -r requirements.txt

# Scan results are already committed, so this is OPTIONAL on a fresh clone
python alternatifler.py     # ~3,000 DP runs, a few minutes
python dashboard.py         # rebuild the HTML from the newest scan file
```

### 2. Make the server reachable — code change required

`pano_sunucu.py` currently binds to `127.0.0.1` (localhost only), so it is **not reachable from a
public IP** until three things change:

1. **Bind address** — `ThreadingHTTPServer(("127.0.0.1", PORT), Islem)` binds to localhost only;
   it must become `"0.0.0.0"` (or your public interface).
2. **`bos_port()`** — it probes `127.0.0.1`; it should probe the same bind address.
3. **`webbrowser.open(adres)`** — pointless (and potentially harmful) on a headless server; it
   should print the public URL instead.

```python
# pano_sunucu.py  — minimal change
HOST = "0.0.0.0"                      # instead of "127.0.0.1"
...
with ThreadingHTTPServer((HOST, PORT), Islem) as sunucu:
```

### 3. Run persistently (systemd)

```ini
# /etc/systemd/system/hezil.service
[Unit]
Description=Hezil HES dashboard server
After=network.target

[Service]
WorkingDirectory=/opt/hezil
ExecStart=/usr/bin/python3 pano_sunucu.py
Restart=always
User=hezil

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now hezil
# quick test without systemd:  nohup python pano_sunucu.py &
```

### 4. Open the firewall

```bash
sudo ufw allow 8765/tcp          # or open port 8765 in your cloud security group
curl http://<PUBLIC_IP>:8765/api/durum   # verify from outside → {"durum":"hazir",...}
```

### 5. Recommended: reverse proxy + HTTPS

Put nginx/Caddy on 80/443 → `127.0.0.1:8765`, with Let's Encrypt TLS. This gives you a clean URL
(e.g. `https://hezil.example.com`), hides the port, and lets you add auth/rate-limiting.

> **Client IPs in `giris_cikis.log`:** behind the proxy every connection comes from `127.0.0.1`,
> so set `GUVENILIR_PROXY=127.0.0.1` in `.env` to log the real client IP from the
> `X-Forwarded-For` header. Keep the proxy's own address there — nothing else, or the header
> becomes spoofable.

---

## Security notes

Before exposing the server publicly, consider:

- **Authentication now exists** (simple, multi-user): credentials live in `.env` (copy
  `.env.example` → `.env`; the server fails fast without it). The dashboard page and all
  `/api/*` endpoints except `giris` / `cikis` / `durum` / `oturum` return 401 without a valid
  session cookie (`hezil_oturum`). Idle timeout defaults to 1 hour (`OTURUM_SURE_S`); every
  login/logout is written to `giris_cikis.log`.
- **Still no rate limiting**: each click triggers a full DP solve (~1–2 s) serialized under one
  global `threading.Lock` → a public instance is trivially DoS-able (only a 0.5 s delay per
  failed login slows brute force). Add rate limiting at the reverse proxy.
- **Auth is client-side for the dashboard itself**: the HTML (with embedded data) is served to
  anyone; the login overlay is JS. If you need the data itself protected, serve `/` as a
  minimal login page instead and/or gate static files at the proxy. Hosting the same HTML on a
  different static host (Path A) bypasses login entirely.
- **`SimpleHTTPRequestHandler` serves the entire repo directory** — source code, input Excel
  files, and the cache are all downloadable (`.py`, `.xlsx`, `.csv` stay public by design). For
  stricter exposure, restrict non-`/api/*` paths or run from a dedicated directory.
- **Don't run as root**; use a dedicated user (`User=hezil` in the systemd unit above).
- **`.env` and `giris_cikis.log` are git-ignored** — never commit credentials.
