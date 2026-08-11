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
        → 0.0.0.0:8765 adresine bağlanır (tüm ağ arayüzleri; dışarıdan
          erişilebilir) ve erişim adresini konsola yazar
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
import re
import secrets
import sys
import json
import time
import socket
import hashlib
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import optimzasyon as opt
from isletme_detay import isletme_serisi
from imalatci_paketi import paket_uret
from govde_enkesit import enkesit_uret

try:
    from dotenv import dotenv_values
except ImportError:
    raise SystemExit(
        "python-dotenv kurulu değil —  venv/bin/pip install python-dotenv  "
        "(veya  pip install python-dotenv) çalıştırın.")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KD = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
HOST = "0.0.0.0"            # tüm ağ arayüzlerinden erişim (ufw 8765 ile uyumlu)
ONBELLEK_KLASOR = os.path.join(KD, "hezil_onbellek")
PANO = "hezil_dashboard.html"

_bellek = {}
_kilit = threading.Lock()
_fse = None

# ---------------------------------------------------------------------------
# GİRİŞ / OTURUM — kimlik doğrulama, oturum yönetimi ve kayıt
# ---------------------------------------------------------------------------
COOKIE_ADI = "hezil_oturum"


def _env_oku():
    """KD/.env dosyasını sözlük olarak okur (os.environ'a dokunmaz)."""
    try:
        return dotenv_values(os.path.join(KD, ".env"))
    except Exception as e:
        print(f"   ! .env okunamadı ({e}) — kullanıcılar boş kabul ediliyor.")
        return {}


_ENV = _env_oku()


def _env_int(anahtar, varsayilan, min_deger=10):
    """.env tamsayısı — geçersiz/çok küçükse varsayılana düşer."""
    try:
        v = int((_ENV.get(anahtar) or "").strip())
    except ValueError:
        v = 0
    if v < min_deger:
        print(f"   ! {anahtar} geçersiz/çok küçük — varsayılan {varsayilan} kullanılıyor.")
        return varsayilan
    return v


def _kullanicilari_oku(env):
    """KULLANICI_<N>_ADI / KULLANICI_<N>_SIFRE çiftlerini sözlüğe çevirir.

    Boş kullanıcı adı veya parola içeren çiftler atlanır; yinelenen adlarda
    sonraki tanım geçerli olur. Parolalar olduğu gibi (trim edilmeden) alınır.
    """
    k = {}
    for anahtar, deger in (env or {}).items():
        m = re.fullmatch(r"KULLANICI_(\d+)_ADI", anahtar)
        if not m:
            continue
        ad = (deger or "").strip()
        sifre = env.get(f"KULLANICI_{m.group(1)}_SIFRE") or ""
        if not ad or not sifre:
            print(f"   ! {anahtar} boş kullanıcı adı/parola — çift atlandı.")
            continue
        if ad in k:
            print(f"   ! '{ad}' yinelenen kullanıcı adı — sonraki tanım geçerli.")
        k[ad] = sifre
    return k


KULLANICILAR = _kullanicilari_oku(_ENV)
OTURUM_SURE_S = _env_int("OTURUM_SURE_S", 3600)
LOG_DOSYASI = ((_ENV.get("LOG_DOSYASI") or "").strip() or "giris_cikis.log")
LOG_YOL = (LOG_DOSYASI if os.path.isabs(LOG_DOSYASI)
           else os.path.join(KD, LOG_DOSYASI))
# Ters vekil (nginx/Caddy) arkasında çalışıyorsa gerçek istemci IP'si
# X-Forwarded-For başlığından alınır — YALNIZCA bağlantı bu güvenilir
# adreslerden birinden geliyorsa (sahtecilik önlenir). Boş = XFF kullanılmaz.
GUVENILIR_PROXY = {s.strip() for s in
                   (_ENV.get("GUVENILIR_PROXY") or "").split(",") if s.strip()}

_oturumlar = {}       # token -> {"kullanici", "son_aktivite", "olusturma", "ip"}
_oturum_kilit = threading.Lock()   # DP kilidinden (DP kilit) ayrıdır
_log_kilit = threading.Lock()
_giris_kilidi = threading.Lock()   # başarısız girişleri sıralar (kaba kuvvet)


def _kayit_ekle(olay, kullanici, ip, neden=""):
    """Giriş/çıkış olayını kayıt dosyasına ekler (thread-güvenli).

    kullanıcı adı istemciden geldiği için, denetim kaydına sahte satır
    eklenmesini (log injection) önlemek amacıyla yeni satırlar temizlenir
    ve uzunluk sınırlanır.
    """
    kullanici = (kullanici or "").replace("\r", " ").replace("\n", " ")[:128]
    satir = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {olay:14s} | "
             f"kullanıcı={kullanici} | ip={ip}"
             + (f" | neden={neden}" if neden else ""))
    with _log_kilit:
        try:
            os.makedirs(os.path.dirname(LOG_YOL), exist_ok=True)
        except OSError:
            pass
        try:
            with open(LOG_YOL, "a", encoding="utf-8") as f:
                f.write(satir + "\n")
        except OSError:
            print("   ! kayıt dosyasına yazılamadı:", satir)


def _yeni_oturum(kullanici, ip):
    token = secrets.token_urlsafe(32)
    with _oturum_kilit:
        _oturumlar[token] = {"kullanici": kullanici,
                             "son_aktivite": time.time(),
                             "olusturma": time.time(),
                             "ip": ip}
    return token


def _oturum_kontrol(token, tazele=False):
    """Token'lı oturumu doğrular (geçersizse None).

    tazele=True ise son_aktivite güncellenir — ancak ÖNCE süre kontrolü yapılır;
    süresi dolmuşsa oturum silinir ve ÇIKIŞ kaydı (süre aşımı) tam bir kez düşülür.
    """
    if not token:
        return None
    sonlanan = None
    with _oturum_kilit:
        o = _oturumlar.get(token)
        if o is None:
            return None
        if time.time() - o["son_aktivite"] > OTURUM_SURE_S:
            del _oturumlar[token]
            sonlanan = o
        elif tazele:
            o["son_aktivite"] = time.time()
    if sonlanan:
        _kayit_ekle("ÇIKIŞ", sonlanan["kullanici"], sonlanan["ip"],
                    "hareketsizlik (süre aşımı)")
    return None if sonlanan else o


def _oturum_sonlandir(token, neden):
    """Oturumu siler; varsa ÇIKIŞ kaydı düşer (elle çıkış vb.)."""
    if not token:
        return None
    with _oturum_kilit:
        o = _oturumlar.pop(token, None)
    if o:
        _kayit_ekle("ÇIKIŞ", o["kullanici"], o["ip"], neden)
    return o


def _temizlikci():
    """Süresi dolan oturumları tarar; kullanıcı bir daha istek yapmasa bile
    otomatik çıkış kaydı düşülür."""
    while True:
        time.sleep(60)
        cikan = []
        with _oturum_kilit:
            simdi = time.time()
            for token, o in list(_oturumlar.items()):
                if simdi - o["son_aktivite"] > OTURUM_SURE_S:
                    del _oturumlar[token]
                    cikan.append(o)
        for o in cikan:
            _kayit_ekle("ÇIKIŞ", o["kullanici"], o["ip"],
                        "hareketsizlik (süre aşımı)")


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

    def _json(self, nesne, kod=200, ek_ustler=None):
        g = json.dumps(nesne, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(g)))
        self.send_header("Cache-Control", "no-store")
        for a, b in (ek_ustler or {}).items():
            self.send_header(a, b)
        self.end_headers()
        self.wfile.write(g)

    def _cerez_al(self):
        """İstek çerezi: 'hezil_oturum' token'ı veya None."""
        for parc in (self.headers.get("Cookie") or "").split(";"):
            if "=" in parc:
                a, b = parc.strip().split("=", 1)
                if a == COOKIE_ADI:
                    return b
        return None

    def _istemci_ip(self):
        """İstemcinin gerçek IP'si (kayıt dosyası için).

        Doğrudan erişimde TCP eşi (peer) zaten gerçek istemcidir. Sunucu bir
        ters vekil arkasındaysa bağlantı vekilin adresinden gelir ve gerçek
        istemci X-Forwarded-For başlığındadır; XFF yalnızca bağlantı
        GUVENILIR_PROXY listesindeki bir adresten geldiğinde güvenilir.
        """
        peer = self.client_address[0]
        if peer in GUVENILIR_PROXY:
            xff = (self.headers.get("X-Forwarded-For") or "").strip()
            if xff:
                return xff.split(",")[0].strip()
        return peer

    def _gelen_veri(self):
        """POST gövdesini form verisi olarak okur (4 KB üst sınır).
        Dönüş: (sözlük, çok_büyük_mü)"""
        try:
            uz = int(self.headers.get("Content-Length", 0))
        except ValueError:
            uz = 0
        if uz > 4096:
            return None, True
        g = self.rfile.read(uz) if uz else b""
        return urllib.parse.parse_qs(g.decode("utf-8", "replace")), False

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)

        if u.path == "/api/oturum":
            o = _oturum_kontrol(self._cerez_al(), tazele=False)   # pasif denetim
            if o is None:
                return self._json({"oturum": False}, 401)
            return self._json({"oturum": True, "kullanici": o["kullanici"]})

        if u.path in ("/", "/index.html"):
            self.path = "/" + PANO
            return SimpleHTTPRequestHandler.do_GET(self)

        if u.path == "/api/durum":
            return self._json({"durum": "hazir", "onbellek": len(_bellek),
                               "port": PORT})

        if u.path == "/api/enkesit":
            if _oturum_kontrol(self._cerez_al(), tazele=True) is None:
                return self._json({"hata": "oturum geçersiz — giriş yapın"}, 401)
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
            if _oturum_kontrol(self._cerez_al(), tazele=True) is None:
                return self._json({"hata": "oturum geçersiz — giriş yapın"}, 401)
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
            if _oturum_kontrol(self._cerez_al(), tazele=True) is None:
                return self._json({"hata": "oturum geçersiz — giriş yapın"}, 401)
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

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/giris":
            return self._giris()
        if u.path == "/api/cikis":
            return self._cikis()
        if u.path == "/api/nabiz":
            return self._nabiz()
        return self._json({"hata": "bulunamadı"}, 404)

    def _giris(self):
        ip = self._istemci_ip()
        p, buyuk = self._gelen_veri()
        if buyuk:
            return self._json({"hata": "istek çok büyük"}, 413)
        kadi = (p.get("kullanici", [""])[0] or "").strip()[:64]
        sifre = p.get("sifre", [""])[0] or ""
        if not kadi or not sifre:
            return self._json({"hata": "kullanıcı adı ve parola gereklidir"}, 400)
        if KULLANICILAR.get(kadi) == sifre:
            token = _yeni_oturum(kadi, ip)
            _kayit_ekle("GİRİŞ", kadi, ip)
            cerez = (f"{COOKIE_ADI}={token}; Path=/; HttpOnly; "
                     f"SameSite=Lax")
            return self._json({"ok": True, "kullanici": kadi},
                              ek_ustler={"Set-Cookie": cerez})
        _kayit_ekle("HATALI GİRİŞ", kadi, ip)
        with _giris_kilidi:                # başarısız girişler SIRAYLA bekletilir
            time.sleep(0.5)                # (eşzamanlı bağlantılarla aşılmasın diye)
        return self._json({"hata": "kullanıcı adı veya parola hatalı"}, 401)

    def _cikis(self):
        _oturum_sonlandir(self._cerez_al(), "elle (çıkış düğmesi)")
        cerez = (f"{COOKIE_ADI}=; Path=/; HttpOnly; SameSite=Lax; "
                 f"Max-Age=0")
        return self._json({"ok": True}, ek_ustler={"Set-Cookie": cerez})

    def _nabiz(self):
        o = _oturum_kontrol(self._cerez_al(), tazele=True)
        if o is None:
            return self._json({"oturum": False}, 401)
        return self._json({"ok": True, "kullanici": o["kullanici"]})


def bos_port(p):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # sunucuyla aynı davranış
        try:
            s.bind((HOST, p))
            return True
        except OSError:
            return False


def _yerel_ip():
    """Sunucunun dışarıdan erişilebileceği ağ adresini bul (yoksa 127.0.0.1)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def main():
    global PORT
    if not os.path.exists(os.path.join(KD, PANO)):
        raise SystemExit(f"{PANO} yok — önce  python dashboard.py  çalıştırın.")
    if not KULLANICILAR:
        raise SystemExit(
            "\n[GİRİŞ HATASI] Kullanıcı tanımlı değil — sunucu başlatılamıyor.\n"
            f"  Aranan dosya : {os.path.join(KD, '.env')}\n"
            "  Olası neden  : .env yok, okunamadı veya içinde kullanıcı çifti yok.\n"
            "  Çözüm: .env.example dosyasını '.env' olarak kopyalayın ve\n"
            "         KULLANICI_1_ADI / KULLANICI_1_SIFRE değerlerini doldurun.\n")
    try:
        with open(os.path.join(KD, PANO), encoding="utf-8") as f:
            if 'id="girisKatmani"' not in f.read():
                print("!! UYARI: hezil_dashboard.html oturum özelliği OLMADAN üretilmiş.")
                print("!!        Giriş formu görünmez — önce  python dashboard.py  çalıştırın.")
    except OSError:
        pass
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
    print(f"Kullanıcı: {len(KULLANICILAR)}  ·  süre aşımı: {OTURUM_SURE_S} sn  "
          f"·  kayıt: {LOG_DOSYASI}")
    _fiyat()
    ip = _yerel_ip()
    adres = f"http://{ip}:{PORT}"
    print(f"\nADRES   : {adres}   (yerel: http://127.0.0.1:{PORT})")
    print("Panodaki herhangi bir noktaya tıklayın; işletme çalışması burada")
    print("çözülüp panoya döner. Durdurmak için Ctrl+C.\n")

    threading.Thread(target=_temizlikci, daemon=True).start()
    with ThreadingHTTPServer((HOST, PORT), Islem) as sunucu:
        try:
            sunucu.serve_forever()
        except KeyboardInterrupt:
            print("\nSunucu durduruldu.")


if __name__ == "__main__":
    main()
