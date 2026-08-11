# -*- coding: utf-8 -*-
"""
================================================================================
HEZİL BARAJI ve HES — REZERVUAR İŞLETME OPTİMİZASYONU (DİNAMİK PROGRAMLAMA)
================================================================================

AMAÇ
-----
Aylık gelen akımlar (giris_akimlari.xlsx) ve kot-alan-hacim eğrisi
(kot_alan_hacim.xlsx) kullanılarak,
basınçlı iletim sistemli (tünel + cebri boru) bir HES için aylık rezervuar
işletme politikasının, PİYASA GELİRİNİ (PTF) maksimize edecek şekilde
DETERMİNİSTİK DİNAMİK PROGRAMLAMA ile belirlenmesi.

"PİK FAYDA" (implicit puant değerlemesi)
----------------------------------------
Santralin ay içinde sürekli değil, PUANT saatlerde tam yükte çalıştığı kabul
edilir. Bir ayda türbinlerden geçirilen su hacmi W ise, işletme debisi Q_op'ta
santral N = W / Q_op saat çalışır. Bu N saatlik üretimin, o ayın SAATLİK PTF
serisindeki EN YÜKSEK N adet fiyattan satıldığı varsayılır:

        Gelir(N) = P_tamyük [MW] × Σ(o ayın en yüksek N adet PTF'si) [TL/MWh·h]

Bu, fiyat-süre eğrisinin altındaki alanın ilk N saatidir; N arttıkça marjinal
fiyat düştüğü için gelir fonksiyonu ENERJİYE GÖRE İÇBÜKEY (concave) olur.
Dinamik programlama bu içbükey fayda fonksiyonunu doğrudan kullanır — depolanan
suyun "su değeri" (marjinal değeri) DP'nin değer fonksiyonundan implicit çıkar.

KARAR DEĞİŞKENİ (her ay için, birlikte optimize edilir)
-------------------------------------------------------
  (a) O ay türbinlerden geçirilecek toplam su hacmi  W   → depolama kararı
  (b) O ayki işletme modu (kaç ünite / hangi yükte)  Q_op → puantlaşma kararı
      Düşük Q_op  → yük kaybı az, birim su başına enerji YÜKSEK, ama çok saat
                    çalışıldığı için yakalanan ortalama fiyat DÜŞÜK
      Yüksek Q_op → yük kaybı Q² ile artar, enerji DÜŞÜK, ama az saatte
                    çalışılıp en pahalı saatler yakalanır
      DP bu ödünleşmeyi (trade-off) her ay ayrı ayrı çözer.

DURUM DEĞİŞKENİ : Ay başı rezervuar hacmi (min. su seviyesi ↔ maks. su seviyesi)
AŞAMA           : su yılı sayısı × 12 ay, Ekim → Eylül su yılı

FİYAT VERİSİ
------------
PTF_DOSYASI / PTF_SUTUNU ile saatlik fiyat serisi okunur. İki biçim desteklenir:
  (a) EPİAŞ dışa aktarımı        : Tarih + Saat + PTF sütunlu csv/xlsx
  (b) yıllık işletme tablosu     : 0…8759 saat indeksi + fiyat sütunu
                                   (takvim PTF_SERI_BASI'ndan kurulur)
Varsayılan : res_operation_table_8760rows.csv → 'price' sütunu, EUR/MWh.
Dosya bulunamazsa TEMSİLİ (sentetik) bir seri üretilir; o durumda mutlak gelir
rakamları gösterge niteliğindedir.

ÇIKTILAR
--------
  hezil_dp_sonuclar.xlsx : Özet / Ortalama Aylık / Yıllık Özet / Aylık İşletme /
                           Fiyat Özeti sayfaları
  hezil_dp_sonuclar.png  : grafikler

ALTERNATİF TARAMASI
-------------------
Girdi sabitleri değiştirilip yeniden_kur() çağrılarak model tazelenebilir;
alternatifler.py bu yolla tünel çapı / tasarım debisi / minimum kot taraması yapar.
================================================================================
"""

import os
import sys
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ==============================================================================
# 1) KULLANICI GİRDİLERİ
# ==============================================================================

# ---- Rezervuar ---------------------------------------------------------------
KOT_MAKS       = 755.0      # Maksimum işletme su seviyesi (normal su seviyesi)  [m]
KOT_MIN        = 720.0      # Minimum işletme su seviyesi                        [m]
KOT_KUYRUK     = 574.0      # Kuyruk suyu seviyesi                               [m]

# Kot – Alan – Hacim tablosu: kot_alan_hacim.xlsx dosyasından okunur
# (sütunlar: kot [m] · alan [km2] · hacim [hm3])
KAH_DOSYASI = "kot_alan_hacim.xlsx"

# ---- Türbin / santral --------------------------------------------------------
Q_TASARIM       = 60.0      # Toplam tasarım debisi                             [m3/s]
UNITE_SAYISI    = 2         # Ünite sayısı (2 × 30 m3/s Francis)
ETA_JENERATOR   = 0.975     # Jeneratör verimi
ETA_TRAFO       = 0.995     # Trafo + mekanik verim
UNITE_MIN_YUK   = 0.55      # Bir ünitenin sürekli çalışabildiği en düşük yük oranı

# ---- TÜRBİN VERİM EĞRİSİ — İMALATÇI VERİSİ ----------------------------------
# Kaynak : HPWE / KOCHENDÖRFER Hydro Elektromekanik, "Hezil 2 HPP",
#          Francis spiral turbine, n = 375 rpm, D = 1.82 m,
#          Hn = 167.27 m, 2 ünite × 30 m3/s, P_max = 46.240 kW  (21.08.2025)
# Eğri TÜRBİN verimidir; jeneratör ve trafo verimi ayrıca çarpılır.
# Doğrulama: 9.81 × 30 × 167.27 × 0.941 = 46.318 kW ≈ 46.240 kW (imalatçı) ✓
VERIM_Q_UNITE = np.array([   8.0,   9.0,  12.0,  15.0,  18.0,
                            21.0,  24.0,  27.0,  28.5,  30.0])   # [m3/s] ünite debisi
VERIM_TURBIN  = np.array([0.634, 0.693, 0.826, 0.869, 0.909,
                          0.932, 0.947, 0.949, 0.945, 0.941])    # türbin verimi [-]
# Yük oranına (Q_ünite / Q_ünite,tasarım) çevrilir. Alternatif taramasında ünite
# boyutu değiştiğinde eğri HOMOLOG kabul edilir (yük oranına göre aynı şekil);
# bu ön tasarım aşamasında olağan kabuldür, kesin değerler imalatçıdan alınmalıdır.
VERIM_YUK = VERIM_Q_UNITE / VERIM_Q_UNITE[-1]
ETA_TURBIN_MAKS = float(VERIM_TURBIN.max())     # 0.949 @ %90 yük (bilgi amaçlı)

# ---- İletim hattı (BASINÇLI SİSTEM) -----------------------------------------
# Pürüzlülük ve yerel kayıp katsayıları Hezil_Hidrolik_Kayip_Hesabi.xlsx ile uyumlu
TUNEL_D     = 4.40      # Enerji tüneli iç çapı                                  [m]
TUNEL_L     = 4600.0    # Enerji tüneli uzunluğu                                 [m]
TUNEL_EPS   = 0.0010    # Betonarme kaplama eşdeğer pürüzlülüğü                  [m]
TUNEL_SUM_K = 2.173     # Tünel yerel kayıp Σ K (dirsekler, denge bacası, geçiş)

CEBRI_D     = 3.90      # Cebri boru iç çapı (bifürkasyon öncesi)                [m]
CEBRI_L     = 300.0     # Cebri boru uzunluğu                                    [m]
CEBRI_EPS   = 0.0005    # Boyalı kaynaklı çelik eşdeğer pürüzlülüğü              [m]
CEBRI_SUM_K = 1.167     # Cebri boru yerel kayıp Σ K (vana, dirsek, bifürkasyon)

KOL_D       = 2.00      # Bifürkasyon sonrası kol (ünite başına)                 [m]
KOL_L       = 35.0      # Kol uzunluğu                                           [m]
KOL_EPS     = 0.0005    # Çelik                                                  [m]
KOL_SUM_K   = 0.381     # Kol yerel kayıp Σ K (dirsek + kelebek vana)

GIRIS_KAYIP_60 = 0.415  # Giriş yapısı toplam kaybı @ Q=60 m3/s (ızgara, kapak
                        # yuvaları, geçişler); Q² ile ölçeklenir                 [m]

NU_SU = 1.0e-6          # Kinematik viskozite (~10 °C)                        [m2/s]
G     = 9.81            # Yerçekimi ivmesi                                    [m/s2]

# ---- İşletme kısıtları -------------------------------------------------------
# "Bırakılacak Nihai Su Miktarı" (can suyu) — SU YILI SIRASI: Ekim → Eylül [m3/s]
# Türbin dışından (dip savak / eko-santral) bırakılır, enerji üretmez sayılmıştır.
# Mecburi bırakma önceliklidir; rezervuar minimum kota dayanırsa mevcut su kadarı
# bırakılabilir.
CAN_SUYU_AYLIK = np.array([
    # Ekim   Kasım  Aralık   Ocak  Şubat   Mart  Nisan  Mayıs Haziran Temmuz Ağustos Eylül
      3.758, 3.750, 3.750, 3.750, 3.750, 5.524, 7.506, 5.788, 3.821, 3.834, 3.823, 3.792])

BASLANGIC_KOTU = 720.0  # Su yılı başında (1 Ekim) rezervuar kotu                [m]
                        # Serinin sonunda hacim ≥ başlangıç hacmi zorlanır
                        # (DP uç etkisinin giderilmesi)

# ---- Piyasa / PTF ------------------------------------------------------------
PTF_DOSYASI      = "res_operation_table_8760rows.csv"   # saatlik fiyat dosyası
PTF_SUTUNU       = "price"        # fiyat sütunu adı (boş bırakılırsa otomatik bulunur)
PTF_PARA_BIRIMI  = "EUR/MWh"
PTF_SERI_BASI    = "2025-08-01"   # Dosyada gerçek tarih yoksa (0…8759 saat indeksi)
                                  # serinin başladığı tarih — veri AĞUSTOS'ta başlıyor
PTF_SENTETIK_ORT = 45.0           # Dosya bulunamazsa üretilen temsili serinin
                                  # yıllık ortalaması [PTF_PARA_BIRIMI]

# ---- AMAÇ FONKSİYONU ---------------------------------------------------------
# "gelir"  : PİK (puant) İŞLETME — santral ay içinde az saatte tam yükte çalışır,
#            üretim o ayın en pahalı saatlerinden satılır. Yüksek işletme debisi
#            yük kaybını Q² ile büyüttüğü için birim sudan alınan enerji düşer;
#            DP bu enerji kaybını fiyat kazancıyla tartar.
# "enerji" : PİK OLMAYAN (bant) İŞLETME — amaç yalnızca ÜRETİLEN ENERJİYİ
#            maksimize etmektir. DP en düşük yük kayıplı işletme modunu ve uzun
#            çalışma süresini seçer. Üretim aya yayıldığı için gelir, o ayın
#            ORTALAMA fiyatından hesaplanır (saat seçimi yapılmaz).
AMAC = "gelir"          # "gelir" | "enerji"

# ---- Sayısal çözüm ayarları --------------------------------------------------
N_DURUM = 71            # Hacim (durum) ızgarası düğüm sayısı
N_KARAR = 81            # Aylık türbin debisi (karar) ızgarası düğüm sayısı
CEZA    = 1e15          # Uygunsuz geçişler için ceza

# ==============================================================================
# 2) HİDROLOJİ — Aylık gelen akımlar, su yılı: EKİM → EYLÜL
#
#    KAYNAK : giris_akimlari.xlsx  ("Hezil HES YÜZEY AKIMLARI")
#    BİRİM  : dosyada aylık HACİM (hm³) verilmiştir; model debi (m3/s) ile
#             çalıştığı için  Q = V·1e6 / (ay_gün · 86400)  ile çevrilir.
#             Çevrimde ayın gün sayısı AY_GUN tablosundan alınır (Şubat 28).
#    DÖNEM  : dosyadaki yıl satırlarının tamamı okunur (su yılı = Ekim–Eylül).
# ==============================================================================

AY_ADLARI = ["Ekim", "Kasım", "Aralık", "Ocak", "Şubat", "Mart",
             "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül"]
TAKVIM_AYI = [10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9]   # su yılı ayı → takvim ayı
AY_GUN = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
          7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

AKIM_DOSYASI = "giris_akimlari.xlsx"

_KD = os.path.dirname(os.path.abspath(__file__))


def _akim_oku(yol):
    """giris_akimlari.xlsx → (yıllar, hacim [hm3], debi [m3/s]).
    Başlık satırları ve ORT. satırı, ilk sütunu geçerli bir yıl olmayan satırlar
    olarak kendiliğinden elenir."""
    d = pd.read_excel(yol, header=None)
    yil, hac = [], []
    for _, r in d.iterrows():
        try:
            y = int(r.iloc[0])
        except (TypeError, ValueError):
            continue
        if not (1900 <= y <= 2100):
            continue
        v = pd.to_numeric(r.iloc[1:13], errors="coerce").to_numpy(dtype=float)
        if v.size != 12 or np.isnan(v).any():
            continue
        yil.append(y)
        hac.append(v)
    if not yil:
        raise SystemExit(f"Akım dosyasında yıl satırı bulunamadı: {yol}")
    hac = np.array(hac, float)
    gun = np.array([AY_GUN[a] for a in TAKVIM_AYI], float)
    debi = hac * 1e6 / (gun * 86400.0)
    return yil, hac, debi


def _kah_oku(yol):
    """kot_alan_hacim.xlsx → [[kot, alan, hacim], …] (kota göre artan)."""
    d = pd.read_excel(yol, header=None)
    sat = []
    for _, r in d.iterrows():
        v = pd.to_numeric(r.iloc[1:4], errors="coerce").to_numpy(dtype=float)
        if v.size == 3 and not np.isnan(v).any():
            sat.append(v)
    if len(sat) < 3:
        raise SystemExit(f"Kot-alan-hacim tablosu okunamadı: {yol}")
    a = np.array(sat, float)
    return a[np.argsort(a[:, 0])]


AKIM_YILLARI, AKIM_HACIM_HM3, AKIMLAR = _akim_oku(
    os.path.join(_KD, AKIM_DOSYASI))
KAH = _kah_oku(os.path.join(_KD, KAH_DOSYASI))

assert AKIMLAR.shape[1] == 12, "Akım tablosu 12 aylık olmalı"


# ==============================================================================
# 3) KOT – ALAN – HACİM İLİŞKİSİ
# ==============================================================================

def _monoton_kubik(x, y):
    """Monoton kübik Hermite (PCHIP) interpolasyon. scipy varsa onu kullanır."""
    try:
        from scipy.interpolate import PchipInterpolator
        return PchipInterpolator(np.asarray(x, float), np.asarray(y, float),
                                 extrapolate=True)
    except Exception:                                   # saf numpy yedeği
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        h = np.diff(x)
        d = np.diff(y) / h
        m = np.zeros_like(y)
        m[1:-1] = np.where(d[:-1] * d[1:] > 0,
                           2.0 / (1.0 / d[:-1] + 1.0 / d[1:]), 0.0)
        m[0], m[-1] = d[0], d[-1]

        def f(xq):
            xq = np.atleast_1d(np.asarray(xq, float))
            i = np.clip(np.searchsorted(x, xq) - 1, 0, len(x) - 2)
            t = (xq - x[i]) / h[i]
            return ((2*t**3 - 3*t**2 + 1) * y[i]
                    + (t**3 - 2*t**2 + t) * h[i] * m[i]
                    + (-2*t**3 + 3*t**2) * y[i+1]
                    + (t**3 - t**2) * h[i] * m[i+1])
        return f


_f_kot2hacim = _monoton_kubik(KAH[:, 0], KAH[:, 2])    # kot [m]    → hacim [hm3]
_f_kot2alan  = _monoton_kubik(KAH[:, 0], KAH[:, 1])    # kot [m]    → alan  [km2]

# Ters ilişki (hacim → kot) AYRI bir eğri uydurularak değil, kot→hacim eğrisinin
# sayısal tersi alınarak kurulur; aksi halde kot(hacim(z)) ≠ z olur (uçlarda
# 1 m'yi aşan tutarsızlık) ve düşü hesabı hatalanır.
_KOT_IZG = np.linspace(KAH[0, 0], KAH[-1, 0], 8001)
_HAC_IZG = np.maximum.accumulate(np.asarray(_f_kot2hacim(_KOT_IZG), float))


def hacim(k):
    return np.asarray(_f_kot2hacim(k), float)


def kot(v):
    return np.interp(np.asarray(v, float), _HAC_IZG, _KOT_IZG)


# ==============================================================================
# 4) HİDROLİK YÜK KAYIPLARI ve GÜÇ (basınçlı sistem)
#    Darcy-Weisbach (Swamee-Jain) sürtünme + Σ K·v²/2g yerel kayıplar
# ==============================================================================

def _f_swamee_jain(Q, D, eps):
    """Sürtünme faktörü — Swamee-Jain (Colebrook-White'ın açık formu)."""
    Q = np.maximum(np.asarray(Q, float), 1e-9)
    V = Q / (np.pi * D**2 / 4.0)
    Re = np.maximum(V * D / NU_SU, 4000.0)
    return 0.25 / (np.log10(eps / (3.7 * D) + 5.74 / Re**0.9))**2


def yuk_kaybi(Q_toplam):
    """Toplam yük kaybı [m] — verilen TOPLAM santral debisi için.
    Tünel ve cebri boru toplam debiyi, kollar ünite başına debiyi taşır."""
    Q  = np.asarray(Q_toplam, float)
    Qk = Q / UNITE_SAYISI                       # kol (ünite) debisi

    def hf(Qx, D, L, eps):                      # hf = 0.0826·f·L·Q²/D⁵
        return 0.0826 * _f_swamee_jain(Qx, D, eps) * L * Qx**2 / D**5

    def hv(Qx, D):                              # hız yükü v²/2g
        return (Qx / (np.pi * D**2 / 4.0))**2 / (2.0 * G)

    h = GIRIS_KAYIP_60 * (Q / Q_TASARIM)**2                             # giriş yapısı
    h = h + hf(Q,  TUNEL_D, TUNEL_L, TUNEL_EPS) + TUNEL_SUM_K * hv(Q,  TUNEL_D)
    h = h + hf(Q,  CEBRI_D, CEBRI_L, CEBRI_EPS) + CEBRI_SUM_K * hv(Q,  CEBRI_D)
    h = h + hf(Qk, KOL_D,   KOL_L,   KOL_EPS)   + KOL_SUM_K   * hv(Qk, KOL_D)
    return h


def yuk_kaybi_detay(Q_toplam):
    """Yük kaybı DÖKÜMÜ [m] — sürtünme ve yerel kayıplar ayrı ayrı.
    yuk_kaybi() ile birebir aynı modeli kullanır; yalnız raporlama içindir
    (DP döngüsünde çağrılmaz, orada hızlı yuk_kaybi() kullanılır)."""
    Q  = float(Q_toplam)
    Qk = Q / UNITE_SAYISI

    def hf(Qx, D, L, eps):
        return float(0.0826 * _f_swamee_jain(Qx, D, eps) * L * Qx**2 / D**5)

    def hv(Qx, D):
        return (Qx / (np.pi * D**2 / 4.0))**2 / (2.0 * G)

    d = {
        "Giriş yapısı (yerel)":        GIRIS_KAYIP_60 * (Q / Q_TASARIM)**2,
        "Tünel — sürtünme":            hf(Q,  TUNEL_D, TUNEL_L, TUNEL_EPS),
        "Tünel — yerel":               TUNEL_SUM_K * hv(Q,  TUNEL_D),
        "Cebri boru — sürtünme":       hf(Q,  CEBRI_D, CEBRI_L, CEBRI_EPS),
        "Cebri boru — yerel":          CEBRI_SUM_K * hv(Q,  CEBRI_D),
        "Kol — sürtünme":              hf(Qk, KOL_D,   KOL_L,   KOL_EPS),
        "Kol — yerel":                 KOL_SUM_K * hv(Qk, KOL_D),
    }
    d["SÜRTÜNME TOPLAMI"] = sum(v for k, v in d.items() if "sürtünme" in k)
    d["YEREL TOPLAMI"]    = sum(v for k, v in d.items() if "yerel" in k)
    d["TOPLAM KAYIP"]     = d["SÜRTÜNME TOPLAMI"] + d["YEREL TOPLAMI"]
    return d


def turbin_verimi(yuk_orani):
    """Ünite yük oranına (Q_ünite / Q_ünite,tasarım) bağlı TÜRBİN verimi.
    İmalatçı eğrisinden (VERIM_YUK / VERIM_TURBIN) doğrudan interpolasyon."""
    return np.interp(yuk_orani, VERIM_YUK, VERIM_TURBIN,
                     left=VERIM_TURBIN[0], right=VERIM_TURBIN[-1])


def guc_MW(Q_op, kot_rez, mod_idx=None):
    """İşletme debisi ve rezervuar kotunda santral gücü [MW] ve net düşü [m]."""
    Q_op = np.asarray(Q_op, float)
    if mod_idx is None:                        # en yakın işletme moduna eşle
        mod_idx = int(np.argmin(np.abs(_MOD_Q - float(np.atleast_1d(Q_op)[0]))))
    H_net = np.maximum(np.asarray(kot_rez, float) - KOT_KUYRUK - yuk_kaybi(Q_op), 0.0)
    eta = turbin_verimi(Q_op / (_MOD_N[mod_idx] * Q_UNITE)) * ETA_JENERATOR * ETA_TRAFO
    return G * Q_op * H_net * eta / 1000.0, H_net


# ==============================================================================
#    TÜRETİLMİŞ BÜYÜKLÜKLER
#    Girdi sabitleri (çap, tasarım debisi, min./maks. kot …) değiştirildikten
#    sonra yeniden_kur() çağrılarak hepsi tazelenir. Alternatif taramaları
#    (bkz. alternatifler.py) bu mekanizmayı kullanır.
# ==============================================================================

def yeniden_kur():
    """Girdi sabitlerinden türetilen bütün büyüklükleri yeniden hesaplar."""
    global V_MAKS, V_MIN, V_AKTIF, V_BASLANGIC, Q_UNITE
    global _MOD, _MOD_Q, _MOD_N, _MOD_YUK, _MOD_AD, _MOD_ETA, _MOD_KAYIP
    global P_KURULU, H_NET_TASARIM

    V_MAKS      = float(hacim(KOT_MAKS))
    V_MIN       = float(hacim(KOT_MIN))
    V_AKTIF     = V_MAKS - V_MIN
    V_BASLANGIC = float(hacim(BASLANGIC_KOTU))

    # İşletme modları (kaç ünite × hangi yükte)
    Q_UNITE = Q_TASARIM / UNITE_SAYISI
    yukler = [1.00, 0.90, 0.80, 0.70, UNITE_MIN_YUK]
    m = {}
    for n in range(1, UNITE_SAYISI + 1):
        for y in yukler:
            q = n * Q_UNITE * y
            # aynı debi birden çok kombinasyonla elde edilebilir → daha yüksek
            # yükte (daha az ünite ile) çalışmak daha verimlidir, onu sakla
            a = round(q, 4)
            if a not in m or y > m[a][2]:
                m[a] = (q, n, y)

    _MOD      = sorted(m.values())
    _MOD_Q    = np.array([x[0] for x in _MOD])          # işletme debisi   [m3/s]
    _MOD_N    = np.array([x[1] for x in _MOD])          # çalışan ünite sayısı
    _MOD_YUK  = np.array([x[2] for x in _MOD])          # ünite yük oranı
    _MOD_AD   = [f"{n}Ü×%{y*100:.0f}" for _, n, y in _MOD]
    _MOD_ETA  = turbin_verimi(_MOD_YUK) * ETA_JENERATOR * ETA_TRAFO
    _MOD_KAYIP = yuk_kaybi(_MOD_Q)

    # Kurulu güç: bütün üniteler tam yükte, maksimum su seviyesinde
    P, H = guc_MW(Q_TASARIM, KOT_MAKS, mod_idx=len(_MOD) - 1)
    P_KURULU      = float(np.atleast_1d(P)[0])
    H_NET_TASARIM = float(np.atleast_1d(H)[0])


yeniden_kur()


# ==============================================================================
# 5) PTF — SON 1 YIL SAATLİK FİYATLAR ve AYLIK FİYAT-SÜRE EĞRİLERİ
# ==============================================================================

def _sentetik_ptf():
    """Fiyat dosyası bulunamazsa kullanılan TEMSİLİ saatlik seri.
    Yıllık ortalaması PTF_SENTETIK_ORT'a kalibre edilir; gün içi/haftalık profil
    tipik bir gün-öncesi piyasasına aittir. SADECE YEDEK — gerçek veri yerine geçmez."""
    aylik_oran = {   # takvim ayı → yıllık ortalamaya göre mevsimsel katsayı
        1: 1.13, 2: 1.09, 3: 0.95, 4: 0.86, 5: 0.84, 6: 0.97,
        7: 1.12, 8: 1.03, 9: 0.99, 10: 0.97, 11: 1.01, 12: 1.06,
    }
    saat_profili = np.array([
        0.78, 0.74, 0.72, 0.71, 0.72, 0.76, 0.85, 0.95, 1.02, 1.05, 1.03, 1.00,
        0.98, 0.98, 0.99, 1.02, 1.10, 1.22, 1.30, 1.28, 1.18, 1.08, 0.96, 0.86])
    saat_profili = saat_profili / saat_profili.mean()
    tavan = 1.45 * PTF_SENTETIK_ORT

    idx = pd.date_range(PTF_SERI_BASI, periods=365 * 24, freq="h")
    rng = np.random.default_rng(20260805)
    gun_faktor   = np.repeat(np.exp(rng.normal(0.0, 0.13, len(idx) // 24)), 24)
    hafta_faktor = np.where(np.isin(idx.dayofweek, [5, 6]), 0.93, 1.028)
    taban = PTF_SENTETIK_ORT * np.array([aylik_oran[m] for m in idx.month])
    p = taban * saat_profili[idx.hour] * gun_faktor * hafta_faktor
    p = p * (1.0 + rng.normal(0.0, 0.05, len(idx)))
    s = pd.Series(np.clip(p, 0.0, tavan), index=idx)
    for m, oran in aylik_oran.items():              # aylık ortalamaları kalibre et
        msk = s.index.month == m
        if msk.any():
            hedef = PTF_SENTETIK_ORT * oran
            s[msk] = np.clip(s[msk] * hedef / s[msk].mean(), 0.0, tavan)
    return s


def ptf_oku(yol):
    """Saatlik fiyat dosyası (csv/xlsx) → saatlik pd.Series. Desteklenen biçimler:
       (a) EPİAŞ dışa aktarımı : Tarih + Saat + PTF sütunları
       (b) yıllık işletme tablosu : 0…8759 SAAT İNDEKSİ + fiyat sütunu
           (bu durumda takvim, PTF_SERI_BASI tarihinden itibaren kurulur)
       Dosya yoksa temsili seriye düşer."""
    if not (yol and os.path.exists(yol)):
        return _sentetik_ptf(), "SENTETİK (temsili seri)"

    if yol.lower().endswith((".xlsx", ".xls", ".xlsm")):
        df = pd.read_excel(yol)
    else:
        df = None
        for kw in ({"sep": ",", "decimal": "."}, {"sep": ";", "decimal": ","},
                   {"sep": None, "engine": "python"}):
            try:
                d = pd.read_csv(yol, **kw)
                if d.shape[1] >= 2:
                    df = d
                    break
            except Exception:
                continue
        if df is None:
            raise ValueError(f"Fiyat dosyası okunamadı: {yol}")

    kol = {str(c).strip().lower(): c for c in df.columns}

    def bul(*adaylar):
        for a in adaylar:                       # önce birebir eşleşme
            if a in kol:
                return kol[a]
        for a in adaylar:                       # sonra kısmi eşleşme
            for k, v in kol.items():
                if a in k:
                    return v
        return None

    # ---- fiyat sütunu --------------------------------------------------------
    c_fiyat = kol.get(str(PTF_SUTUNU).strip().lower()) if PTF_SUTUNU else None
    if c_fiyat is None:
        c_fiyat = bul("ptf", "price", "fiyat", "mcp")
    if c_fiyat is None:
        raise ValueError(f"Fiyat sütunu bulunamadı: {list(df.columns)}")

    v = df[c_fiyat]
    if v.dtype == object:
        v = (v.astype(str).str.replace(" ", "", regex=False)
                          .str.replace(",", ".", regex=False)
                          .str.replace(r"[^\d.\-]", "", regex=True))
    v = pd.to_numeric(v, errors="coerce")

    # ---- zaman ekseni --------------------------------------------------------
    c_tarih = bul("tarih", "date", "datetime", "zaman")
    saat_indeksi = True
    t = None
    if c_tarih is not None:
        ham = df[c_tarih]
        sayisal = pd.to_numeric(ham, errors="coerce")
        # 0…N-1 (veya 1…N) artan tamsayı dizisi → gerçek tarih değil, saat indeksi
        if not (sayisal.notna().all()
                and float(sayisal.max() - sayisal.min()) == len(df) - 1):
            t = pd.to_datetime(ham.astype(str).str.strip(), dayfirst=True,
                               errors="coerce")
            if t.notna().mean() > 0.9:
                saat_indeksi = False
                c_saat = bul("saat", "hour", "time")
                if c_saat is not None and c_saat != c_tarih:
                    sa = pd.to_numeric(
                        df[c_saat].astype(str).str.extract(r"(\d{1,2})")[0],
                        errors="coerce")
                    if sa.max() <= 24:            # gerçek saat sütunu mu?
                        t = t.dt.normalize() + pd.to_timedelta(sa.fillna(0), unit="h")

    if saat_indeksi:
        t = pd.date_range(PTF_SERI_BASI, periods=len(df), freq="h")

    s = pd.Series(np.asarray(v), index=pd.DatetimeIndex(t)).dropna().sort_index()
    s = s[s.index >= s.index.max() - pd.Timedelta(days=365)]
    if len(s) < 24 * 300:
        raise ValueError(f"Fiyat serisi çok kısa ({len(s)} saat)")
    etiket = os.path.basename(yol) + f"  [sütun: {c_fiyat}]"
    if saat_indeksi:
        etiket += f"  (saat indeksi → takvim {PTF_SERI_BASI} başlangıçlı)"
    return s, etiket


class FiyatSureEgrisi:
    """Aylık fiyat-süre eğrisi: 'en yüksek N saatin' PTF toplamı."""

    def __init__(self, ptf: pd.Series):
        self.kum, self.ort, self.saat, self.tepe = {}, {}, {}, {}
        for m in range(1, 13):
            p = np.sort(np.asarray(ptf[ptf.index.month == m].values, float))[::-1]
            if len(p) == 0:
                raise ValueError(f"{m}. ay için PTF verisi yok")
            self.kum[m]  = np.concatenate([[0.0], np.cumsum(p)])
            self.ort[m]  = float(p.mean())
            self.saat[m] = len(p)
            self.tepe[m] = float(p[:max(1, len(p) // 10)].mean())

    def toplam_fiyat(self, m, N):
        """En yüksek N saatin PTF toplamı [TL/MWh·h]; kesirli saat interpole."""
        c = self.kum[m]
        return np.interp(N, np.arange(len(c)), c, left=0.0, right=c[-1])


# ==============================================================================
# 6) DİNAMİK PROGRAMLAMA
# ==============================================================================

def dp_coz(akimlar, fse, ilerleme=True):
    """Geriye doğru (backward) deterministik DP.
       Durum : ay başı rezervuar hacmi
       Karar : (aylık ortalama türbin debisi, işletme modu)
       Amaç  : Σ gelir maksimizasyonu
    """
    T = akimlar.shape[0] * 12
    V_grid = np.linspace(V_MIN, V_MAKS, N_DURUM)          # [hm3]
    Q_grid = np.linspace(0.0, Q_TASARIM, N_KARAR)         # [m3/s]

    st_ay   = np.array([TAKVIM_AYI[t % 12] for t in range(T)])
    st_dt   = np.array([AY_GUN[a] * 86400.0 for a in st_ay])         # [s]
    st_akim = akimlar.reshape(-1)                                    # su yılı sırası

    aktif = _MOD_Q > 1e-6

    # Terminal değer: son ay sonunda hacim ≥ başlangıç hacmi (uç etkisi giderme)
    F_next = np.where(V_grid >= V_BASLANGIC - 1e-9, 0.0, -CEZA)

    pol_q = np.zeros((T, N_DURUM), dtype=np.int16)
    pol_m = np.zeros((T, N_DURUM), dtype=np.int16)
    idx_i = np.arange(N_DURUM)

    for t in range(T - 1, -1, -1):
        dt, ay = st_dt[t], st_ay[t]
        hrs = min(dt / 3600.0, fse.saat[ay])
        giren = st_akim[t] * dt / 1e6                                # [hm3]

        # Mecburi can suyu bırakması önceliklidir; minimum kota dayanılırsa
        # ancak mevcut su kadarı bırakılabilir
        can_hac = CAN_SUYU_AYLIK[t % 12] * dt / 1e6                  # [hm3]
        mevcut  = V_grid + giren - V_MIN                             # (durum,)
        can_act = np.minimum(can_hac, np.maximum(mevcut, 0.0))

        cikan = (Q_grid * dt / 1e6)[None, :] + can_act[:, None]      # [hm3]
        Vn = V_grid[:, None] + giren - cikan                         # (durum, karar)
        uygun = Vn >= V_MIN - 1e-9
        Vn = np.clip(Vn, V_MIN, V_MAKS)          # fazlası savaklanır (enerjisiz)
        kot_ort = kot(0.5 * (V_grid[:, None] + Vn))                  # [m]

        W = np.broadcast_to((Q_grid * dt)[None, :], (N_DURUM, N_KARAR))  # [m3]
        F_int = np.interp(Vn.ravel(), V_grid, F_next).reshape(Vn.shape)

        en_iyi     = np.full((N_DURUM, N_KARAR), -np.inf)
        en_iyi_mod = np.zeros((N_DURUM, N_KARAR), dtype=np.int16)

        for k in range(len(_MOD_Q)):
            if not aktif[k]:
                continue
            N_saat = W / (_MOD_Q[k] * 3600.0)                        # çalışma saati
            H_net = np.maximum(kot_ort - KOT_KUYRUK - _MOD_KAYIP[k], 0.0)
            P = G * _MOD_Q[k] * H_net * _MOD_ETA[k] / 1000.0         # [MW]
            if AMAC == "enerji":
                fayda = P * N_saat                                   # [MWh]
            else:
                fayda = P * fse.toplam_fiyat(ay, N_saat)             # [para birimi]
            fayda = np.where(N_saat <= hrs + 1e-9, fayda, -np.inf)
            daha_iyi = fayda > en_iyi
            en_iyi     = np.where(daha_iyi, fayda, en_iyi)
            en_iyi_mod = np.where(daha_iyi, k, en_iyi_mod)

        en_iyi[:, 0] = 0.0                       # Q=0 → duruş, gelir yok
        en_iyi_mod[:, 0] = -1

        toplam = np.where(uygun & np.isfinite(en_iyi), en_iyi + F_int, -CEZA)
        j = np.argmax(toplam, axis=1)
        F_next = toplam[idx_i, j]
        pol_q[t] = j
        pol_m[t] = en_iyi_mod[idx_i, j]

        if ilerleme and t % 48 == 0:
            print(f"    DP geriye çözüm ... aşama {t:4d}/{T}", end="\r")

    if ilerleme:
        print(" " * 60, end="\r")
    return V_grid, Q_grid, pol_q, pol_m, F_next


def ileri_simulasyon(V_grid, Q_grid, pol_q, pol_m, akimlar, fse):
    """Optimal politikayı başlangıç durumundan ileri doğru işlet."""
    T = akimlar.shape[0] * 12
    st_ay   = np.array([TAKVIM_AYI[t % 12] for t in range(T)])
    st_dt   = np.array([AY_GUN[a] * 86400.0 for a in st_ay])
    st_akim = akimlar.reshape(-1)

    V = V_BASLANGIC
    kayit = []
    for t in range(T):
        ay, dt = st_ay[t], st_dt[t]
        hrs = min(dt / 3600.0, fse.saat[ay])
        i = int(np.argmin(np.abs(V_grid - V)))            # en yakın durum düğümü
        j, k = int(pol_q[t, i]), int(pol_m[t, i])
        Qt = Q_grid[j]

        giren = st_akim[t] * dt / 1e6
        can_act = min(CAN_SUYU_AYLIK[t % 12] * dt / 1e6, max(V + giren - V_MIN, 0.0))
        Vn = V + giren - can_act - Qt * dt / 1e6
        savak_hac = max(Vn - V_MAKS, 0.0)                 # [hm3]
        Vn = min(max(Vn, V_MIN), V_MAKS)
        kot_ort = float(kot(0.5 * (V + Vn)))

        H_brut = kot_ort - KOT_KUYRUK
        if k >= 0 and Qt > 1e-9:
            Q_op   = float(_MOD_Q[k])
            kayip  = float(_MOD_KAYIP[k])
            N_saat = min(Qt * dt / (Q_op * 3600.0), hrs)
            H_net  = max(H_brut - kayip, 0.0)
            eta_t  = float(turbin_verimi(_MOD_YUK[k]))
            P      = G * Q_op * H_net * float(_MOD_ETA[k]) / 1000.0
            E      = P * N_saat                                       # [MWh]
            if AMAC == "enerji":
                # üretim aya yayılır → ayın ortalama fiyatından satılır
                gelir = E * fse.ort[ay]
            else:
                gelir = P * float(fse.toplam_fiyat(ay, N_saat))
            fiyat  = gelir / E if E > 1e-9 else 0.0
            mod_ad = _MOD_AD[k]
            eta_top = float(_MOD_ETA[k])
            unite  = int(_MOD_N[k])
        else:
            Q_op = N_saat = H_net = P = E = gelir = fiyat = 0.0
            kayip = eta_t = eta_top = 0.0
            unite = 0
            mod_ad = "Duruş"

        kayit.append(dict(
            SuYili=AKIM_YILLARI[t // 12], AyNo=t % 12 + 1, Ay=AY_ADLARI[t % 12],
            TakvimAy=ay, Gelen_m3s=st_akim[t], CanSuyu_m3s=can_act * 1e6 / dt,
            Turbin_m3s=Qt,
            Savak_m3s=savak_hac * 1e6 / dt, Kot_bas=float(kot(V)),
            Kot_son=float(kot(Vn)), Kot_ort=kot_ort, Hacim_hm3=Vn,
            Isletme_Modu=mod_ad, Calisan_Unite=unite,
            Q_isletme_m3s=Q_op, Calisma_saat=N_saat,
            Brut_Dusu_m=H_brut, Yuk_Kaybi_m=kayip, Net_Dusu_m=H_net,
            Eta_turbin=eta_t, Eta_toplam=eta_top,
            Guc_MW=P, Enerji_MWh=E, Gelir=gelir, Ort_Fiyat=fiyat))
        V = Vn
    return pd.DataFrame(kayit)


def senaryo_nehirtipi(akimlar, fse):
    """KIYAS SENARYOSU — depolamasız / optimize edilmemiş işletme:
    santral ay boyunca gelen akımla sürekli çalışır (Q = min(gelen, tasarım)),
    üretim o ayın ORTALAMA PTF'sinden satılır. Rezervuar maks. kotta tutulur."""
    st_akim = akimlar.reshape(-1)
    kayit = []
    for t in range(akimlar.shape[0] * 12):
        ay = TAKVIM_AYI[t % 12]
        dt = AY_GUN[ay] * 86400.0
        Q = min(max(st_akim[t] - CAN_SUYU_AYLIK[t % 12], 0.0), Q_TASARIM)
        if Q < UNITE_MIN_YUK * Q_UNITE:
            E = gelir = 0.0
        else:
            nu = 2 if Q > Q_UNITE else 1
            H_net = max(KOT_MAKS - KOT_KUYRUK - float(yuk_kaybi(Q)), 0.0)
            eta = float(turbin_verimi(Q / (nu * Q_UNITE))) * ETA_JENERATOR * ETA_TRAFO
            E = G * Q * H_net * eta / 1000.0 * dt / 3600.0
            gelir = E * fse.ort[ay]
        kayit.append(dict(SuYili=AKIM_YILLARI[t // 12], Enerji_MWh=E,
                          Gelir=gelir))
    return pd.DataFrame(kayit)


# ==============================================================================
# 7) RAPORLAMA
# ==============================================================================

def grafikler(df, fse, ptf, yol):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(3, 2, figsize=(16, 13))
    fig.suptitle("HEZİL BARAJI ve HES — Dinamik Programlama ile İşletme "
                 "Optimizasyonu", fontsize=14, fontweight="bold")

    a = ax[0, 0]
    a.plot(np.arange(len(df)) / 12.0 + AKIM_YILLARI[0], df["Kot_son"], lw=0.8,
           color="#1f6feb")
    a.axhline(KOT_MAKS, color="#d1242f", ls="--", lw=1, label=f"Maks {KOT_MAKS:.0f} m")
    a.axhline(KOT_MIN, color="#8250df", ls="--", lw=1, label=f"Min {KOT_MIN:.0f} m")
    a.set_title("Rezervuar su seviyesi (optimal işletme)")
    a.set_xlabel("Su yılı"); a.set_ylabel("Kot [m]")
    a.legend(fontsize=8); a.grid(alpha=.3)

    a = ax[0, 1]
    g = df.groupby("AyNo").agg(E=("Enerji_MWh", "mean"), S=("Calisma_saat", "mean"))
    a.bar(g.index, g["E"] / 1000.0, color="#2da44e", alpha=.85)
    a.set_xticks(range(1, 13)); a.set_xticklabels(AY_ADLARI, rotation=45, fontsize=8)
    a.set_ylabel("Ortalama aylık enerji [GWh]")
    a2 = a.twinx()
    a2.plot(g.index, g["S"], "o-", color="#bf3989")
    a2.set_ylabel("Ortalama çalışma saati [h/ay]", color="#bf3989")
    a.set_title("Uzun yıllar ortalama aylık üretim ve çalışma süresi")
    a.grid(alpha=.3)

    a = ax[1, 0]
    y = df.groupby("SuYili")["Enerji_MWh"].sum() / 1000.0
    a.bar(y.index, y.values, color="#0969da", alpha=.85)
    a.axhline(y.mean(), color="#d1242f", ls="--", label=f"Ort. {y.mean():.1f} GWh")
    a.set_title("Su yılı bazında toplam enerji üretimi")
    a.set_xlabel("Su yılı"); a.set_ylabel("Enerji [GWh]")
    a.legend(fontsize=8); a.grid(alpha=.3)

    a = ax[1, 1]
    ys = np.sort(y.values)[::-1]
    p = np.arange(1, len(ys) + 1) / (len(ys) + 1) * 100
    a.plot(p, ys, "o-", ms=3, color="#953800")
    a.axvline(95, color="#d1242f", ls="--", lw=1, label="%95 (firm)")
    a.set_title("Yıllık enerji süreklilik eğrisi")
    a.set_xlabel("Aşılma olasılığı [%]"); a.set_ylabel("Enerji [GWh/yıl]")
    a.legend(fontsize=8); a.grid(alpha=.3)

    a = ax[2, 0]
    for m in (1, 4, 7, 10):
        c = fse.kum[m]
        a.plot(np.arange(1, len(c)), np.diff(c), lw=1.2, label=f"{m}. ay")
    a.set_title("Aylık fiyat-süre eğrileri")
    a.set_xlabel("Saat sırası (pahalıdan ucuza)")
    a.set_ylabel(f"PTF [{PTF_PARA_BIRIMI}]")
    a.legend(fontsize=8); a.grid(alpha=.3)

    a = ax[2, 1]
    d = df[df["Enerji_MWh"] > 0]
    gm = {m: np.average(x["Ort_Fiyat"], weights=x["Enerji_MWh"])
          for m, x in d.groupby("TakvimAy")}
    aylar = sorted(gm)
    a.plot(aylar, [gm[m] for m in aylar], "s-", color="#bf3989",
           label="Yakalanan ort. fiyat (puant)")
    a.plot(aylar, [fse.ort[m] for m in aylar], "o--", color="#57606a",
           label="Ay ortalama PTF")
    a.set_title("Puant işletmenin fiyat kazanımı")
    a.set_xlabel("Takvim ayı"); a.set_ylabel(f"PTF [{PTF_PARA_BIRIMI}]")
    a.legend(fontsize=8); a.grid(alpha=.3)

    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(yol, dpi=130)
    plt.close(fig)


def main():
    kd = os.path.dirname(os.path.abspath(__file__))
    PB = PTF_PARA_BIRIMI.split("/")[0]

    print("=" * 78)
    print("HEZİL BARAJI ve HES — DİNAMİK PROGRAMLAMA İLE İŞLETME OPTİMİZASYONU")
    print("=" * 78)

    # -- [1] Rezervuar --------------------------------------------------------
    print("\n[1] REZERVUAR — KOT / ALAN / HACİM")
    for k in (KOT_MIN, 730.0, 740.0, KOT_MAKS):
        print(f"      Kot {k:7.2f} m  →  Hacim {float(hacim(k)):8.2f} hm³   "
              f"Alan {float(_f_kot2alan(k)):5.2f} km²")
    print(f"      Maksimum su seviyesi  : {KOT_MAKS:7.2f} m → {V_MAKS:8.2f} hm³")
    print(f"      Minimum su seviyesi   : {KOT_MIN:7.2f} m → {V_MIN:8.2f} hm³")
    print(f"      AKTİF (FAYDALI) HACİM : {V_AKTIF:8.2f} hm³")
    print(f"      Kuyruk suyu seviyesi  : {KOT_KUYRUK:7.2f} m")
    print(f"      Brüt düşü maks / min  : {KOT_MAKS-KOT_KUYRUK:.2f} / "
          f"{KOT_MIN-KOT_KUYRUK:.2f} m")

    # -- [2] Hidrolik ---------------------------------------------------------
    print("\n[2] BASINÇLI İLETİM SİSTEMİ ve YÜK KAYIPLARI")
    print(f"      Enerji tüneli : L={TUNEL_L:6.0f} m  D={TUNEL_D:.2f} m  "
          f"v={Q_TASARIM/(np.pi*TUNEL_D**2/4):.2f} m/s @Q_tasarım")
    print(f"      Cebri boru    : L={CEBRI_L:6.0f} m  D={CEBRI_D:.2f} m  "
          f"v={Q_TASARIM/(np.pi*CEBRI_D**2/4):.2f} m/s @Q_tasarım")
    print(f"      Kol (×{UNITE_SAYISI})      : L={KOL_L:6.0f} m  D={KOL_D:.2f} m  "
          f"v={Q_UNITE/(np.pi*KOL_D**2/4):.2f} m/s @Q_ünite")
    print(f"      {'Q':>8}{'Kayıp':>9}{'H_net@755':>12}{'H_net@720':>12}"
          f"{'Güç@755':>10}{'Güç@720':>10}")
    print(f"      {'m³/s':>8}{'m':>9}{'m':>12}{'m':>12}{'MW':>10}{'MW':>10}")
    for kk in range(len(_MOD_Q)):
        q = _MOD_Q[kk]
        hk = float(_MOD_KAYIP[kk])
        P1 = G*q*max(KOT_MAKS-KOT_KUYRUK-hk, 0)*_MOD_ETA[kk]/1000.0
        P2 = G*q*max(KOT_MIN - KOT_KUYRUK-hk, 0)*_MOD_ETA[kk]/1000.0
        print(f"      {q:8.1f}{hk:9.2f}{KOT_MAKS-KOT_KUYRUK-hk:12.2f}"
              f"{KOT_MIN-KOT_KUYRUK-hk:12.2f}{P1:10.2f}{P2:10.2f}   ({_MOD_AD[kk]})")
    print(f"      → KURULU GÜÇ ({UNITE_SAYISI} ünite tam yük, {KOT_MAKS:.0f} m) : "
          f"{P_KURULU:.2f} MW   (net düşü {H_NET_TASARIM:.2f} m)")

    print(f"\n      YÜK KAYBI DÖKÜMÜ  (Q = {Q_TASARIM:.1f} m³/s tasarım debisinde)")
    dk = yuk_kaybi_detay(Q_TASARIM)
    for ad in ["Giriş yapısı (yerel)", "Tünel — sürtünme", "Tünel — yerel",
               "Cebri boru — sürtünme", "Cebri boru — yerel",
               "Kol — sürtünme", "Kol — yerel"]:
        print(f"        {ad:<26}{dk[ad]:8.3f} m   "
              f"(%{dk[ad]/dk['TOPLAM KAYIP']*100:5.1f})")
    print(f"        {'-'*26}{'-'*8}")
    print(f"        {'SÜRTÜNME TOPLAMI':<26}{dk['SÜRTÜNME TOPLAMI']:8.3f} m   "
          f"(%{dk['SÜRTÜNME TOPLAMI']/dk['TOPLAM KAYIP']*100:5.1f})")
    print(f"        {'YEREL TOPLAMI':<26}{dk['YEREL TOPLAMI']:8.3f} m   "
          f"(%{dk['YEREL TOPLAMI']/dk['TOPLAM KAYIP']*100:5.1f})")
    print(f"        {'TOPLAM KAYIP':<26}{dk['TOPLAM KAYIP']:8.3f} m   "
          f"(brüt düşünün %{dk['TOPLAM KAYIP']/(KOT_MAKS-KOT_KUYRUK)*100:.1f}'i)")

    # -- [3] Hidroloji --------------------------------------------------------
    print(f"\n[3] HİDROLOJİ ({AKIM_YILLARI[0]}–{AKIM_YILLARI[-1]}, "
          f"{len(AKIM_YILLARI)} su yılı · {AKIM_DOSYASI})")
    print("                 " + "".join(f"{a:>9}" for a in AY_ADLARI))
    print("      Gelen akım " + "".join(f"{v:9.2f}" for v in AKIMLAR.mean(axis=0)))
    print("      Can suyu   " + "".join(f"{v:9.3f}" for v in CAN_SUYU_AYLIK))
    Qort = float(AKIMLAR.mean())
    hac_yil = Qort * 365.25 * 86400 / 1e6
    can_ort = float(np.average(CAN_SUYU_AYLIK,
                               weights=[AY_GUN[a] for a in TAKVIM_AYI]))
    print(f"      Uzun yıllar ortalama akım : {Qort:.2f} m³/s (~{hac_yil:.0f} hm³/yıl)")
    print(f"      Ortalama can suyu         : {can_ort:.3f} m³/s "
          f"(gelen akımın %{can_ort/Qort*100:.1f}'i, ~"
          f"{can_ort*365.25*86400/1e6:.0f} hm³/yıl)")
    print(f"      Aktif hacim / yıllık akış : {V_AKTIF/hac_yil*100:.1f} %  →  "
          f"{'mevsimlik' if V_AKTIF/hac_yil > 0.10 else 'kısmi (aylık/haftalık)'} "
          f"düzenleme")
    print(f"      Tasarım debisinin aşıldığı ay oranı : "
          f"{(AKIMLAR > Q_TASARIM).mean()*100:.1f} %")

    # -- [4] PTF --------------------------------------------------------------
    print("\n[4] SAATLİK PİYASA FİYATLARI (SON 1 YIL)")
    ptf, kaynak = ptf_oku(os.path.join(kd, PTF_DOSYASI))
    fse = FiyatSureEgrisi(ptf)
    print(f"      Kaynak : {kaynak}")
    print(f"      Dönem  : {ptf.index.min():%d.%m.%Y} – {ptf.index.max():%d.%m.%Y}"
          f"   ({len(ptf)} saat)")
    print(f"      Ortalama {ptf.mean():.2f} | medyan {ptf.median():.2f} | "
          f"min {ptf.min():.2f} | maks {ptf.max():.2f} {PTF_PARA_BIRIMI}")
    if kaynak.startswith("SENTETİK"):
        print(f"      !! '{PTF_DOSYASI}' bulunamadı; TEMSİLİ seri kullanılıyor.")
        print("      !! Gerçek saatlik fiyat dosyasını bu klasöre koyunuz.")
    print(f"      {'Ay':>5}{'Ortalama':>11}{'En pahalı %10':>15}{'Maks':>10}"
          f"{'Min':>9}{'Saat':>7}")
    for m in range(1, 13):
        c = fse.kum[m]
        print(f"      {m:5d}{fse.ort[m]:11.2f}{fse.tepe[m]:15.2f}"
              f"{c[1]:10.2f}{c[-1]-c[-2]:9.2f}{fse.saat[m]:7d}")

    # -- [5] DP ---------------------------------------------------------------
    print("\n[5] DİNAMİK PROGRAMLAMA")
    print(f"      Durum ızgarası  : {N_DURUM} hacim düğümü "
          f"({V_MIN:.2f} – {V_MAKS:.2f} hm³)")
    print(f"      Karar ızgarası  : {N_KARAR} debi düğümü × "
          f"{int((_MOD_Q > 0).sum())} işletme modu")
    print("      İşletme modları : " + ",  ".join(
        f"{ad}={q:.1f} m³/s (η={e:.3f})"
        for q, ad, e in zip(_MOD_Q, _MOD_AD, _MOD_ETA) if q > 0))
    print(f"      Aşama sayısı    : {AKIMLAR.shape[0]*12} ay "
          f"({AKIM_YILLARI[0]}–{AKIM_YILLARI[-1]})")
    V_grid, Q_grid, pol_q, pol_m, F0 = dp_coz(AKIMLAR, fse)
    i0 = int(np.argmin(np.abs(V_grid - V_BASLANGIC)))
    print(f"      Optimal değer fonksiyonu F*(V₀) : {F0[i0]/1e6:,.1f} milyon {PB}"
          f"  ({len(AKIM_YILLARI)} yıl toplamı)")

    df = ileri_simulasyon(V_grid, Q_grid, pol_q, pol_m, AKIMLAR, fse)

    # -- [6] Sonuçlar ---------------------------------------------------------
    yil = df.groupby("SuYili").agg(
        Enerji_GWh=("Enerji_MWh", lambda s: s.sum() / 1000.0),
        Gelir_Milyon=("Gelir", lambda s: s.sum() / 1e6),
        Calisma_h=("Calisma_saat", "sum"),
        Savak_m3s=("Savak_m3s", "mean"))
    E_ort  = yil["Enerji_GWh"].mean()
    E_firm = float(np.percentile(yil["Enerji_GWh"], 5))
    G_ort  = yil["Gelir_Milyon"].mean()
    CF = E_ort * 1000.0 / (P_KURULU * 8766.0)
    ort_fiyat = df["Gelir"].sum() / max(df["Enerji_MWh"].sum(), 1e-9)
    ptf_ort = float(ptf.mean())

    print("\n[6] SONUÇLAR — OPTİMAL (DP) İŞLETME")
    print(f"      Kurulu güç                       : {P_KURULU:10.2f} MW")
    print(f"      Ortalama yıllık enerji           : {E_ort:10.2f} GWh/yıl")
    print(f"      Firm enerji (%95 aşılma)         : {E_firm:10.2f} GWh/yıl")
    print(f"      En düşük / en yüksek yıl         : {yil['Enerji_GWh'].min():10.2f}"
          f" / {yil['Enerji_GWh'].max():.2f} GWh")
    print(f"      Kapasite faktörü                 : {CF*100:10.1f} %")
    print(f"      Eşdeğer tam yük saati            : {E_ort*1000/P_KURULU:10.0f} h/yıl")
    print(f"      Ortalama yıllık çalışma süresi   : {yil['Calisma_h'].mean():10.0f} h"
          f"  (%{yil['Calisma_h'].mean()/8766*100:.1f})")
    print(f"      Ortalama yıllık gelir            : {G_ort:10.2f} milyon {PB}")
    # Yakalanan fiyatın ayrıştırılması:
    #   yıllık ortalama → (mevsimsel etki) → ay ortalaması → (ay içi puant) → yakalanan
    E_toplam = df["Enerji_MWh"].sum()
    ay_ort_agirlikli = sum(df.loc[df["TakvimAy"] == m, "Enerji_MWh"].sum() * fse.ort[m]
                           for m in range(1, 13)) / max(E_toplam, 1e-9)
    print(f"      Yakalanan ortalama birim fiyat   : {ort_fiyat:10.2f} {PTF_PARA_BIRIMI}")
    print(f"      Yıllık ortalama piyasa fiyatı    : {ptf_ort:10.2f} {PTF_PARA_BIRIMI}")
    print(f"      Üretim ağırlıklı ay ort. fiyatı  : {ay_ort_agirlikli:10.2f} "
          f"{PTF_PARA_BIRIMI}")
    print(f"      → AY İÇİ PUANT PRİMİ             : "
          f"{(ort_fiyat/ay_ort_agirlikli-1)*100:+10.1f} %   (DP'nin kazandığı)")
    print(f"      → MEVSİMSEL ETKİ                 : "
          f"{(ay_ort_agirlikli/ptf_ort-1)*100:+10.1f} %   (hidroloji-fiyat uyumu)")
    print(f"      → NET (yıllık ortalamaya göre)   : "
          f"{(ort_fiyat/ptf_ort-1)*100:+10.1f} %")
    # ---- enerji ağırlıklı ortalama verimler ve kayıplar ---------------------
    u = df[df["Enerji_MWh"] > 0]
    w = u["Enerji_MWh"]
    eta_t_ort   = float(np.average(u["Eta_turbin"], weights=w))
    eta_top_ort = float(np.average(u["Eta_toplam"], weights=w))
    kayip_ort   = float(np.average(u["Yuk_Kaybi_m"], weights=w))
    hbrut_ort   = float(np.average(u["Brut_Dusu_m"], weights=w))
    hnet_ort    = float(np.average(u["Net_Dusu_m"], weights=w))

    # ---- TÜRBİNLENEN HACME ağırlıklı (RATED) değerler -----------------------
    # Türbin boyutlandırmasında esas alınan "rated" (anma) işletme noktası:
    # ağırlık = o ay türbinden geçen SU HACMİ (Q × ay süresi). Aylar farklı
    # uzunlukta olduğu için ham debi ortalaması yerine hacim ağırlığı kullanılır.
    w_hac = df["Turbin_m3s"] * df["AyNo"].map(
        {i + 1: AY_GUN[TAKVIM_AYI[i]] * 86400.0 for i in range(12)})
    if float(w_hac.sum()) > 0:
        rated_kot   = float(np.average(df["Kot_ort"], weights=w_hac))
        rated_brut  = float(np.average(df["Brut_Dusu_m"], weights=w_hac))
        rated_kayip = float(np.average(df["Yuk_Kaybi_m"], weights=w_hac))
        rated_net   = float(np.average(df["Net_Dusu_m"], weights=w_hac))
    else:
        rated_kot = rated_brut = rated_kayip = rated_net = 0.0
    # sistem verimi: üretilen enerji / türbinlenen suyun BRÜT düşüdeki potansiyeli
    su_hac = (df["Turbin_m3s"] * df["AyNo"].map(
        {i + 1: AY_GUN[TAKVIM_AYI[i]] * 86400.0 for i in range(12)}))
    E_teorik = (G * su_hac * df["Brut_Dusu_m"] / 3.6e6).sum()      # [MWh]
    sistem_verimi = df["Enerji_MWh"].sum() / max(E_teorik, 1e-9)

    print(f"      {'':-<52}")
    print(f"      Ağırlıklı ort. TÜRBİN verimi     : {eta_t_ort*100:10.2f} %"
          f"   (enerji ağırlıklı)")
    print(f"      Ağırlıklı ort. TOPLAM verim      : {eta_top_ort*100:10.2f} %"
          f"   (türbin×jeneratör×trafo)")
    print(f"      SİSTEM verimi (kayıplar dahil)   : {sistem_verimi*100:10.2f} %"
          f"   (üretim / brüt düşü potansiyeli)")
    print(f"      Ağırlıklı ort. brüt düşü         : {hbrut_ort:10.2f} m")
    print(f"      Ağırlıklı ort. YÜK KAYBI         : {kayip_ort:10.2f} m"
          f"   (brüt düşünün %{kayip_ort/hbrut_ort*100:.1f}'i)")
    print(f"      Ağırlıklı ort. net düşü          : {hnet_ort:10.2f} m")
    print(f"      {'':-<52}")
    print(f"      RATED REZERVUAR KOTU             : {rated_kot:10.2f} m"
          f"   (türbinlenen hacme ağırlıklı)")
    print(f"      RATED BRÜT DÜŞÜ                  : {rated_brut:10.2f} m")
    print(f"      RATED yük kaybı                  : {rated_kayip:10.2f} m")
    print(f"      RATED NET DÜŞÜ                   : {rated_net:10.2f} m"
          f"   (türbin anma düşüsü)")
    for nu in (1, UNITE_SAYISI):
        m = (df["Calisan_Unite"] == nu) & (w_hac > 0)
        if m.any() and float(w_hac[m].sum()) > 0:
            hn = float(np.average(df.loc[m, "Net_Dusu_m"], weights=w_hac[m]))
            pay = float(w_hac[m].sum() / w_hac.sum() * 100)
            print(f"        · {nu} ünite işletmesinde       : {hn:10.2f} m"
                  f"   (türbinlenen suyun %{pay:.0f}'i)")
    print(f"      {'':-<52}")

    tas = df["Savak_m3s"].mean()
    can = df["CanSuyu_m3s"].mean()
    tur = df["Turbin_m3s"].mean()
    print(f"      Ortalama türbinlenen debi        : {tur:10.2f} m³/s "
          f"(gelen akımın %{tur/Qort*100:.1f}'i)")
    print(f"      Ortalama bırakılan can suyu      : {can:10.2f} m³/s "
          f"(%{can/Qort*100:.1f})")
    print(f"      Ortalama savaklanan (boşa akan)  : {tas:10.2f} m³/s "
          f"(%{tas/Qort*100:.1f})")

    # -- [7] Kıyas ------------------------------------------------------------
    global AMAC
    print("\n[7] KIYAS SENARYOLARI")

    # (a) enerji maksimizasyonu — pik olmayan (bant) işletme
    _amac = AMAC
    AMAC = "enerji"
    try:
        Ve, Qe, pqe, pme, _ = dp_coz(AKIMLAR, fse, ilerleme=False)
        dfe = ileri_simulasyon(Ve, Qe, pqe, pme, AKIMLAR, fse)
    finally:
        AMAC = _amac
    ye = dfe.groupby("SuYili").agg(
        E=("Enerji_MWh", lambda s: s.sum() / 1000.0),
        G=("Gelir", lambda s: s.sum() / 1e6),
        S=("Calisma_saat", "sum"))
    Ee, Ge = ye["E"].mean(), ye["G"].mean()
    fe = dfe["Gelir"].sum() / max(dfe["Enerji_MWh"].sum(), 1e-9)

    # (b) depolamasız sürekli işletme
    nt = senaryo_nehirtipi(AKIMLAR, fse)
    nty = nt.groupby("SuYili").agg(E=("Enerji_MWh", lambda s: s.sum() / 1000.0),
                                   G=("Gelir", lambda s: s.sum() / 1e6))

    print(f"      {'Senaryo':<34}{'Enerji':>10}{'Gelir':>11}{'Fiyat':>10}"
          f"{'Çalışma':>10}")
    print(f"      {'':<34}{'GWh/yıl':>10}{'M '+PB:>11}{PTF_PARA_BIRIMI:>10}"
          f"{'h/yıl':>10}")
    print(f"      {'(a) DP — GELİR maks. (pik)':<34}{E_ort:10.2f}{G_ort:11.3f}"
          f"{ort_fiyat:10.2f}{yil['Calisma_h'].mean():10.0f}")
    print(f"      {'(b) DP — ENERJİ maks. (bant)':<34}{Ee:10.2f}{Ge:11.3f}"
          f"{fe:10.2f}{ye['S'].mean():10.0f}")
    print(f"      {'(c) Depolamasız sürekli':<34}{nty['E'].mean():10.2f}"
          f"{nty['G'].mean():11.3f}{'':>10}{'':>10}")
    print(f"      → (a) vs (b) : enerji {(E_ort/Ee-1)*100:+.1f} %, "
          f"gelir {(G_ort/Ge-1)*100:+.1f} %")
    print(f"      → (a) vs (c) : enerji {(E_ort/nty['E'].mean()-1)*100:+.1f} %, "
          f"gelir {(G_ort/nty['G'].mean()-1)*100:+.1f} %")
    print(f"      Yorum: pik işletme yük kaybı yüzünden "
          f"{Ee-E_ort:.2f} GWh/yıl enerji feda ediyor, buna karşılık birim fiyatı "
          f"{fe:.2f} → {ort_fiyat:.2f} {PTF_PARA_BIRIMI} yükseltiyor.")

    # -- [8] Ortalama aylık işletme programı ----------------------------------
    oa = df.groupby("AyNo").agg(
        Gelen_m3s=("Gelen_m3s", "mean"), CanSuyu_m3s=("CanSuyu_m3s", "mean"),
        Turbin_m3s=("Turbin_m3s", "mean"),
        Savak_m3s=("Savak_m3s", "mean"), Kot_son=("Kot_son", "mean"),
        Calisma_h=("Calisma_saat", "mean"), Net_Dusu_m=("Net_Dusu_m", "mean"),
        Guc_MW=("Guc_MW", "mean"),
        Enerji_GWh=("Enerji_MWh", lambda s: s.mean() / 1000.0),
        Gelir_Milyon=("Gelir", lambda s: s.mean() / 1e6),
        Fiyat=("Ort_Fiyat", "mean"))
    oa.insert(0, "Ay", AY_ADLARI)
    print("\n[8] UZUN YILLAR ORTALAMA AYLIK İŞLETME PROGRAMI")
    print(f"      {'Ay':>8}{'Gelen':>8}{'Can su':>8}{'Türbin':>8}{'Savak':>8}"
          f"{'Kot':>8}{'Çalışma':>9}{'H_net':>8}{'Güç':>8}{'Enerji':>9}"
          f"{'Gelir':>9}{'Fiyat':>9}")
    print(f"      {'':>8}{'m³/s':>8}{'m³/s':>8}{'m³/s':>8}{'m³/s':>8}{'m':>8}"
          f"{'h/ay':>9}{'m':>8}{'MW':>8}{'GWh':>9}{'M '+PB:>9}{PTF_PARA_BIRIMI:>9}")
    for _, r in oa.iterrows():
        print(f"      {r['Ay']:>8}{r['Gelen_m3s']:8.2f}{r['CanSuyu_m3s']:8.2f}"
              f"{r['Turbin_m3s']:8.2f}"
              f"{r['Savak_m3s']:8.2f}{r['Kot_son']:8.1f}{r['Calisma_h']:9.0f}"
              f"{r['Net_Dusu_m']:8.1f}{r['Guc_MW']:8.1f}{r['Enerji_GWh']:9.2f}"
              f"{r['Gelir_Milyon']:9.2f}{r['Fiyat']:9.2f}")
    print(f"      {'TOPLAM':>8}{'':>8}{'':>8}{'':>8}{'':>8}{'':>8}"
          f"{oa['Calisma_h'].sum():9.0f}{'':>8}{'':>8}"
          f"{oa['Enerji_GWh'].sum():9.2f}{oa['Gelir_Milyon'].sum():9.2f}")

    # -- [9] İşletme modu dağılımı --------------------------------------------
    print("\n[9] DP'NİN SEÇTİĞİ İŞLETME MODLARI")
    for ad, n in df["Isletme_Modu"].value_counts().items():
        e = df.loc[df["Isletme_Modu"] == ad, "Enerji_MWh"].sum() / 1000.0
        print(f"      {ad:>10} : {n:4d} ay (%{n/len(df)*100:4.1f})   "
              f"toplam {e:8.1f} GWh")

    # -- [10] Dosyalar --------------------------------------------------------
    ozet = pd.DataFrame([
        ("Maksimum su seviyesi", KOT_MAKS, "m"),
        ("Minimum su seviyesi", KOT_MIN, "m"),
        ("Kuyruk suyu seviyesi", KOT_KUYRUK, "m"),
        ("Aktif (faydalı) hacim", V_AKTIF, "hm³"),
        ("Tasarım debisi", Q_TASARIM, "m³/s"),
        ("Ünite sayısı", UNITE_SAYISI, "adet"),
        ("Tünel çapı / uzunluğu", TUNEL_D, f"m  (L={TUNEL_L:.0f} m)"),
        ("Tünel hızı @Q_tasarım", Q_TASARIM / (np.pi * TUNEL_D**2 / 4), "m/s"),
        ("Cebri boru çapı / uzunluğu", CEBRI_D, f"m  (L={CEBRI_L:.0f} m)"),
        ("Cebri boru hızı @Q_tasarım", Q_TASARIM / (np.pi * CEBRI_D**2 / 4), "m/s"),
        ("Sürtünme kaybı @Q_tasarım", dk["SÜRTÜNME TOPLAMI"], "m"),
        ("Yerel kayıp @Q_tasarım", dk["YEREL TOPLAMI"], "m"),
        ("Toplam yük kaybı @Q_tasarım", dk["TOPLAM KAYIP"], "m"),
        ("Net düşü @maks. kot", H_NET_TASARIM, "m"),
        ("Kurulu güç", P_KURULU, "MW"),
        ("Ağırlıklı ort. türbin verimi", eta_t_ort * 100, "%"),
        ("Ağırlıklı ort. toplam verim", eta_top_ort * 100, "%"),
        ("Sistem verimi (kayıplar dahil)", sistem_verimi * 100, "%"),
        ("Ağırlıklı ort. yük kaybı", kayip_ort, "m"),
        ("Ağırlıklı ort. net düşü", hnet_ort, "m"),
        ("RATED rezervuar kotu", rated_kot, "m"),
        ("RATED brüt düşü", rated_brut, "m"),
        ("RATED yük kaybı", rated_kayip, "m"),
        ("RATED net düşü", rated_net, "m"),
        ("Ortalama yıllık enerji", E_ort, "GWh/yıl"),
        ("Firm enerji (%95)", E_firm, "GWh/yıl"),
        ("Kapasite faktörü", CF * 100, "%"),
        ("Eşdeğer tam yük saati", E_ort * 1000 / P_KURULU, "h/yıl"),
        ("Ortalama yıllık gelir", G_ort, f"milyon {PB}"),
        ("Yakalanan ortalama fiyat", ort_fiyat, PTF_PARA_BIRIMI),
        ("Yıllık ortalama piyasa fiyatı", ptf_ort, PTF_PARA_BIRIMI),
        ("Ay içi puant primi", (ort_fiyat / ay_ort_agirlikli - 1) * 100, "%"),
        ("Mevsimsel etki", (ay_ort_agirlikli / ptf_ort - 1) * 100, "%"),
        ("Ortalama türbinlenen debi", tur, "m³/s"),
        ("Ortalama can suyu", can, "m³/s"),
        ("Ortalama savaklanan debi", tas, "m³/s"),
        ("Fiyat verisi", kaynak, ""),
    ], columns=["Büyüklük", "Değer", "Birim"])
    ozet["Değer"] = [round(v, 3) if isinstance(v, (int, float)) else v
                     for v in ozet["Değer"]]

    fiyat_tab = pd.DataFrame({
        "TakvimAy": range(1, 13),
        "Ortalama": [fse.ort[m] for m in range(1, 13)],
        "En_pahali_%10": [fse.tepe[m] for m in range(1, 13)],
        "Maks": [fse.kum[m][1] for m in range(1, 13)],
        "Saat": [fse.saat[m] for m in range(1, 13)]})

    # yük kaybı dökümü — tasarım debisi ve işletme modları için
    satirlar = []
    for kk in range(len(_MOD_Q)):
        q = float(_MOD_Q[kk])
        d = yuk_kaybi_detay(q)
        satirlar.append({"Debi_m3s": round(q, 1), "Mod": _MOD_AD[kk],
                         **{k: round(v, 3) for k, v in d.items()},
                         "Kayıp/brüt_%": round(d["TOPLAM KAYIP"] /
                                               (KOT_MAKS - KOT_KUYRUK) * 100, 2)})
    kayip_tab = pd.DataFrame(satirlar)

    px = os.path.join(kd, "hezil_dp_sonuclar.xlsx")
    with pd.ExcelWriter(px, engine="openpyxl") as xw:
        ozet.to_excel(xw, sheet_name="Özet", index=False)
        kayip_tab.to_excel(xw, sheet_name="Yük Kaybı Dökümü", index=False)
        oa.round(3).to_excel(xw, sheet_name="Ortalama Aylık")
        yil.round(3).to_excel(xw, sheet_name="Yıllık Özet")
        df.round(3).to_excel(xw, sheet_name="Aylık İşletme", index=False)
        fiyat_tab.round(2).to_excel(xw, sheet_name="Fiyat Özeti", index=False)
        for ws in xw.book.worksheets:                  # sütun genişlikleri
            for c in ws.columns:
                w = max(len(str(x.value)) for x in c if x.value is not None)
                ws.column_dimensions[c[0].column_letter].width = min(max(w + 2, 10), 40)
            ws.freeze_panes = "A2"

    p4 = os.path.join(kd, "hezil_dp_sonuclar.png")
    try:
        grafikler(df, fse, ptf, p4)
    except Exception as e:
        p4 = f"(grafik oluşturulamadı: {e})"

    print("\n[10] ÇIKTI DOSYALARI")
    for p in (px, p4):
        print(f"      {p}")
    print("=" * 78)
    return df, yil, oa


if __name__ == "__main__":
    main()
