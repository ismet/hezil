# -*- coding: utf-8 -*-
"""
================================================================================
HEZİL HES — PANO SUNUCUSU (işletme çalışmasını arka planda çözer)
================================================================================

Panoda bir alternatife tıklandığında o konfigürasyonun İŞLETME ÇALIŞMASI bu
sunucuda ANLIK olarak dinamik programlama ile çözülür ve sonuç panoya JSON
olarak döner. Böylece:

  · HTML'e yüzlerce seri gömmek gerekmez (dosya ~1 MB'a iner)
  · Taramadaki 1512 alternatifin HEPSİ incelenebilir (önceden seçilmiş
    26 tanesi değil)
  · Sonuçlar bellekte ve diskte önbelleğe alınır; ikinci tıklama anında gelir

KULLANIM
--------
    python pano_sunucu.py
        → http://127.0.0.1:8765 adresini tarayıcıda açar
        → durdurmak için Ctrl+C

Sunucu çalışmadan HTML'e çift tıklanırsa pano yine açılır; yalnızca işletme
çalışması bölümü "sunucuyu başlatın" uyarısı verir (gömülü detay varsa onu
kullanır).

NOT: Dinamik programlama modül düzeyindeki global girdileri (çap, debi, kot …)
değiştirdiği için hesaplar bir KİLİT altında sırayla yapılır; eşzamanlı istekler
birbirinin girdisini bozmaz.
================================================================================
"""

import os
import sys
import json
import time
import socket
import hashlib
import threading
import webbrowser
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import optimzasyon as opt
from isletme_detay import isletme_serisi
from imalatci_paketi import paket_uret
from govde_enkesit import enkesit_uret

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KD = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
ONBELLEK_KLASOR = os.path.join(KD, "hezil_onbellek")
PANO = "hezil_dashboard.html"

_bellek = {}
_kilit = threading.Lock()
_fse = None


def _fiyat():
    global _fse
    if _fse is None:
        ptf, kaynak = opt.ptf_oku(os.path.join(KD, opt.PTF_DOSYASI))
        _fse = opt.FiyatSureEgrisi(ptf)
        print(f"   fiyat-süre eğrileri kuruldu ({kaynak})")
    return _fse


def _anahtar(dt, q, vc, km, amac):
    return f"{dt:.1f}_{q:.1f}_{vc:.1f}_{km:.0f}_{amac}"


def _disk_yol(a):
    os.makedirs(ONBELLEK_KLASOR, exist_ok=True)
    return os.path.join(ONBELLEK_KLASOR, a + ".json")


def isletme(dt, q, vc, km, amac):
    """Önbellekten getir, yoksa DP ile çöz."""
    a = _anahtar(dt, q, vc, km, amac)
    if a in _bellek:
        return _bellek[a], "bellek"

    dy = _disk_yol(a)
    if os.path.exists(dy):
        with open(dy, encoding="utf-8") as f:
            _bellek[a] = json.load(f)
        return _bellek[a], "disk"

    with _kilit:                      # DP global girdileri değiştirir
        if a in _bellek:              # kilidi beklerken başkası hesaplamış olabilir
            return _bellek[a], "bellek"
        t0 = time.time()
        r = isletme_serisi(dt, q, vc, km, amac, _fiyat())
        sure = time.time() - t0
    r["sure_s"] = round(sure, 2)
    _bellek[a] = r
    with open(dy, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, separators=(",", ":"))
    return r, f"hesaplandı ({sure:.1f} s)"


class Islem(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=KD, **k)

    def log_message(self, fmt, *args):
        pass                          # varsayılan gürültülü günlüğü kapat

    def _json(self, nesne, kod=200):
        g = json.dumps(nesne, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(g)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(g)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)

        if u.path in ("/", "/index.html"):
            self.path = "/" + PANO
            return SimpleHTTPRequestHandler.do_GET(self)

        if u.path == "/api/durum":
            return self._json({"durum": "hazir", "onbellek": len(_bellek),
                               "port": PORT})

        if u.path == "/api/enkesit":
            p = urllib.parse.parse_qs(u.query)
            try:
                dt = float(p["dt"][0]); q = float(p["q"][0])
                vc = float(p["vc"][0]); km = float(p["km"][0])
                amac = p.get("amac", ["gelir"])[0]
                et = p.get("etiket", ["seçilen"])[0]
            except Exception as e:
                return self._json({"hata": f"geçersiz istek: {e}"}, 400)
            print(f"   /api/enkesit  D={dt:.1f} Q={q:.1f} kot={km:.0f}"
                  f" → en kesit çiziliyor…")
            try:
                with _kilit:
                    t0 = time.time()
                    r = enkesit_uret(dt, q, vc, km, et, amac, _fiyat(),
                                     yaz=lambda *a: None)
                    r["sure_s"] = round(time.time() - t0, 1)
            except Exception as e:
                import traceback; traceback.print_exc()
                return self._json({"hata": f"en kesit çizilemedi: {e}"}, 500)
            print(f"      → {r['png']}  ({r['sure_s']} s)")
            return self._json(r)

        if u.path == "/api/imalatci":
            p = urllib.parse.parse_qs(u.query)
            try:
                dt = float(p["dt"][0]); q = float(p["q"][0])
                vc = float(p["vc"][0]); km = float(p["km"][0])
                amac = p.get("amac", ["gelir"])[0]
                if amac not in ("gelir", "enerji"):
                    raise ValueError("amac 'gelir' veya 'enerji' olmalı")
            except Exception as e:
                return self._json({"hata": f"geçersiz istek: {e}"}, 400)
            print(f"   /api/imalatci D={dt:.1f} Q={q:.1f} v_c={vc:.1f} "
                  f"kot={km:.0f} {amac} → paket üretiliyor…")
            try:
                with _kilit:              # DP + matplotlib global durum kullanır
                    t0 = time.time()
                    r = paket_uret(dt, q, vc, km, amac, _fiyat(),
                                   yaz=lambda *a: None)
                    r["sure_s"] = round(time.time() - t0, 1)
            except Exception as e:
                import traceback; traceback.print_exc()
                return self._json({"hata": f"paket üretilemedi: {e}"}, 500)
            print(f"      → {r['png']}  ({r['sure_s']} s)")
            return self._json(r)

        if u.path == "/api/isletme":
            p = urllib.parse.parse_qs(u.query)
            try:
                dt = float(p["dt"][0]); q = float(p["q"][0])
                vc = float(p["vc"][0]); km = float(p["km"][0])
                amac = p.get("amac", ["gelir"])[0]
                if amac not in ("gelir", "enerji"):
                    raise ValueError("amac 'gelir' veya 'enerji' olmalı")
            except Exception as e:
                return self._json({"hata": f"geçersiz istek: {e}"}, 400)
            try:
                r, kaynak = isletme(dt, q, vc, km, amac)
            except Exception as e:
                return self._json({"hata": f"çözüm hatası: {e}"}, 500)
            print(f"   /api/isletme  D={dt:.1f} Q={q:.1f} v_c={vc:.1f} "
                  f"kot={km:.0f} {amac:6s} → {kaynak}")
            return self._json({"veri": r, "kaynak": kaynak,
                               "dt": dt, "q": q, "vc": vc, "km": km,
                               "amac": amac})

        return SimpleHTTPRequestHandler.do_GET(self)


def bos_port(p):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", p))
            return True
        except OSError:
            return False


def main():
    global PORT
    if not os.path.exists(os.path.join(KD, PANO)):
        raise SystemExit(f"{PANO} yok — önce  python dashboard.py  çalıştırın.")
    while not bos_port(PORT) and PORT < 8790:
        PORT += 1

    print("=" * 84)
    print("HEZİL HES — PANO SUNUCUSU")
    print("=" * 84)
    print(f"Klasör  : {KD}")
    print(f"Hidroloji: {opt.AKIM_YILLARI[0]}–{opt.AKIM_YILLARI[-1]} "
          f"({len(opt.AKIM_YILLARI)} su yılı)")
    n = len(os.listdir(ONBELLEK_KLASOR)) if os.path.isdir(ONBELLEK_KLASOR) else 0
    print(f"Önbellek: {n} kayıt  ({ONBELLEK_KLASOR})")
    _fiyat()
    adres = f"http://127.0.0.1:{PORT}"
    print(f"\nADRES   : {adres}")
    print("Panodaki herhangi bir noktaya tıklayın; işletme çalışması burada")
    print("çözülüp panoya döner. Durdurmak için Ctrl+C.\n")

    try:
        webbrowser.open(adres)
    except Exception:
        pass

    with ThreadingHTTPServer(("127.0.0.1", PORT), Islem) as sunucu:
        try:
            sunucu.serve_forever()
        except KeyboardInterrupt:
            print("\nSunucu durduruldu.")


if __name__ == "__main__":
    main()
