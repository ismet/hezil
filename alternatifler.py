# -*- coding: utf-8 -*-
"""
================================================================================
HEZİL BARAJI ve HES — ALTERNATİF TARAMASI
(tünel çapı × tasarım debisi × minimum su kotu)
================================================================================

Her alternatif için optimzasyon.py'deki dinamik programlama modeli baştan
çözülür ve ortalama yıllık enerji / gelir hesaplanır.

TARAMA IZGARASI
---------------
  Tünel çapı        : 4.0 / 4.4 / 4.8 / 5.0 / 5.2 / 5.6 m  (uzunluk 4600 m sabit)
  Tünel hızı        : 2.8 – 3.8 m/s arası       → her çap için 6 tasarım debisi
                      Q = v · (π·D²/4)
  Cebri boru        : hız TAM 5.0 m/s olacak şekilde çapı hesaplanır
                      D_cebri = sqrt(4·Q / (π·5.0)) , uzunluk 300 m sabit
  Bifürkasyon kolu  : temel tasarımın oranı korunur (D_kol = 0.5128·D_cebri),
                      böylece kol hızı ~9.55 m/s'de sabit kalır
  Minimum su kotu   : 690 – 720 m arası 5 m aralıklarla (maks. kot 755 m sabit)

Toplam 6 × 6 × 7 = 252 alternatif.

EKONOMİ (yıllık gelir-gider)
---------------------------
  Tünel yatırımı    : kullanıcı maliyet tablosundan (ara çaplar interpole)
  EM yatırımı       : kurulu güç × EM birim maliyeti
  Yıllık gider      : (tünel + EM) × indirgeme oranı (0.12)
  NET FAYDA         : yıllık gelir − yıllık gider

ÇIKTI : hezil_alternatifler.xlsx   (Girdiler + Tüm Alternatifler + Ekonomi +
                                    En İyi 20 + Referans + pivot tabloları)
        hezil_alternatifler.png    (enerji/gelir taraması)
        hezil_ekonomi.png          (net fayda, regülasyon oranı, satış bedeli)
================================================================================
"""

import os
import sys
import time
import numpy as np
import pandas as pd

import optimzasyon as opt

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ==============================================================================
# TARAMA IZGARASI
# ==============================================================================
TUNEL_CAPLARI   = [4.0, 4.4, 4.8, 5.0, 5.2, 5.6, 6.0]   # [m]
TUNEL_HIZLARI   = [2.8, 3.0, 3.2, 3.4, 3.6, 3.8]        # [m/s]
CEBRI_HIZLARI   = [3.5, 4.0, 4.5, 5.0, 5.5, 6.0]        # [m/s] — TARANIR
KOL_CAP_ORANI   = 2.00 / 3.90                            # temel tasarımdaki oran
MIN_KOTLAR      = [690.0, 700.0, 710.0, 720.0, 730.0, 740.0]   # [m]

# Paralel çözüm: DP tek çekirdekte ~1.2 s/koşum sürer. Tarama 4 boyutlu
# olduğundan koşum sayısı hızla büyür; süreç havuzuyla bölünür.
# 0 veya 1 → sırayla çöz (hata ayıklama için).
PARALEL = max(1, (os.cpu_count() or 2) // 2)

TUNEL_UZUNLUK   = 4600.0
CEBRI_UZUNLUK   = 300.0
KOL_UZUNLUK     = 35.0

# ==============================================================================
# MALİYETLER ve YILLIK GELİR-GİDER HESABI
# ==============================================================================
# Tünel maliyeti (L = 4600 m için toplam yatırım) — kullanıcı tablosu
TUNEL_MALIYET_CAP = [4.0, 4.4, 5.0, 5.2, 5.6, 6.0]                              # [m]
TUNEL_MALIYET_EUR = [14_438_016.94, 16_368_509.76, 19_171_840.44,
                     19_901_877.26, 20_896_971.12, 22_359_759.10]
# Ara çaplar (ör. 4.8 m) bu noktalardan monoton eğriyle interpole edilir.

# ---- CEBRİ BORU ÇELİK MALİYETİ (et kalınlığı hesabıyla) ----------------------
CELIK_BIRIM_EUR_KG   = 1.20        # çelik birim maliyeti (imalat+montaj dahil)
CELIK_YOGUNLUK       = 7850.0      # [kg/m3]
CELIK_AKMA           = 355.0e6     # S355 / St52 akma dayanımı            [Pa]
GUVENLIK_KATSAYISI   = 1.5         # σ_izin = akma / güvenlik katsayısı
KAYNAK_VERIMI        = 0.90        # boyuna kaynak verimi (nokta radyografi)
KOROZYON_PAYI        = 0.002       # korozyon + imalat toleransı           [m]
SU_DARBESI_FAKTORU   = 1.35        # tasarım basıncı / statik basınç (denge bacalı)
IMALAT_FAZLASI       = 1.15        # bükümler, takviye halkaları, mesnetler,
                                   # genleşme parçaları, adam deliği vb. payı
SU_YOGUNLUK          = 1000.0      # [kg/m3]


def et_kalinligi(D, H_tasarim):
    """Boru et kalınlığı [m] — iç basınç + asgari imalat kalınlığı.
       t = p·D / (2·σ_izin·η_kaynak) + korozyon payı
       p = ρ·g·H_tasarım ,  H_tasarım = statik düşü × su darbesi faktörü
       Asgari kalınlık: USBR t_min = (D[mm] + 508) / 400  [mm]"""
    p = SU_YOGUNLUK * opt.G * H_tasarim
    sigma = CELIK_AKMA / GUVENLIK_KATSAYISI
    t_basinc = p * D / (2.0 * sigma * KAYNAK_VERIMI) + KOROZYON_PAYI
    t_min = (D * 1000.0 + 508.0) / 400.0 / 1000.0
    return max(t_basinc, t_min, 0.006)


def celik_agirlik(D, L, H_tasarim, adet=1):
    """Boru çelik ağırlığı [kg] (imalat fazlası dahil)."""
    t = et_kalinligi(D, H_tasarim)
    return (np.pi * (D + t) * t * L * CELIK_YOGUNLUK * adet
            * IMALAT_FAZLASI), t


def cebri_boru_maliyeti(D_c, D_k):
    """Cebri boru + bifürkasyon kolları çelik maliyeti [EUR] ve dökümü.
    Et kalınlığı, maksimum su seviyesindeki statik düşüye su darbesi faktörü
    uygulanarak SABİT (kademesiz) alınmıştır — bütün alternatifler için aynı
    esasla hesaplandığından karşılaştırma tutarlıdır; kademeli et kalınlığıyla
    gerçek ağırlık %15-25 daha düşük çıkar."""
    H_stat = opt.KOT_MAKS - opt.KOT_KUYRUK
    H_tas = H_stat * SU_DARBESI_FAKTORU
    m_c, t_c = celik_agirlik(D_c, CEBRI_UZUNLUK, H_tas, 1)
    m_k, t_k = celik_agirlik(D_k, KOL_UZUNLUK, H_tas, opt.UNITE_SAYISI)
    m_bt, D_kazi = boru_tuneli_maliyeti(D_c, t_c)
    return {
        "H_tasarım_m": round(H_tas, 1),
        "Cebri_et_mm": round(t_c * 1000, 1),
        "Kol_et_mm": round(t_k * 1000, 1),
        "Cebri_ağırlık_t": round(m_c / 1000, 1),
        "Kol_ağırlık_t": round(m_k / 1000, 1),
        "Çelik_ağırlık_t": round((m_c + m_k) / 1000, 1),
        "Çelik_maliyet_MEUR": round((m_c + m_k) * CELIK_BIRIM_EUR_KG / 1e6, 3),
        "Boru_tüneli_kazı_D_m": round(D_kazi, 2),
        "Boru_tüneli_MEUR": round(m_bt / 1e6, 3),
        "Cebri_maliyet_MEUR": round(((m_c + m_k) * CELIK_BIRIM_EUR_KG + m_bt) / 1e6, 3),
    }

# Elektromekanik teçhizat birim maliyeti.
# NOT: "MW başına 140 Euro" ifadesi 140 EUR/kW (= 140.000 EUR/MW) olarak
# yorumlanmıştır. Harfiyen 140 EUR/MW alınsaydı 114 MW'lık santralin EM bedeli
# 16.000 EUR, yani tünel maliyetinin binde biri olurdu ve karara hiç etki etmezdi.
# Aksini istiyorsanız aşağıdaki değeri 0.140 yapın.
EM_BIRIM_EUR_KW = 140.0                              # [EUR/kW]

# Santral binası + şalt sahası + inşaat işleri
SANTRAL_SALT_EUR_KW = 75.0                           # [EUR/kW]

INDIRGEME_ORANI = 0.12    # yatırımı yıllık SABİT GİDERE indirgeme oranı
                          # (sermaye geri kazanım faktörü)
OM_ORANI        = 0.00    # yatırıma oranla ek yıllık sabit gider

# ---- GELİRDEN YAPILAN KESİNTİ ------------------------------------------------
# Brüt satış gelirinden düşülen oran: piyasa işlem ve dengesizlik bedelleri,
# iletim/dağıtım, işletme-bakım, sigorta, lisans ve benzeri kalemler.
#     NET GELİR       = brüt gelir × (1 − GELIR_KESINTI_ORANI)
#     NİHAİ NET FAYDA = net gelir − yıllık sabit gider
# NOT: Oran bütün aylarda ve bütün senaryolarda aynı olduğundan DP'nin İŞLETME
# POLİTİKASINI DEĞİŞTİRMEZ (gelir düzgün ölçeklenir, argmax aynı kalır);
# yalnızca ekonomik değerlendirmeyi ve dolayısıyla optimal KONFİGÜRASYONU etkiler.
GELIR_KESINTI_ORANI = 0.09


def net_gelir(brut_MEUR):
    """Brüt gelirden kesinti düşülmüş net gelir [M EUR/yıl]."""
    return brut_MEUR * (1.0 - GELIR_KESINTI_ORANI)

# ---- YEKDEM GELİR AKIŞI ------------------------------------------------------
# İlk 5 yıl 85 EUR/MWh, sonraki 5 yıl 75 EUR/MWh sabit alım garantisi;
# kalan 40 yıl serbest piyasada PİK (puant) işletme geliri.
# SABİT tarife dönemlerinde fiyat farkı olmadığı için puant yapmanın faydası
# yoktur → o yıllarda BANT (enerji maks.) işletme geçerlidir. Serbest piyasa
# döneminde ise PİK işletme geliri kullanılır.
YEKDEM_KADEMELER = [(5, 85.0), (5, 75.0)]   # (yıl sayısı, EUR/MWh)
PROJE_OMRU       = 50                        # toplam ekonomik ömür [yıl]
ISKONTO          = INDIRGEME_ORANI           # nakit akışı iskonto oranı

# ---- DÖRT İŞLETME / GELİR MODELİ --------------------------------------------
# S1 PİK·PİYASA   : ömür boyunca puant işletme, saatlik piyasa fiyatı
# S2 BANT·PİYASA  : ömür boyunca enerji maksimizasyonu, o ayın ortalama fiyatı
# S3 SABİT        : ömür boyunca sabit birim fayda, enerji maksimizasyonu
# S4 YEKDEM       : 5 yıl 77,5 + 5 yıl 70 EUR/MWh (bant) → 40 yıl piyasa (pik)
SABIT_BIRIM_FAYDA = 88.0                     # S3 birim enerji faydası [EUR/MWh]

SENARYOLAR = [
    ("S1", "PİK · piyasa",      "#0969da"),
    ("S2", "BANT · piyasa",     "#bf3989"),
    ("S3", f"SABİT {SABIT_BIRIM_FAYDA:.0f} €/MWh", "#2da44e"),
    ("S4", "YEKDEM",            "#953800"),
]


def _yekdem_katsayilar(iskonto=None, omur=None, kademeler=None):
    """YEKDEM gelir akışını YILLIK EŞDEĞER gelire indirgeyen katsayılar.

    Eşdeğer yıllık gelir = SGKF × Σ R_t/(1+i)^t   ,  SGKF = 1/Σ 1/(1+i)^t

    Döner: (bant_katsayıları [her kademe için], pik_katsayısı, SGKF)
    Bant kademeleri enerjiyle (GWh) çarpılır → M EUR; pik katsayısı ise
    piyasa geliriyle (M EUR/yıl) çarpılır."""
    i = ISKONTO if iskonto is None else iskonto
    n = PROJE_OMRU if omur is None else omur
    kd = YEKDEM_KADEMELER if kademeler is None else kademeler

    def yillik_faktor(bas, bit):        # Σ_{t=bas..bit} 1/(1+i)^t
        return sum(1.0 / (1.0 + i) ** t for t in range(bas, bit + 1))

    sgkf = 1.0 / yillik_faktor(1, n)
    kats, t0 = [], 1
    for yil, fiyat in kd:
        f = yillik_faktor(t0, t0 + yil - 1)
        # enerji [GWh] × fiyat [EUR/MWh] / 1000 = M EUR
        kats.append((fiyat, f, fiyat / 1000.0 * f * sgkf))
        t0 += yil
    pik_kat = yillik_faktor(t0, n) * sgkf
    return kats, pik_kat, sgkf


def yekdem_gelir(E_bant_GWh, gelir_pik_MEUR):
    """YEKDEM senaryosunun YILLIK EŞDEĞER geliri [M EUR/yıl]."""
    kats, pik_kat, _ = _yekdem_katsayilar()
    return sum(k[2] * E_bant_GWh for k in kats) + pik_kat * gelir_pik_MEUR


def senaryo_gelirleri(yk):
    """Dört senaryonun yıllık (eşdeğer) geliri ve net faydası.
    yk : aynı konfigürasyonun PİK ve BANT çözümleri eşleştirilmiş tablo.
    Yıllık gider bütün senaryolarda aynıdır (konfigürasyon aynı → yatırım aynı)."""
    d = yk.copy()
    # önce BRÜT gelirler
    d["S1_brut_MEUR"] = d["Brüt_gelir_MEUR/yıl"].round(3)
    d["S2_brut_MEUR"] = d["Brüt_gelir_MEUR/yıl_bant"].round(3)
    d["S3_brut_MEUR"] = (d["Enerji_GWh/yıl_bant"] * SABIT_BIRIM_FAYDA
                         / 1000.0).round(3)
    d["S4_brut_MEUR"] = [round(yekdem_gelir(eb, gp), 3) for eb, gp
                         in zip(d["Enerji_GWh/yıl_bant"],
                                d["Brüt_gelir_MEUR/yıl"])]
    for s, _, _ in SENARYOLAR:
        # brüt → kesinti → net gelir → sabit gider → nihai net fayda
        d[f"{s}_gelir_MEUR"] = net_gelir(d[f"{s}_brut_MEUR"]).round(3)
        d[f"{s}_kesinti_MEUR"] = (d[f"{s}_brut_MEUR"]
                                  - d[f"{s}_gelir_MEUR"]).round(3)
        d[f"{s}_net_MEUR"] = (d[f"{s}_gelir_MEUR"]
                              - d["Yıllık_gider_MEUR"]).round(3)
        d[f"{s}_F/M"] = (d[f"{s}_gelir_MEUR"] / d["Yıllık_gider_MEUR"]).round(3)
        # senaryonun geçerli olduğu işletme biçimindeki enerji
        d[f"{s}_enerji_GWh"] = (d["Enerji_GWh/yıl"] if s in ("S1",)
                                else d["Enerji_GWh/yıl_bant"])
    # S4'te enerji karma: ilk 10 yıl bant, sonrası pik → PD ağırlıklı
    _, pik_kat, _ = _yekdem_katsayilar()
    d["S4_enerji_GWh"] = ((1 - pik_kat) * d["Enerji_GWh/yıl_bant"]
                          + pik_kat * d["Enerji_GWh/yıl"]).round(2)
    d["S3_enerji_GWh"] = d["Enerji_GWh/yıl_bant"].round(2)
    d["S2_enerji_GWh"] = d["Enerji_GWh/yıl_bant"].round(2)
    d["S1_enerji_GWh"] = d["Enerji_GWh/yıl"].round(2)
    return d


_f_tunel_maliyet = opt._monoton_kubik(TUNEL_MALIYET_CAP, TUNEL_MALIYET_EUR)
_TM_EGIM_ALT = ((TUNEL_MALIYET_EUR[1] - TUNEL_MALIYET_EUR[0])
                / (TUNEL_MALIYET_CAP[1] - TUNEL_MALIYET_CAP[0]))
_TM_EGIM_UST = ((TUNEL_MALIYET_EUR[-1] - TUNEL_MALIYET_EUR[-2])
                / (TUNEL_MALIYET_CAP[-1] - TUNEL_MALIYET_CAP[-2]))


def tunel_maliyeti(D):
    """Tünel yatırım maliyeti [EUR], L = 4600 m için — verilen tablodan.
    Tablo aralığı (4.0–6.0 m) dışında uç eğimlerle DOĞRUSAL uzatılır; bu,
    monoton kübik eğrinin dışarıda savrulmasını önler."""
    D = float(D)
    if D < TUNEL_MALIYET_CAP[0]:
        return TUNEL_MALIYET_EUR[0] + (D - TUNEL_MALIYET_CAP[0]) * _TM_EGIM_ALT
    if D > TUNEL_MALIYET_CAP[-1]:
        return TUNEL_MALIYET_EUR[-1] + (D - TUNEL_MALIYET_CAP[-1]) * _TM_EGIM_UST
    return float(np.atleast_1d(_f_tunel_maliyet(D))[0])


def tunel_birim_maliyet(D):
    """Metre başına tünel maliyeti [EUR/m]."""
    return tunel_maliyeti(D) / TUNEL_UZUNLUK


# ---- CEBRİ BORU TÜNELİ -------------------------------------------------------
# Cebri boru açıkta değil, kendi tüneli içinde döşenir. Bu 300 m'lik tünelin
# kazı çapı, borunun DIŞ çapı + montaj/dolgu payı kadardır ve maliyeti aynı
# tünel maliyet eğrisinden (metre başına) hesaplanır.
BORU_TUNEL_UZUNLUK = 300.0     # cebri borunun tünel içindeki uzunluğu     [m]
BORU_TUNEL_PAYI    = 1.20      # kazı çapı − boru dış çapı (montaj + dolgu) [m]


def boru_tuneli_maliyeti(D_c, t_c):
    """Cebri boruyu barındıran tünelin maliyeti [EUR] ve kazı çapı [m]."""
    D_kazi = D_c + 2.0 * t_c + BORU_TUNEL_PAYI
    return tunel_birim_maliyet(D_kazi) * BORU_TUNEL_UZUNLUK, D_kazi


def ekonomi(D_t, P_kurulu_MW, brut_gelir_MEUR, cebri_MEUR=0.0):
    """Yıllık gelir-gider hesabı.
       brüt gelir → (−%kesinti) → net gelir → (−sabit gider) → nihai net fayda"""
    m_tunel   = tunel_maliyeti(D_t)
    m_em      = P_kurulu_MW * 1000.0 * EM_BIRIM_EUR_KW
    m_santral = P_kurulu_MW * 1000.0 * SANTRAL_SALT_EUR_KW
    m_cebri   = cebri_MEUR * 1e6
    yatirim = m_tunel + m_em + m_santral + m_cebri
    yillik_gider = yatirim * (INDIRGEME_ORANI + OM_ORANI) / 1e6   # [M EUR]
    ng = net_gelir(brut_gelir_MEUR)
    return {
        "Tünel_maliyeti_MEUR": round(m_tunel / 1e6, 3),
        "Cebri_maliyet_MEUR": round(m_cebri / 1e6, 3),
        "EM_maliyeti_MEUR": round(m_em / 1e6, 3),
        "Santral_şalt_MEUR": round(m_santral / 1e6, 3),
        "Yatırım_MEUR": round(yatirim / 1e6, 3),
        "Brüt_gelir_MEUR/yıl": round(brut_gelir_MEUR, 3),
        "Gelir_kesintisi_MEUR": round(brut_gelir_MEUR - ng, 3),
        "Net_gelir_MEUR/yıl": round(ng, 3),
        "Gelir_MEUR/yıl": round(ng, 3),      # takma ad: NET gelir
        "Yıllık_gider_MEUR": round(yillik_gider, 3),
        "Net_fayda_MEUR/yıl": round(ng - yillik_gider, 3),
        "Fayda_masraf_oranı": round(ng / yillik_gider, 3),
    }


def alternatif_coz(D_t, v_t, v_c, kot_min, fse, ptf_ort, amac="gelir"):
    """Tek bir alternatifi kur, DP ile çöz, özet göstergeleri döndür.
    D_t, v_t : tünel çapı ve hızı  → tasarım debisi Q = v_t · A_t
    v_c      : cebri boru hızı     → cebri boru çapı D_c = √(4Q/(π·v_c))
    amac = "gelir"  → pik (puant) işletme, geliri maksimize eder
           "enerji" → bant işletme, üretilen enerjiyi maksimize eder"""
    A_t = np.pi * D_t**2 / 4.0
    Q   = round(v_t * A_t, 1)                       # tasarım debisi [m3/s]
    D_c = np.sqrt(4.0 * Q / (np.pi * v_c))          # cebri boru çapı [m]
    D_k = KOL_CAP_ORANI * D_c                       # kol çapı [m]

    # --- girdileri ata ve türetilmiş büyüklükleri tazele ---------------------
    opt.TUNEL_D, opt.TUNEL_L = D_t, TUNEL_UZUNLUK
    opt.CEBRI_D, opt.CEBRI_L = D_c, CEBRI_UZUNLUK
    opt.KOL_D, opt.KOL_L = D_k, KOL_UZUNLUK
    opt.Q_TASARIM = Q
    opt.KOT_MIN = kot_min
    opt.BASLANGIC_KOTU = kot_min                    # su yılı başında boş rezervuar
    opt.AMAC = amac
    opt.yeniden_kur()

    # --- çöz ------------------------------------------------------------------
    V_grid, Q_grid, pol_q, pol_m, F0 = opt.dp_coz(opt.AKIMLAR, fse, ilerleme=False)
    df = opt.ileri_simulasyon(V_grid, Q_grid, pol_q, pol_m, opt.AKIMLAR, fse)

    yil = df.groupby("SuYili").agg(
        E=("Enerji_MWh", lambda s: s.sum() / 1000.0),
        Gelir=("Gelir", lambda s: s.sum() / 1e6),
        Saat=("Calisma_saat", "sum"))
    E_ort = float(yil["E"].mean())
    E_top = float(df["Enerji_MWh"].sum())
    ort_fiyat = df["Gelir"].sum() / max(E_top, 1e-9)
    ay_ort = sum(df.loc[df["TakvimAy"] == m, "Enerji_MWh"].sum() * fse.ort[m]
                 for m in range(1, 13)) / max(E_top, 1e-9)

    # --- yük kaybı dökümü (tasarım debisinde) --------------------------------
    dk = opt.yuk_kaybi_detay(Q)
    kayip = dk["TOPLAM KAYIP"]

    # --- enerji ağırlıklı ortalama verimler / kayıplar ------------------------
    u = df[df["Enerji_MWh"] > 0]
    if len(u):
        w = u["Enerji_MWh"]
        eta_t   = float(np.average(u["Eta_turbin"], weights=w))
        eta_top = float(np.average(u["Eta_toplam"], weights=w))
        kayip_w = float(np.average(u["Yuk_Kaybi_m"], weights=w))
        hbrut_w = float(np.average(u["Brut_Dusu_m"], weights=w))
        hnet_w  = float(np.average(u["Net_Dusu_m"], weights=w))
    else:
        eta_t = eta_top = kayip_w = hbrut_w = hnet_w = 0.0
    su_hac = df["Turbin_m3s"] * df["AyNo"].map(
        {i + 1: opt.AY_GUN[opt.TAKVIM_AYI[i]] * 86400.0 for i in range(12)})
    E_teorik = (opt.G * su_hac * df["Brut_Dusu_m"] / 3.6e6).sum()
    sistem_verimi = df["Enerji_MWh"].sum() / max(E_teorik, 1e-9)

    # --- TÜRBİNLENEN HACME ağırlıklı (RATED / anma) işletme noktası ----------
    if float(su_hac.sum()) > 0:
        rated_kot   = float(np.average(df["Kot_ort"], weights=su_hac))
        rated_brut  = float(np.average(df["Brut_Dusu_m"], weights=su_hac))
        rated_kayip = float(np.average(df["Yuk_Kaybi_m"], weights=su_hac))
        rated_net   = float(np.average(df["Net_Dusu_m"], weights=su_hac))
    else:
        rated_kot = rated_brut = rated_kayip = rated_net = 0.0

    # ünite sayısına göre anma net düşüsü: tek ünitede toplam debi yarıya
    # indiği için yük kaybı ~1/4'e düşer, net düşü belirgin biçimde yükselir
    def _rated_unite(nu):
        m = (df["Calisan_Unite"] == nu) & (su_hac > 0)
        if not m.any() or float(su_hac[m].sum()) <= 0:
            return 0.0, 0.0
        return (float(np.average(df.loc[m, "Net_Dusu_m"], weights=su_hac[m])),
                float(su_hac[m].sum() / su_hac.sum() * 100))
    rated_net_1u, pay_1u = _rated_unite(1)
    rated_net_2u, pay_2u = _rated_unite(opt.UNITE_SAYISI)

    gelir_MEUR = float(yil["Gelir"].mean())

    # regülasyon göstergeleri
    Q_gelen = float(opt.AKIMLAR.mean())
    Q_turbin = float(df["Turbin_m3s"].mean())
    yillik_akis_hm3 = Q_gelen * 365.25 * 86400 / 1e6

    cb = cebri_boru_maliyeti(D_c, D_k)
    ek = ekonomi(D_t, opt.P_KURULU, gelir_MEUR, cb["Cebri_maliyet_MEUR"])
    birim_maliyet = ek["Yıllık_gider_MEUR"] * 1e6 / max(E_ort * 1000.0, 1e-9)

    return {
        "Amaç": "PİK (gelir maks.)" if amac == "gelir" else "BANT (enerji maks.)",
        "Tünel_D_m": D_t,
        "Tünel_hızı_m/s": round(Q / A_t, 3),
        "Q_tasarım_m3/s": Q,
        "Cebri_D_m": round(D_c, 3),
        "Cebri_hızı_m/s": round(Q / (np.pi * D_c**2 / 4.0), 3),
        "Kol_D_m": round(D_k, 3),
        "Min_kot_m": kot_min,
        "Aktif_hacim_hm3": round(opt.V_AKTIF, 2),
        # --- yük kaybı dökümü @ tasarım debisi ---
        "Giriş_kaybı_m": round(dk["Giriş yapısı (yerel)"], 3),
        "Tünel_sürtünme_m": round(dk["Tünel — sürtünme"], 3),
        "Tünel_yerel_m": round(dk["Tünel — yerel"], 3),
        "Cebri_sürtünme_m": round(dk["Cebri boru — sürtünme"], 3),
        "Cebri_yerel_m": round(dk["Cebri boru — yerel"], 3),
        "Kol_sürtünme_m": round(dk["Kol — sürtünme"], 3),
        "Kol_yerel_m": round(dk["Kol — yerel"], 3),
        "SÜRTÜNME_toplam_m": round(dk["SÜRTÜNME TOPLAMI"], 3),
        "YEREL_toplam_m": round(dk["YEREL TOPLAMI"], 3),
        "Yük_kaybı_m": round(kayip, 3),
        "Sürtünme_payı_%": round(dk["SÜRTÜNME TOPLAMI"] / kayip * 100, 1),
        "Yerel_payı_%": round(dk["YEREL TOPLAMI"] / kayip * 100, 1),
        "Kayıp/brüt_düşü_%": round(kayip / (opt.KOT_MAKS - opt.KOT_KUYRUK) * 100, 2),
        "Net_düşü_maks_m": round(opt.H_NET_TASARIM, 2),
        "Net_düşü_min_m": round(kot_min - opt.KOT_KUYRUK - kayip, 2),
        # --- işletmede gerçekleşen (enerji ağırlıklı) ---
        "Ağırlıklı_türbin_verimi_%": round(eta_t * 100, 2),
        "Ağırlıklı_toplam_verim_%": round(eta_top * 100, 2),
        "Sistem_verimi_%": round(sistem_verimi * 100, 2),
        "Ağırlıklı_brüt_düşü_m": round(hbrut_w, 2),
        "Ağırlıklı_yük_kaybı_m": round(kayip_w, 3),
        "Ağırlıklı_net_düşü_m": round(hnet_w, 2),
        # --- rated (türbinlenen hacme ağırlıklı) işletme noktası ---
        "Rated_rezervuar_kotu_m": round(rated_kot, 2),
        "Rated_brüt_düşü_m": round(rated_brut, 2),
        "Rated_yük_kaybı_m": round(rated_kayip, 3),
        "Rated_net_düşü_m": round(rated_net, 2),
        "Rated_net_düşü_1Ü_m": round(rated_net_1u, 2),
        "Rated_net_düşü_2Ü_m": round(rated_net_2u, 2),
        "Tek_ünite_su_payı_%": round(pay_1u, 1),
        # --- cebri boru çeliği ---
        **cb,
        "Kurulu_güç_MW": round(opt.P_KURULU, 2),
        "Enerji_GWh/yıl": round(E_ort, 2),
        "Firm_enerji_GWh": round(float(np.percentile(yil["E"], 5)), 2),
        "Kapasite_faktörü_%": round(E_ort * 1000 / (opt.P_KURULU * 8766.0) * 100, 1),
        "Tam_yük_saati_h": round(E_ort * 1000 / opt.P_KURULU),
        "Çalışma_saati_h/yıl": round(float(yil["Saat"].mean())),
        "Brüt_gelir_MEUR/yıl": round(gelir_MEUR, 3),
        "Yakalanan_fiyat_EUR/MWh": round(ort_fiyat, 2),
        "Ay_içi_puant_primi_%": round((ort_fiyat / ay_ort - 1) * 100, 1),
        "Mevsimsel_etki_%": round((ay_ort / ptf_ort - 1) * 100, 1),
        "Türbinlenen_m3/s": round(Q_turbin, 2),
        "Savaklanan_m3/s": round(float(df["Savak_m3s"].mean()), 2),
        "Savaklanan_%": round(float(df["Savak_m3s"].mean()) / Q_gelen * 100, 1),
        # --- regülasyon göstergeleri ---
        "Regülasyon_oranı_%": round(Q_turbin / Q_gelen * 100, 1),   # türbinlenen/gelen
        "Depolama_oranı_%": round(opt.V_AKTIF / yillik_akis_hm3 * 100, 2),
        # --- ekonomi ---
        **ek,
        "Birim_enerji_maliyeti_EUR/MWh": round(birim_maliyet, 2),
    }


RENK = {4.0: "#0969da", 4.4: "#2da44e", 4.8: "#bf3989",
        5.0: "#8250df", 5.2: "#953800", 5.6: "#cf222e", 6.0: "#1b7c83"}


def _eksen_sik(ax, *seriler, pay=0.10, ust_pay=None):
    """Y eksenini SIFIRDAN DEĞİL, verinin kendi aralığından başlatır — böylece
    eğrilerin kıvrımı (curvature) görünür kalır."""
    v = np.concatenate([np.asarray(s, float).ravel() for s in seriler])
    v = v[np.isfinite(v)]
    if v.size == 0:
        return
    lo, hi = float(v.min()), float(v.max())
    r = hi - lo if hi > lo else max(abs(hi), 1.0) * 0.1
    ax.set_ylim(lo - pay * r, hi + (pay if ust_pay is None else ust_pay) * r)


def ekonomi_grafikleri(t, ptf_ort, yol):
    """İstenen üç grafik: net fayda, regülasyon oranı, ortalama satış bedeli
    (+ seçeneklerin gelir/gider dökümü)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # her (tünel çapı, debi) seçeneği kendi EN İYİ cebri boru hızıyla temsil edilir
    s = t.loc[t.groupby(["Tünel_D_m", "Q_tasarım_m3/s"])
               ["Net_fayda_MEUR/yıl"].idxmax()].sort_values(
                   ["Tünel_D_m", "Q_tasarım_m3/s"])

    fig, ax = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle("HEZİL HES — SEÇENEKLERİN EKONOMİK DEĞERLENDİRMESİ\n"
                 f"yıllık gelir-gider · indirgeme oranı {INDIRGEME_ORANI:.2f} · "
                 f"EM {EM_BIRIM_EUR_KW:.0f} EUR/kW · tünel maliyeti verilen tablodan",
                 fontsize=13, fontweight="bold")

    # (1) NET FAYDA -----------------------------------------------------------
    a = ax[0, 0]
    for D, g in s.groupby("Tünel_D_m"):
        a.plot(g["Q_tasarım_m3/s"], g["Net_fayda_MEUR/yıl"], "o-",
               color=RENK[D], label=f"D={D:.1f} m")
    b = s.loc[s["Net_fayda_MEUR/yıl"].idxmax()]
    a.scatter([b["Q_tasarım_m3/s"]], [b["Net_fayda_MEUR/yıl"]], s=190,
              facecolors="none", edgecolors="#d1242f", linewidths=2, zorder=5)
    a.annotate(f"  en yüksek net fayda\n  D={b['Tünel_D_m']:.1f} m, "
               f"Q={b['Q_tasarım_m3/s']:.1f} m³/s\n"
               f"  {b['Net_fayda_MEUR/yıl']:.3f} M EUR/yıl",
               (b["Q_tasarım_m3/s"], b["Net_fayda_MEUR/yıl"]),
               fontsize=8, va="top")
    a.set_title("NET FAYDA  =  yıllık gelir − yıllık gider")
    a.set_xlabel("Tasarım debisi [m³/s]")
    a.set_ylabel("Net fayda [milyon EUR/yıl]")
    _eksen_sik(a, s["Net_fayda_MEUR/yıl"])
    a.legend(fontsize=8); a.grid(alpha=.3)

    # (2) REGÜLASYON ORANI ----------------------------------------------------
    a = ax[1, 0]
    for D, g in s.groupby("Tünel_D_m"):
        a.plot(g["Q_tasarım_m3/s"], g["Regülasyon_oranı_%"], "o-",
               color=RENK[D], label=f"D={D:.1f} m")
    a.set_title("REGÜLASYON ORANI  =  türbinlenen su / gelen su\n"
                "(kalanı: can suyu + savaklanan)")
    a.set_xlabel("Tasarım debisi [m³/s]")
    a.set_ylabel("Regülasyon oranı [%]")
    can_pay = float(np.average(opt.CAN_SUYU_AYLIK,
                               weights=[opt.AY_GUN[m] for m in opt.TAKVIM_AYI])
                    / opt.AKIMLAR.mean() * 100)
    a.axhline(100 - can_pay, color="#d1242f", ls="--", lw=1)
    _eksen_sik(a, s["Regülasyon_oranı_%"], [100 - can_pay], ust_pay=0.16)
    a.text(s["Q_tasarım_m3/s"].min(), 100 - can_pay + 0.3,
           f"can suyu düşüldükten sonraki teorik üst sınır "
           f"(%{100-can_pay:.1f})", fontsize=8, color="#d1242f")
    a.legend(fontsize=8); a.grid(alpha=.3)

    # (3) ORTALAMA SATIŞ BEDELİ ----------------------------------------------
    a = ax[0, 1]
    for D, g in s.groupby("Tünel_D_m"):
        a.plot(g["Q_tasarım_m3/s"], g["Yakalanan_fiyat_EUR/MWh"], "o-",
               color=RENK[D], label=f"D={D:.1f} m")
    a.axhline(ptf_ort, color="#57606a", ls="--", lw=1.2,
              label=f"yıllık ort. piyasa fiyatı ({ptf_ort:.2f})")
    a.set_title("ORTALAMA SATIŞ BEDELİ  (üretim ağırlıklı yakalanan fiyat)")
    a.set_xlabel("Tasarım debisi [m³/s]")
    a.set_ylabel("Satış bedeli [EUR/MWh]")
    _eksen_sik(a, s["Yakalanan_fiyat_EUR/MWh"], [ptf_ort])
    a.legend(fontsize=8); a.grid(alpha=.3)

    # (4) CEBRİ BORU HIZI — ekonomik çap ---------------------------------------
    a = ax[1, 1]
    en = t.loc[t["Net_fayda_MEUR/yıl"].idxmax()]
    for D, gg in t[t["Tünel_hızı_m/s"] > 3.75].groupby("Tünel_D_m"):
        gg = gg.sort_values("Cebri_hızı_m/s")
        a.plot(gg["Cebri_hızı_m/s"], gg["Net_fayda_MEUR/yıl"], "o-",
               color=RENK[D], label=f"D_tünel={D:.1f} m")
    a.scatter([en["Cebri_hızı_m/s"]], [en["Net_fayda_MEUR/yıl"]], s=190,
              facecolors="none", edgecolors="#d1242f", linewidths=2, zorder=5)
    a.set_title("CEBRİ BORU EKONOMİK ÇAPI\n"
                "(düşük hız = büyük çap = çok çelik · yüksek hız = çok kayıp)")
    a.set_xlabel("Cebri boru hızı [m/s]  →  çap küçülüyor")
    a.set_ylabel("Net fayda [milyon EUR/yıl]")
    _eksen_sik(a, t[t["Tünel_hızı_m/s"] > 3.75]["Net_fayda_MEUR/yıl"])
    a.legend(fontsize=7, ncol=2); a.grid(alpha=.3)

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(yol, dpi=130)
    plt.close(fig)


def dort_senaryo_grafikleri(yk, yol):
    """Dört işletme / gelir modelinin tek sayfada karşılaştırılması."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 3, figsize=(19, 11))
    fig.suptitle("HEZİL HES — DÖRT İŞLETME / GELİR MODELİNİN KARŞILAŞTIRILMASI\n"
                 f"indirgeme {INDIRGEME_ORANI:.2f} · EM {EM_BIRIM_EUR_KW:.0f} + "
                 f"santral/şalt {SANTRAL_SALT_EUR_KW:.0f} EUR/kW · "
                 f"çelik {CELIK_BIRIM_EUR_KG:.2f} EUR/kg",
                 fontsize=13, fontweight="bold")

    optimumlar = {}
    # --- her senaryo için net fayda – tasarım debisi eğrileri ----------------
    for j, (s, ad, renk_s) in enumerate(SENARYOLAR):
        a = ax[j // 2][j % 2]
        en = yk.loc[yk.groupby(["Tünel_D_m", "Q_tasarım_m3/s"])
                      [f"{s}_net_MEUR"].idxmax()].sort_values(
                          ["Tünel_D_m", "Q_tasarım_m3/s"])
        for D, g in en.groupby("Tünel_D_m"):
            a.plot(g["Q_tasarım_m3/s"], g[f"{s}_net_MEUR"], "o-", ms=4,
                   color=RENK[D], label=f"{D:.1f} m")
        b = yk.loc[yk[f"{s}_net_MEUR"].idxmax()]
        optimumlar[s] = b
        a.scatter([b["Q_tasarım_m3/s"]], [b[f"{s}_net_MEUR"]], s=200,
                  facecolors="none", edgecolors="#d1242f", linewidths=2, zorder=5)
        a.annotate(f"  D={b['Tünel_D_m']:.1f} m · Q={b['Q_tasarım_m3/s']:.1f} m³/s\n"
                   f"  {b[f'{s}_net_MEUR']:.3f} M€/yıl",
                   (b["Q_tasarım_m3/s"], b[f"{s}_net_MEUR"]), fontsize=8, va="top")
        a.set_title(f"[{s}] {ad}", color=renk_s, fontweight="bold")
        a.set_xlabel("Tasarım debisi [m³/s]")
        a.set_ylabel("Net fayda [milyon EUR/yıl]")
        _eksen_sik(a, en[f"{s}_net_MEUR"], ust_pay=0.18)
        a.legend(fontsize=7, ncol=2, title="tünel çapı", title_fontsize=7)
        a.grid(alpha=.3)

    # --- optimumların karşılaştırması ----------------------------------------
    a = ax[0, 2]
    x = np.arange(len(SENARYOLAR))
    kal = [("Tünel çapı [m]", "Tünel_D_m", 1.0),
           ("Cebri boru çapı [m]", "Cebri_D_m", 1.0),
           ("Tasarım debisi [m³/s] ÷10", "Q_tasarım_m3/s", 0.1),
           ("Kurulu güç [MW] ÷10", "Kurulu_güç_MW", 0.1)]
    w = 0.2
    for i, (ad, k, o) in enumerate(kal):
        v = [optimumlar[s][k] * o for s, _, _ in SENARYOLAR]
        a.bar(x + (i - 1.5) * w, v, w, label=ad)
        for xi, yy, ham in zip(x + (i - 1.5) * w, v,
                               [optimumlar[s][k] for s, _, _ in SENARYOLAR]):
            a.text(xi, yy, f"{ham:.1f}", ha="center", va="bottom", fontsize=7)
    a.set_xticks(x)
    a.set_xticklabels([ad for _, ad, _ in SENARYOLAR], fontsize=8)
    a.set_title("Optimum konfigürasyonlar")
    a.legend(fontsize=7); a.grid(alpha=.3, axis="y")

    # --- gelir / gider / net fayda -------------------------------------------
    a = ax[1, 2]
    w = 0.26
    for i, (ad, sk, c) in enumerate([("yıllık gelir", "gelir_MEUR", "#2da44e"),
                                     ("yıllık gider", None, "#d1242f"),
                                     ("NET FAYDA", "net_MEUR", "#0969da")]):
        if sk is None:
            v = [optimumlar[s]["Yıllık_gider_MEUR"] for s, _, _ in SENARYOLAR]
        else:
            v = [optimumlar[s][f"{s}_{sk}"] for s, _, _ in SENARYOLAR]
        a.bar(x + (i - 1) * w, v, w, color=c, label=ad)
        for xi, yy in zip(x + (i - 1) * w, v):
            a.text(xi, yy, f"{yy:.2f}", ha="center", va="bottom", fontsize=7)
    a.set_xticks(x)
    a.set_xticklabels([ad for _, ad, _ in SENARYOLAR], fontsize=8)
    a.set_ylabel("milyon EUR/yıl")
    a.set_title("Her senaryonun kendi optimumunda gelir – gider – net fayda")
    a.legend(fontsize=8); a.grid(alpha=.3, axis="y")

    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(yol, dpi=130)
    plt.close(fig)


def pik_bant_grafikleri(t, t_bant, ptf_ort, yol):
    """PİK (gelir maks.) ile BANT (enerji maks.) işletmenin karşılaştırılması."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def enipi(d, hedef):
        return d.loc[d.groupby(["Tünel_D_m", "Q_tasarım_m3/s"])[hedef].idxmax()
                     ].sort_values(["Tünel_D_m", "Q_tasarım_m3/s"])

    sp = enipi(t, "Net_fayda_MEUR/yıl")
    sb = enipi(t_bant, "Net_fayda_MEUR/yıl")

    fig, ax = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle("HEZİL HES — PİK (puant, gelir maks.) ve BANT (enerji maks.) "
                 "İŞLETMENİN KARŞILAŞTIRILMASI\n"
                 "sürekli çizgi = pik işletme · kesikli çizgi = bant işletme",
                 fontsize=13, fontweight="bold")

    def ciz(a, sut, baslik, ybaslik, ref_cizgi=None, ref_ad=None):
        for D, g in sp.groupby("Tünel_D_m"):
            a.plot(g["Q_tasarım_m3/s"], g[sut], "o-", ms=4,
                   color=RENK[D], label=f"D={D:.1f} m")
        for D, g in sb.groupby("Tünel_D_m"):
            a.plot(g["Q_tasarım_m3/s"], g[sut], "s--", ms=4, alpha=.75,
                   color=RENK[D])
        if ref_cizgi is not None:
            a.axhline(ref_cizgi, color="#57606a", ls=":", lw=1.2, label=ref_ad)
            _eksen_sik(a, sp[sut], sb[sut], [ref_cizgi])
        else:
            _eksen_sik(a, sp[sut], sb[sut])
        a.set_title(baslik)
        a.set_xlabel("Tasarım debisi [m³/s]")
        a.set_ylabel(ybaslik)
        a.legend(fontsize=7, ncol=2); a.grid(alpha=.3)

    ciz(ax[0, 0], "Net_fayda_MEUR/yıl",
        "NET FAYDA — pik işletme her konfigürasyonda üstün",
        "Net fayda [milyon EUR/yıl]")
    ciz(ax[0, 1], "Enerji_GWh/yıl",
        "ENERJİ — bant işletme yük kaybı az olduğu için daha çok üretiyor",
        "Enerji [GWh/yıl]")
    ciz(ax[1, 0], "Yakalanan_fiyat_EUR/MWh",
        "ORTALAMA SATIŞ BEDELİ", "Satış bedeli [EUR/MWh]",
        ptf_ort, f"yıllık ort. piyasa fiyatı ({ptf_ort:.2f})")

    # optimum konfigürasyonların doğrudan karşılaştırması
    a = ax[1, 1]
    p = t.loc[t["Net_fayda_MEUR/yıl"].idxmax()]
    b = t_bant.loc[t_bant["Net_fayda_MEUR/yıl"].idxmax()]
    kalem = ["Enerji_GWh/yıl", "Gelir_MEUR/yıl", "Yıllık_gider_MEUR",
             "Net_fayda_MEUR/yıl"]
    etiket = ["Enerji\n[GWh/yıl]", "Gelir\n[M€/yıl]", "Gider\n[M€/yıl]",
              "NET FAYDA\n[M€/yıl]"]
    # enerjiyi aynı ölçeğe getirmek için 25'e böl (yalnızca görsel)
    olcek = [1 / 25.0, 1.0, 1.0, 1.0]
    x = np.arange(len(kalem))
    w = 0.36
    vp = [p[k] * o for k, o in zip(kalem, olcek)]
    vb = [b[k] * o for k, o in zip(kalem, olcek)]
    a.bar(x - w/2, vp, w, color="#0969da",
          label=f"PİK  (D={p['Tünel_D_m']:.1f} m, Q={p['Q_tasarım_m3/s']:.1f})")
    a.bar(x + w/2, vb, w, color="#bf3989",
          label=f"BANT (D={b['Tünel_D_m']:.1f} m, Q={b['Q_tasarım_m3/s']:.1f})")
    for i, (k, o) in enumerate(zip(kalem, olcek)):
        a.text(i - w/2, p[k]*o, f"{p[k]:.2f}", ha="center", va="bottom", fontsize=8)
        a.text(i + w/2, b[k]*o, f"{b[k]:.2f}", ha="center", va="bottom", fontsize=8)
    a.set_xticks(x); a.set_xticklabels(etiket, fontsize=8)
    a.set_title("Her iki amaç fonksiyonunun KENDİ OPTİMUM konfigürasyonu\n"
                "(enerji çubuğu görsel amaçla 25'e bölünmüştür)")
    a.legend(fontsize=8); a.grid(alpha=.3, axis="y")

    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(yol, dpi=130)
    plt.close(fig)


# ==============================================================================
# PARALEL ÇÖZÜM YARDIMCILARI
# Süreç havuzu Windows'ta "spawn" ile çalışır; her işçi modülü baştan içe
# aktarır ve fiyat-süre eğrilerini bir kez kurar.
# ==============================================================================
_ISCI = {}


def _isci_kur(ptf_yol):
    ptf, _ = opt.ptf_oku(ptf_yol)
    _ISCI["fse"] = opt.FiyatSureEgrisi(ptf)
    _ISCI["ptf_ort"] = float(ptf.mean())


def _isci_coz(g):
    D_t, v_t, v_c, kot_min, amac = g
    return alternatif_coz(D_t, v_t, v_c, kot_min, _ISCI["fse"],
                          _ISCI["ptf_ort"], amac)


def grafikler(t, yol):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    renk = RENK
    fig, ax = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle("HEZİL HES — Alternatif Taraması: tünel çapı × tasarım debisi "
                 "× minimum su kotu", fontsize=14, fontweight="bold")

    en_iyi_kot = float(t.loc[t["Gelir_MEUR/yıl"].idxmax(), "Min_kot_m"])

    a = ax[0, 0]
    gk = t[t["Min_kot_m"] == en_iyi_kot]
    for D, g in gk.groupby("Tünel_D_m"):
        g = g.sort_values("Q_tasarım_m3/s")
        a.plot(g["Q_tasarım_m3/s"], g["Gelir_MEUR/yıl"], "o-", color=renk[D],
               label=f"D={D:.1f} m")
    a.set_title(f"Ortalama yıllık gelir — minimum kot {en_iyi_kot:.0f} m")
    a.set_xlabel("Tasarım debisi [m³/s]"); a.set_ylabel("Gelir [milyon EUR/yıl]")
    _eksen_sik(a, gk["Gelir_MEUR/yıl"])
    a.legend(fontsize=8); a.grid(alpha=.3)

    a = ax[0, 1]
    en = t.loc[t.groupby(["Tünel_D_m", "Q_tasarım_m3/s"])
                ["Net_fayda_MEUR/yıl"].idxmax()].sort_values("Q_tasarım_m3/s")
    a.plot(en["Q_tasarım_m3/s"], en["Tünel_maliyeti_MEUR"], "o-",
           color="#57606a", label="tünel")
    a.plot(en["Q_tasarım_m3/s"], en["Cebri_maliyet_MEUR"], "s-",
           color="#bf3989", label="cebri boru (çelik)")
    a.plot(en["Q_tasarım_m3/s"], en["EM_maliyeti_MEUR"], "^-",
           color="#2da44e", label="elektromekanik")
    a.plot(en["Q_tasarım_m3/s"], en["Yatırım_MEUR"], "d-",
           color="#0969da", lw=2, label="TOPLAM YATIRIM")
    a.set_title("Yatırım dökümü — tasarım debisine göre")
    a.set_xlabel("Tasarım debisi [m³/s]"); a.set_ylabel("Yatırım [milyon EUR]")
    a.legend(fontsize=8); a.grid(alpha=.3)

    a = ax[1, 0]
    for D, g in gk.groupby("Tünel_D_m"):
        g = g.sort_values("Q_tasarım_m3/s")
        a.plot(g["Q_tasarım_m3/s"], g["Enerji_GWh/yıl"], "o-", color=renk[D],
               label=f"D={D:.1f} m")
    a.set_title(f"Ortalama yıllık enerji — minimum kot {en_iyi_kot:.0f} m")
    a.set_xlabel("Tasarım debisi [m³/s]"); a.set_ylabel("Enerji [GWh/yıl]")
    _eksen_sik(a, gk["Enerji_GWh/yıl"])
    a.legend(fontsize=8); a.grid(alpha=.3)

    a = ax[1, 1]
    for D, g in t.groupby("Tünel_D_m"):
        a.scatter(g["Kurulu_güç_MW"], g["Gelir_MEUR/yıl"], s=18, color=renk[D],
                  alpha=.75, label=f"D={D:.1f} m")
    en = t.loc[t["Gelir_MEUR/yıl"].idxmax()]
    a.scatter([en["Kurulu_güç_MW"]], [en["Gelir_MEUR/yıl"]], s=160,
              facecolors="none", edgecolors="#d1242f", linewidths=2,
              label="en yüksek gelir")
    a.set_title("Bütün alternatifler: kurulu güç – gelir")
    a.set_xlabel("Kurulu güç [MW]"); a.set_ylabel("Gelir [milyon EUR/yıl]")
    a.legend(fontsize=8); a.grid(alpha=.3)

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(yol, dpi=130)
    plt.close(fig)


def main():
    kd = os.path.dirname(os.path.abspath(__file__))
    print("=" * 96)
    print("HEZİL HES — ALTERNATİF TARAMASI (tünel çapı × tasarım debisi × "
          "minimum su kotu)")
    print("=" * 96)

    ptf, kaynak = opt.ptf_oku(os.path.join(kd, opt.PTF_DOSYASI))
    fse = opt.FiyatSureEgrisi(ptf)
    ptf_ort = float(ptf.mean())
    print(f"Fiyat verisi : {kaynak}")
    print(f"Dönem        : {ptf.index.min():%d.%m.%Y} – {ptf.index.max():%d.%m.%Y}"
          f"   ortalama {ptf_ort:.2f} {opt.PTF_PARA_BIRIMI}")
    print(f"Sabitler     : tünel L={TUNEL_UZUNLUK:.0f} m, cebri boru "
          f"L={CEBRI_UZUNLUK:.0f} m, maks. kot {opt.KOT_MAKS:.0f} m, "
          f"kuyruk suyu {opt.KOT_KUYRUK:.0f} m, {opt.UNITE_SAYISI} ünite")
    n = len(TUNEL_CAPLARI) * len(TUNEL_HIZLARI) * len(MIN_KOTLAR)
    print(f"Alternatif   : {len(TUNEL_CAPLARI)} çap × {len(TUNEL_HIZLARI)} hız "
          f"× {len(MIN_KOTLAR)} kot = {n} adet\n")

    print(f"{'#':>4} {'D_tün':>6} {'v_tün':>6} {'Q':>6} {'D_ceb':>6} {'v_ceb':>6}"
          f" {'et':>6} {'çelik':>8} {'Kayıp':>6} {'P_kur':>7} {'Enerji':>8}"
          f" {'Gelir':>8} {'NET':>8}")
    print(f"{'':>4} {'m':>6} {'m/s':>6} {'m³/s':>6} {'m':>6} {'m/s':>6}"
          f" {'mm':>6} {'ton':>8} {'m':>6} {'MW':>7} {'GWh/yıl':>8}"
          f" {'MEUR':>8} {'MEUR':>8}")
    print("-" * 104)

    gorevler = [(D_t, v_t, v_c, km, amac)
                for amac in ("gelir", "enerji")
                for D_t in TUNEL_CAPLARI
                for v_t in TUNEL_HIZLARI
                for v_c in CEBRI_HIZLARI
                for km in MIN_KOTLAR]

    kayitlar = []
    t0 = time.time()
    N = len(gorevler)

    def ilerle(i):
        if i % 100 and i != N:
            return
        ge = time.time() - t0
        kalan = ge / max(i, 1) * (N - i)
        print(f"    {i:5d}/{N}  (%{i/N*100:5.1f})  geçen {ge:5.0f} s  "
              f"kalan ~{kalan:5.0f} s", end="\r")

    if PARALEL > 1:
        from concurrent.futures import ProcessPoolExecutor
        print(f"    {PARALEL} süreçle paralel çözülüyor "
              f"(tek çekirdekte ~{N*1.2/60:.0f} dk sürerdi)...")
        with ProcessPoolExecutor(
                PARALEL, initializer=_isci_kur,
                initargs=(os.path.join(kd, opt.PTF_DOSYASI),)) as havuz:
            for i, r in enumerate(havuz.map(_isci_coz, gorevler, chunksize=6), 1):
                kayitlar.append(r)
                ilerle(i)
    else:
        for i, g in enumerate(gorevler, 1):
            kayitlar.append(alternatif_coz(g[0], g[1], g[2], g[3],
                                           fse, ptf_ort, g[4]))
            ilerle(i)

    print(" " * 78, end="\r")
    print("-" * 104)
    print(f"{N} koşum {time.time()-t0:.0f} saniyede çözüldü "
          f"({N//2} alternatif × 2 amaç fonksiyonu, {PARALEL} süreç).\n")

    hepsi = pd.DataFrame(kayitlar)
    hepsi.insert(0, "Alt_No", range(1, len(hepsi) + 1))
    t_bant = hepsi[hepsi["Amaç"].str.startswith("BANT")].copy()
    t = hepsi[hepsi["Amaç"].str.startswith("PİK")].copy()   # ana değerlendirme

    # ---- referans: mevcut tasarım (D=4.4 m, Q=60 m3/s, min kot 720 m) --------
    # Not: v_tünel = 3.95 m/s olduğu için tarama aralığının (2.8–3.8) dışındadır,
    # yalnızca karşılaştırma amacıyla çözülür.
    v_ref = 60.0 / (np.pi * 4.4**2 / 4)
    vc_ref = 60.0 / (np.pi * 3.9**2 / 4)            # mevcut cebri boru D=3.9 m
    ref = alternatif_coz(4.4, v_ref, vc_ref, 720.0, fse, ptf_ort, "gelir")
    ref["Alt_No"] = 0
    ref_bant = alternatif_coz(4.4, v_ref, vc_ref, 720.0, fse, ptf_ort, "enerji")
    ref_bant["Alt_No"] = 0
    referans = pd.DataFrame([ref, ref_bant])[t.columns]
    print(f"\nREFERANS (mevcut tasarım) D=4.4 m, Q={ref['Q_tasarım_m3/s']:.1f} m³/s "
          f"(v={ref['Tünel_hızı_m/s']:.2f} m/s), min kot 720 m")
    print(f"   kurulu güç {ref['Kurulu_güç_MW']:.2f} MW | "
          f"{ref['Enerji_GWh/yıl']:.2f} GWh/yıl | "
          f"{ref['Gelir_MEUR/yıl']:.3f} MEUR/yıl")

    # ---- pivot tabloları -----------------------------------------------------
    def pivot(deger):
        p = t.pivot_table(index=["Tünel_D_m", "Q_tasarım_m3/s"],
                          columns="Min_kot_m", values=deger)
        p.columns = [f"{c:.0f} m" for c in p.columns]
        return p

    piv_gelir  = pivot("Gelir_MEUR/yıl")          # net gelir
    piv_enerji = pivot("Enerji_GWh/yıl")
    piv_guc    = pivot("Kurulu_güç_MW")
    piv_cf     = pivot("Kapasite_faktörü_%")

    piv_net    = pivot("Net_fayda_MEUR/yıl")
    piv_reg    = pivot("Regülasyon_oranı_%")
    en_iyi = t.sort_values("Net_fayda_MEUR/yıl", ascending=False).head(20)

    # Ekonomi sayfası: her (çap, debi) seçeneğinin en iyi min. kotu
    ekon = t.loc[t.groupby(["Tünel_D_m", "Q_tasarım_m3/s"])
                  ["Net_fayda_MEUR/yıl"].idxmax()].sort_values(
                      "Net_fayda_MEUR/yıl", ascending=False)[[
        "Tünel_D_m", "Tünel_hızı_m/s", "Q_tasarım_m3/s", "Cebri_D_m",
        "Cebri_hızı_m/s", "Cebri_et_mm", "Çelik_ağırlık_t", "Min_kot_m",
        "Kurulu_güç_MW", "Enerji_GWh/yıl", "Regülasyon_oranı_%", "Depolama_oranı_%",
        "SÜRTÜNME_toplam_m", "YEREL_toplam_m", "Yük_kaybı_m",
        "Ağırlıklı_türbin_verimi_%", "Ağırlıklı_toplam_verim_%", "Sistem_verimi_%",
        "Ağırlıklı_yük_kaybı_m", "Ağırlıklı_net_düşü_m",
        "Rated_rezervuar_kotu_m", "Rated_brüt_düşü_m", "Rated_net_düşü_m",
        "Rated_net_düşü_1Ü_m", "Rated_net_düşü_2Ü_m",
        "Tünel_maliyeti_MEUR", "Cebri_maliyet_MEUR", "EM_maliyeti_MEUR",
        "Santral_şalt_MEUR", "Yatırım_MEUR",
        "Brüt_gelir_MEUR/yıl", "Gelir_kesintisi_MEUR",
        "Gelir_MEUR/yıl", "Yıllık_gider_MEUR", "Net_fayda_MEUR/yıl",
        "Fayda_masraf_oranı", "Yakalanan_fiyat_EUR/MWh",
        "Birim_enerji_maliyeti_EUR/MWh"]]

    # ---- sonuç özeti ---------------------------------------------------------
    b = t.loc[t["Gelir_MEUR/yıl"].idxmax()]
    print("\nEN YÜKSEK GELİRLİ ALTERNATİF")
    print(f"   Tünel D={b['Tünel_D_m']:.1f} m (v={b['Tünel_hızı_m/s']:.2f} m/s), "
          f"Q_tasarım={b['Q_tasarım_m3/s']:.1f} m³/s, "
          f"cebri boru D={b['Cebri_D_m']:.2f} m")
    print(f"   Minimum su kotu {b['Min_kot_m']:.0f} m → aktif hacim "
          f"{b['Aktif_hacim_hm3']:.1f} hm³")
    print(f"   Kurulu güç {b['Kurulu_güç_MW']:.2f} MW, enerji "
          f"{b['Enerji_GWh/yıl']:.2f} GWh/yıl, GELİR "
          f"{b['Gelir_MEUR/yıl']:.3f} milyon EUR/yıl")
    print(f"   Referans tasarıma göre : enerji "
          f"{(b['Enerji_GWh/yıl']/ref['Enerji_GWh/yıl']-1)*100:+.1f} %, gelir "
          f"{(b['Gelir_MEUR/yıl']/ref['Gelir_MEUR/yıl']-1)*100:+.1f} %")

    # ---- ekonomi -------------------------------------------------------------
    n = t.loc[t["Net_fayda_MEUR/yıl"].idxmax()]
    print("\n" + "=" * 96)
    print("EKONOMİK DEĞERLENDİRME  (yıllık gelir-gider, indirgeme oranı "
          f"{INDIRGEME_ORANI:.2f}, EM {EM_BIRIM_EUR_KW:.0f} EUR/kW)")
    print("=" * 96)
    print("EN YÜKSEK NET FAYDALI ALTERNATİF")
    print(f"   Tünel D={n['Tünel_D_m']:.1f} m (v={n['Tünel_hızı_m/s']:.2f} m/s), "
          f"Q={n['Q_tasarım_m3/s']:.1f} m³/s, cebri boru D={n['Cebri_D_m']:.2f} m, "
          f"min kot {n['Min_kot_m']:.0f} m")
    print(f"   Kurulu güç {n['Kurulu_güç_MW']:.2f} MW | enerji "
          f"{n['Enerji_GWh/yıl']:.2f} GWh/yıl | regülasyon oranı "
          f"%{n['Regülasyon_oranı_%']:.1f}")
    print(f"   Yatırım {n['Yatırım_MEUR']:.3f} M EUR "
          f"(tünel {n['Tünel_maliyeti_MEUR']:.3f} + EM {n['EM_maliyeti_MEUR']:.3f})")
    print(f"   Yıllık NET gelir {n['Gelir_MEUR/yıl']:.3f} "
          f"(brüt {n['Brüt_gelir_MEUR/yıl']:.3f}) − yıllık sabit gider "
          f"{n['Yıllık_gider_MEUR']:.3f} = NET FAYDA "
          f"{n['Net_fayda_MEUR/yıl']:.3f} M EUR/yıl")
    print(f"   Fayda/masraf oranı {n['Fayda_masraf_oranı']:.3f} | satış bedeli "
          f"{n['Yakalanan_fiyat_EUR/MWh']:.2f} vs birim maliyet "
          f"{n['Birim_enerji_maliyeti_EUR/MWh']:.2f} EUR/MWh")

    print("\n" + "=" * 96)
    print("YÜK KAYBI DÖKÜMÜ ve AĞIRLIKLI ORTALAMA VERİMLER "
          "(her çapın en iyi seçeneği)")
    print("=" * 96)
    print(f"   {'D':>5} {'Q':>6} | {'Giriş':>6} {'Tün.sür':>8} {'Tün.yer':>8}"
          f" {'Ceb.sür':>8} {'Ceb.yer':>8} {'Kol.sür':>8} {'Kol.yer':>8} |"
          f" {'SÜRT.':>7} {'YEREL':>7} {'TOPLAM':>7}")
    print(f"   {'m':>5} {'m³/s':>6} | " + " ".join(f"{'m':>8}" for _ in range(7)) +
          f" | {'m':>7} {'m':>7} {'m':>7}")
    for D in TUNEL_CAPLARI:
        g = t[t["Tünel_D_m"] == D]
        r = g.loc[g["Net_fayda_MEUR/yıl"].idxmax()]
        print(f"   {D:5.1f} {r['Q_tasarım_m3/s']:6.1f} | "
              f"{r['Giriş_kaybı_m']:6.3f} {r['Tünel_sürtünme_m']:8.3f}"
              f" {r['Tünel_yerel_m']:8.3f} {r['Cebri_sürtünme_m']:8.3f}"
              f" {r['Cebri_yerel_m']:8.3f} {r['Kol_sürtünme_m']:8.3f}"
              f" {r['Kol_yerel_m']:8.3f} | {r['SÜRTÜNME_toplam_m']:7.3f}"
              f" {r['YEREL_toplam_m']:7.3f} {r['Yük_kaybı_m']:7.3f}")
    print(f"\n   {'D':>5} {'Q':>6} | {'Sürt.payı':>10}{'Yerel payı':>11}"
          f"{'Kayıp/brüt':>11} | {'Ağ.türbin':>10}{'Ağ.toplam':>10}"
          f"{'Sistem':>9} | {'Ağ.brüt':>8}{'Ağ.kayıp':>9}{'Ağ.net':>8}"
          f" | {'RATED kot':>10}{'RATED net':>10}")
    print(f"   {'m':>5} {'m³/s':>6} | {'%':>10}{'%':>11}{'%':>11} | "
          f"{'%':>10}{'%':>10}{'%':>9} | {'m':>8}{'m':>9}{'m':>8}"
          f" | {'m':>10}{'m':>10}")
    for D in TUNEL_CAPLARI:
        g = t[t["Tünel_D_m"] == D]
        r = g.loc[g["Net_fayda_MEUR/yıl"].idxmax()]
        print(f"   {D:5.1f} {r['Q_tasarım_m3/s']:6.1f} | "
              f"{r['Sürtünme_payı_%']:10.1f}{r['Yerel_payı_%']:11.1f}"
              f"{r['Kayıp/brüt_düşü_%']:11.2f} | "
              f"{r['Ağırlıklı_türbin_verimi_%']:10.2f}"
              f"{r['Ağırlıklı_toplam_verim_%']:10.2f}"
              f"{r['Sistem_verimi_%']:9.2f} | "
              f"{r['Ağırlıklı_brüt_düşü_m']:8.2f}{r['Ağırlıklı_yük_kaybı_m']:9.3f}"
              f"{r['Ağırlıklı_net_düşü_m']:8.2f}"
              f" | {r['Rated_rezervuar_kotu_m']:10.2f}"
              f"{r['Rated_net_düşü_m']:10.2f}")
    print("\n   Not: 'Ağırlıklı' değerler işletme simülasyonundan ENERJİ AĞIRLIKLI"
          " ortalamalardır;")
    print("        kayıp dökümü ise TASARIM DEBİSİNDEKİ değerlerdir. İşletmede "
          "santral çoğu")
    print("        zaman kısmi yükte çalıştığı için ağırlıklı kayıp tasarım "
          "kaybından düşüktür.")

    print("\nHER ÇAP İÇİN EN İYİ SEÇENEK (net faydaya göre)")
    print(f"   {'D_tün':>6} {'Q':>6} {'D_ceb':>6} {'v_ceb':>6} {'et':>5}"
          f" {'çelik':>7} {'P_kur':>7} {'Enerji':>8} {'M_tün':>7} {'M_ceb':>7}"
          f" {'M_EM':>7} {'Yatırım':>8} {'Gelir':>7} {'Gider':>7} {'NET':>8}"
          f" {'F/M':>6}")
    print(f"   {'m':>6} {'m³/s':>6} {'m':>6} {'m/s':>6} {'mm':>5}"
          f" {'ton':>7} {'MW':>7} {'GWh':>8} {'MEUR':>7} {'MEUR':>7}"
          f" {'MEUR':>7} {'MEUR':>8} {'MEUR':>7} {'MEUR':>7} {'MEUR':>8}"
          f" {'-':>6}")
    for D in TUNEL_CAPLARI:
        g = t[t["Tünel_D_m"] == D]
        r = g.loc[g["Net_fayda_MEUR/yıl"].idxmax()]
        print(f"   {D:6.1f} {r['Q_tasarım_m3/s']:6.1f} {r['Cebri_D_m']:6.2f}"
              f" {r['Cebri_hızı_m/s']:6.2f} {r['Cebri_et_mm']:5.1f}"
              f" {r['Çelik_ağırlık_t']:7.0f} {r['Kurulu_güç_MW']:7.2f}"
              f" {r['Enerji_GWh/yıl']:8.2f} {r['Tünel_maliyeti_MEUR']:7.3f}"
              f" {r['Cebri_maliyet_MEUR']:7.3f} {r['EM_maliyeti_MEUR']:7.3f}"
              f" {r['Yatırım_MEUR']:8.3f} {r['Gelir_MEUR/yıl']:7.3f}"
              f" {r['Yıllık_gider_MEUR']:7.3f} {r['Net_fayda_MEUR/yıl']:8.3f}"
              f" {r['Fayda_masraf_oranı']:6.3f}")

    print("\nCEBRİ BORU HIZININ ETKİSİ (tünel çapı ve debisi en iyi seçenekte "
          "sabit tutularak)")
    en = t.loc[t["Net_fayda_MEUR/yıl"].idxmax()]
    g = t[(t["Tünel_D_m"] == en["Tünel_D_m"]) &
          (t["Q_tasarım_m3/s"] == en["Q_tasarım_m3/s"])].sort_values("Cebri_hızı_m/s")
    print(f"   {'v_ceb':>6} {'D_ceb':>6} {'et':>5} {'çelik':>7} {'M_ceb':>7}"
          f" {'Kayıp':>6} {'Enerji':>8} {'Gelir':>7} {'Gider':>7} {'NET':>8}")
    print(f"   {'m/s':>6} {'m':>6} {'mm':>5} {'ton':>7} {'MEUR':>7}"
          f" {'m':>6} {'GWh':>8} {'MEUR':>7} {'MEUR':>7} {'MEUR':>8}")
    for _, r in g.iterrows():
        yildiz = "  ←" if r["Cebri_hızı_m/s"] == en["Cebri_hızı_m/s"] else ""
        print(f"   {r['Cebri_hızı_m/s']:6.2f} {r['Cebri_D_m']:6.2f}"
              f" {r['Cebri_et_mm']:5.1f} {r['Çelik_ağırlık_t']:7.0f}"
              f" {r['Cebri_maliyet_MEUR']:7.3f} {r['Yük_kaybı_m']:6.2f}"
              f" {r['Enerji_GWh/yıl']:8.2f} {r['Gelir_MEUR/yıl']:7.3f}"
              f" {r['Yıllık_gider_MEUR']:7.3f} {r['Net_fayda_MEUR/yıl']:8.3f}"
              f"{yildiz}")

    print(f"   {'REF':>5} {ref['Q_tasarım_m3/s']:6.1f} {720:6.0f}"
          f" {ref['Kurulu_güç_MW']:7.2f} {ref['Enerji_GWh/yıl']:8.2f}"
          f" {ref['Yatırım_MEUR']:9.3f} {ref['Gelir_MEUR/yıl']:7.3f}"
          f" {ref['Yıllık_gider_MEUR']:7.3f} {ref['Net_fayda_MEUR/yıl']:8.3f}"
          f" {ref['Fayda_masraf_oranı']:6.3f} {ref['Regülasyon_oranı_%']:6.1f}"
          f" {ref['Yakalanan_fiyat_EUR/MWh']:7.2f}"
          f" {ref['Birim_enerji_maliyeti_EUR/MWh']:7.2f}")

    # ---- YEKDEM senaryosu ----------------------------------------------------
    # Aynı konfigürasyonun PİK ve BANT çözümleri eşleştirilir:
    #   ilk 10 yıl sabit tarife → BANT işletme enerjisi
    #   kalan 40 yıl serbest piyasa → PİK işletme geliri
    anah = ["Tünel_D_m", "Q_tasarım_m3/s", "Cebri_hızı_m/s", "Min_kot_m"]
    # BANT çözümünün ANMA değerleri de taşınır: S2/S3 bant işletir, S4'ün ilk
    # 10 yılı bant, kalan 40 yılı pik — iki dönemin anma noktası FARKLIDIR.
    RATED = ["Rated_rezervuar_kotu_m", "Rated_brüt_düşü_m", "Rated_net_düşü_m",
             "Rated_net_düşü_1Ü_m", "Rated_net_düşü_2Ü_m"]
    yk = t.merge(t_bant[anah + ["Enerji_GWh/yıl", "Brüt_gelir_MEUR/yıl",
                                "Çalışma_saati_h/yıl",
                                "Yakalanan_fiyat_EUR/MWh",
                                "Regülasyon_oranı_%"] + RATED],
                 on=anah, suffixes=("", "_bant"))
    yk = senaryo_gelirleri(yk)

    kats, pik_kat, sgkf = _yekdem_katsayilar()
    print("\n" + "=" * 110)
    print("DÖRT İŞLETME / GELİR MODELİ")
    print("=" * 110)
    print("   S1 PİK · piyasa   : ömür boyu puant işletme, saatlik piyasa fiyatı")
    print("   S2 BANT · piyasa  : ömür boyu enerji maks., ay ortalama fiyatı")
    print(f"   S3 SABİT          : ömür boyu {SABIT_BIRIM_FAYDA:.0f} EUR/MWh sabit, "
          f"enerji maks.")
    print("   S4 YEKDEM         : sabit alım garantisi + serbest piyasa")
    y0 = 1
    for (yil, fiyat), (_, f, k) in zip(YEKDEM_KADEMELER, kats):
        print(f"        yıl {y0:2d}–{y0+yil-1:2d} : {fiyat:5.1f} EUR/MWh (BANT) "
              f"→ PD payı %{f*sgkf*100:4.1f}")
        y0 += yil
    print(f"        yıl {y0:2d}–{PROJE_OMRU:2d} : serbest piyasa (PİK)      "
          f"→ PD payı %{pik_kat*100:4.1f}")
    print(f"        iskonto {ISKONTO:.2f} · ömür {PROJE_OMRU} yıl · "
          f"SGKF {sgkf:.5f}")
    print("   Yıllık gider dört senaryoda AYNIDIR (konfigürasyon aynı → "
          "yatırım aynı).")

    optimumlar = {}
    for s, ad, _ in SENARYOLAR:
        b = yk.loc[yk[f"{s}_net_MEUR"].idxmax()]
        optimumlar[s] = b
        print(f"\n   [{s}] {ad} — HER ÇAP İÇİN EN İYİ SEÇENEK")
        print(f"      {'D':>5} {'Q':>6} {'D_ceb':>6} {'v_ceb':>6} {'P_kur':>7}"
              f" {'Enerji':>8} {'Yatırım':>8} {'Gelir':>7} {'Gider':>7}"
              f" {'NET':>8} {'F/M':>6}")
        for D in TUNEL_CAPLARI:
            g = yk[yk["Tünel_D_m"] == D]
            r = g.loc[g[f"{s}_net_MEUR"].idxmax()]
            im = "  ←" if (r["Tünel_D_m"] == b["Tünel_D_m"] and
                           r["Q_tasarım_m3/s"] == b["Q_tasarım_m3/s"]) else ""
            print(f"      {D:5.1f} {r['Q_tasarım_m3/s']:6.1f}"
                  f" {r['Cebri_D_m']:6.2f} {r['Cebri_hızı_m/s']:6.2f}"
                  f" {r['Kurulu_güç_MW']:7.2f} {r[f'{s}_enerji_GWh']:8.2f}"
                  f" {r['Yatırım_MEUR']:8.3f} {r[f'{s}_gelir_MEUR']:7.3f}"
                  f" {r['Yıllık_gider_MEUR']:7.3f} {r[f'{s}_net_MEUR']:8.3f}"
                  f" {r[f'{s}_F/M']:6.3f}{im}")

    # ---- dört senaryonun optimumları yan yana --------------------------------
    print("\n" + "=" * 110)
    print("DÖRT SENARYONUN OPTİMUM KONFİGÜRASYONU")
    print("=" * 110)
    print(f"   {'':<28}" + "".join(f"{ad:>20}" for _, ad, _ in SENARYOLAR))
    kalemler = [
        ("Tünel çapı", "Tünel_D_m", "{:.1f} m"),
        ("Tünel hızı", "Tünel_hızı_m/s", "{:.2f} m/s"),
        ("Tasarım debisi", "Q_tasarım_m3/s", "{:.1f} m³/s"),
        ("Cebri boru çapı", "Cebri_D_m", "{:.2f} m"),
        ("Cebri boru hızı", "Cebri_hızı_m/s", "{:.1f} m/s"),
        ("Cebri boru et kalınlığı", "Cebri_et_mm", "{:.1f} mm"),
        ("Çelik ağırlığı", "Çelik_ağırlık_t", "{:.0f} ton"),
        ("Minimum su kotu", "Min_kot_m", "{:.0f} m"),
        ("Aktif hacim", "Aktif_hacim_hm3", "{:.2f} hm³"),
        ("Kurulu güç", "Kurulu_güç_MW", "{:.2f} MW"),
        ("Yük kaybı @Q_tas", "Yük_kaybı_m", "{:.2f} m"),
        ("Tünel maliyeti", "Tünel_maliyeti_MEUR", "{:.3f} M€"),
        ("Cebri boru+tünel", "Cebri_maliyet_MEUR", "{:.3f} M€"),
        ("Elektromekanik", "EM_maliyeti_MEUR", "{:.3f} M€"),
        ("Santral + şalt", "Santral_şalt_MEUR", "{:.3f} M€"),
        ("TOPLAM YATIRIM", "Yatırım_MEUR", "{:.3f} M€"),
        ("Yıllık gider", "Yıllık_gider_MEUR", "{:.3f} M€"),
    ]
    for ad, k, fm in kalemler:
        print(f"   {ad:<28}" + "".join(
            f"{fm.format(optimumlar[s][k]):>20}" for s, _, _ in SENARYOLAR))

    # ---- ANMA (rated) değerleri: her senaryonun KENDİ işletme biçiminden ----
    # S1 → pik · S2, S3 → bant · S4 → 1–10. yıl bant, 11–50. yıl pik
    def _rated(s, k, fm):
        b = optimumlar[s]
        if s == "S1":
            return fm.format(b[k])
        if s in ("S2", "S3"):
            return fm.format(b[k + "_bant"])
        return f"{b[k + '_bant']:.1f}→{b[k]:.1f}"      # S4: bant → pik
    print(f"   {'':-<28}" + "".join(f"{'':->20}" for _ in SENARYOLAR))
    for ad, k, fm in [("RATED rezervuar kotu", "Rated_rezervuar_kotu_m", "{:.2f} m"),
                      ("RATED brüt düşü", "Rated_brüt_düşü_m", "{:.2f} m"),
                      ("RATED net düşü", "Rated_net_düşü_m", "{:.2f} m"),
                      ("  · 1 ünite işletmesinde", "Rated_net_düşü_1Ü_m", "{:.2f} m"),
                      ("  · 2 ünite işletmesinde", "Rated_net_düşü_2Ü_m", "{:.2f} m")]:
        print(f"   {ad:<28}" + "".join(
            f"{_rated(s, k, fm):>20}" for s, _, _ in SENARYOLAR))
    print(f"   {'(S4: 1–10. yıl bant → 11–50. yıl pik)':<28}"
          + "".join(f"{'':>20}" for _ in SENARYOLAR))
    print(f"   {'':-<28}" + "".join(f"{'':->20}" for _ in SENARYOLAR))
    for ad, sk, fm in [("Enerji", "enerji_GWh", "{:.2f} GWh/yıl"),
                       ("BRÜT gelir", "brut_MEUR", "{:.3f} M€"),
                       (f"  − kesinti (%{GELIR_KESINTI_ORANI*100:.0f})",
                        "kesinti_MEUR", "{:.3f} M€"),
                       ("NET GELİR", "gelir_MEUR", "{:.3f} M€"),
                       ("NİHAİ NET FAYDA", "net_MEUR", "{:.3f} M€/yıl"),
                       ("Fayda/masraf", "F/M", "{:.3f}")]:
        print(f"   {ad:<28}" + "".join(
            f"{fm.format(optimumlar[s][f'{s}_{sk}']):>20}"
            for s, _, _ in SENARYOLAR))
    print(f"   {'İşletme biçimi':<28}" +
          "".join(f"{x:>20}" for x in ["PİK", "BANT", "BANT", "BANT→PİK"]))

    # referansın dört senaryodaki durumu
    rf = yk[(yk["Tünel_D_m"] == 4.4) & (yk["Q_tasarım_m3/s"].round(1) ==
            round(60.0 / (np.pi * 4.4**2 / 4) * (np.pi * 4.4**2 / 4), 1))]
    if len(rf):
        rr = rf.loc[rf["S1_net_MEUR"].idxmax()]
        print(f"\n   {'REFERANSA YAKIN (D=4.4)':<28}" + "".join(
            f"{rr[f'{s}_net_MEUR']:>20.3f}" for s, _, _ in SENARYOLAR))
        print(f"   {'optimuma göre fark':<28}" + "".join(
            f"{(rr[f'{s}_net_MEUR']/optimumlar[s][f'{s}_net_MEUR']-1)*100:>19.1f}%"
            for s, _, _ in SENARYOLAR))

    # ---- PİK vs BANT işletme -------------------------------------------------
    npik  = t.loc[t["Net_fayda_MEUR/yıl"].idxmax()]
    nbant = t_bant.loc[t_bant["Net_fayda_MEUR/yıl"].idxmax()]
    print("\n" + "=" * 96)
    print("PİK (gelir maks.) — BANT (enerji maks.) İŞLETME KARŞILAŞTIRMASI")
    print("=" * 96)
    print(f"   {'':<22}{'PİK işletme':>22}{'BANT işletme':>22}{'fark':>14}")
    kars = [
        ("Optimum tünel çapı", "Tünel_D_m", "{:.1f} m"),
        ("Optimum tasarım debisi", "Q_tasarım_m3/s", "{:.1f} m³/s"),
        ("Optimum min. kot", "Min_kot_m", "{:.0f} m"),
        ("Kurulu güç", "Kurulu_güç_MW", "{:.2f} MW"),
        ("Enerji", "Enerji_GWh/yıl", "{:.2f} GWh/yıl"),
        ("Regülasyon oranı", "Regülasyon_oranı_%", "{:.1f} %"),
        ("Çalışma süresi", "Çalışma_saati_h/yıl", "{:.0f} h/yıl"),
        ("Satış bedeli", "Yakalanan_fiyat_EUR/MWh", "{:.2f} €/MWh"),
        ("Yatırım", "Yatırım_MEUR", "{:.3f} M€"),
        ("Yıllık net gelir", "Gelir_MEUR/yıl", "{:.3f} M€"),
        ("Yıllık gider", "Yıllık_gider_MEUR", "{:.3f} M€"),
        ("NET FAYDA", "Net_fayda_MEUR/yıl", "{:.3f} M€"),
        ("Fayda/masraf", "Fayda_masraf_oranı", "{:.3f}"),
    ]
    for ad, k, fm in kars:
        f = ((npik[k] / nbant[k] - 1) * 100) if nbant[k] else 0.0
        print(f"   {ad:<22}{fm.format(npik[k]):>22}{fm.format(nbant[k]):>22}"
              f"{f:>13.1f}%")

    # aynı konfigürasyonda (pik optimumu) iki işletmenin karşılaştırması
    ayni = t_bant[(t_bant["Tünel_D_m"] == npik["Tünel_D_m"]) &
                  (t_bant["Q_tasarım_m3/s"] == npik["Q_tasarım_m3/s"]) &
                  (t_bant["Min_kot_m"] == npik["Min_kot_m"])]
    if len(ayni):
        a = ayni.iloc[0]
        print(f"\n   AYNI KONFİGÜRASYON (D={npik['Tünel_D_m']:.1f} m, "
              f"Q={npik['Q_tasarım_m3/s']:.1f} m³/s) iki işletme biçimiyle:")
        print(f"      pik  : {npik['Enerji_GWh/yıl']:7.2f} GWh | "
              f"{npik['Gelir_MEUR/yıl']:6.3f} M€ | "
              f"{npik['Yakalanan_fiyat_EUR/MWh']:5.2f} €/MWh | "
              f"net {npik['Net_fayda_MEUR/yıl']:6.3f} M€")
        print(f"      bant : {a['Enerji_GWh/yıl']:7.2f} GWh | "
              f"{a['Gelir_MEUR/yıl']:6.3f} M€ | "
              f"{a['Yakalanan_fiyat_EUR/MWh']:5.2f} €/MWh | "
              f"net {a['Net_fayda_MEUR/yıl']:6.3f} M€")
        print(f"      → pik işletme {a['Enerji_GWh/yıl']-npik['Enerji_GWh/yıl']:.2f} "
              f"GWh/yıl enerjiden feragat edip "
              f"{npik['Gelir_MEUR/yıl']-a['Gelir_MEUR/yıl']:.3f} M€/yıl fazla "
              f"gelir elde ediyor")

    print("\nHER ÇAP İÇİN BANT (enerji maks.) İŞLETMEDE EN İYİ SEÇENEK")
    print(f"   {'D':>5} {'Q':>6} {'P_kur':>7} {'Enerji':>8} {'Gelir':>7}"
          f" {'Gider':>7} {'NET':>8} {'F/M':>6} {'Reg%':>6} {'Satış':>7}")
    for D in TUNEL_CAPLARI:
        g = t_bant[t_bant["Tünel_D_m"] == D]
        r = g.loc[g["Net_fayda_MEUR/yıl"].idxmax()]
        print(f"   {D:5.1f} {r['Q_tasarım_m3/s']:6.1f} {r['Kurulu_güç_MW']:7.2f}"
              f" {r['Enerji_GWh/yıl']:8.2f} {r['Gelir_MEUR/yıl']:7.3f}"
              f" {r['Yıllık_gider_MEUR']:7.3f} {r['Net_fayda_MEUR/yıl']:8.3f}"
              f" {r['Fayda_masraf_oranı']:6.3f} {r['Regülasyon_oranı_%']:6.1f}"
              f" {r['Yakalanan_fiyat_EUR/MWh']:7.2f}")

    print("\nEN İYİ 10 ALTERNATİF (net faydaya göre)")
    kol = ["Tünel_D_m", "Q_tasarım_m3/s", "Min_kot_m", "Kurulu_güç_MW",
           "Enerji_GWh/yıl", "Gelir_MEUR/yıl", "Yıllık_gider_MEUR",
           "Net_fayda_MEUR/yıl", "Fayda_masraf_oranı", "Regülasyon_oranı_%",
           "Yakalanan_fiyat_EUR/MWh"]
    print(en_iyi[kol].head(10).to_string(index=False))

    print("\nMİNİMUM SU KOTUNUN ETKİSİ (her kot için en iyi alternatif)")
    for k in MIN_KOTLAR:
        g = t[t["Min_kot_m"] == k]
        r = g.loc[g["Gelir_MEUR/yıl"].idxmax()]
        print(f"   {k:.0f} m → aktif hacim {r['Aktif_hacim_hm3']:5.1f} hm³ | "
              f"D={r['Tünel_D_m']:.1f} m, Q={r['Q_tasarım_m3/s']:5.1f} m³/s | "
              f"{r['Enerji_GWh/yıl']:6.2f} GWh/yıl | "
              f"{r['Gelir_MEUR/yıl']:6.3f} MEUR/yıl")

    print("\nTÜNEL ÇAPININ ETKİSİ (her çap için en iyi alternatif)")
    for D in TUNEL_CAPLARI:
        g = t[t["Tünel_D_m"] == D]
        r = g.loc[g["Gelir_MEUR/yıl"].idxmax()]
        print(f"   D={D:.1f} m → Q={r['Q_tasarım_m3/s']:5.1f} m³/s "
              f"(v={r['Tünel_hızı_m/s']:.2f} m/s), min kot {r['Min_kot_m']:.0f} m | "
              f"kayıp {r['Yük_kaybı_m']:5.2f} m | "
              f"{r['Enerji_GWh/yıl']:6.2f} GWh/yıl | "
              f"{r['Gelir_MEUR/yıl']:6.3f} MEUR/yıl")

    # ---- Excel ---------------------------------------------------------------
    girdiler = pd.DataFrame([
        ("Tünel çapları", ", ".join(f"{d:.1f}" for d in TUNEL_CAPLARI), "m"),
        ("Tünel hızı aralığı", f"{min(TUNEL_HIZLARI)} – {max(TUNEL_HIZLARI)}", "m/s"),
        ("Tünel uzunluğu", TUNEL_UZUNLUK, "m"),
        ("Cebri boru hızları (taranan)",
         ", ".join(f"{v:.1f}" for v in CEBRI_HIZLARI), "m/s"),
        ("Cebri boru uzunluğu", CEBRI_UZUNLUK, "m"),
        ("Kol çapı / cebri boru çapı", round(KOL_CAP_ORANI, 4), "-"),
        ("Minimum su kotları", ", ".join(f"{k:.0f}" for k in MIN_KOTLAR), "m"),
        ("Maksimum su seviyesi", opt.KOT_MAKS, "m"),
        ("Kuyruk suyu seviyesi", opt.KOT_KUYRUK, "m"),
        ("Ünite sayısı", opt.UNITE_SAYISI, "adet"),
        ("Can suyu (Ekim→Eylül)",
         ", ".join(f"{v:.3f}" for v in opt.CAN_SUYU_AYLIK), "m³/s"),
        ("Hidroloji", f"{opt.AKIM_YILLARI[0]}–{opt.AKIM_YILLARI[-1]} "
                      f"({opt.AKIMLAR.shape[0]} su yılı)", ""),
        ("Fiyat verisi", kaynak, ""),
        ("Yıllık ortalama fiyat", round(ptf_ort, 2), opt.PTF_PARA_BIRIMI),
        ("Alternatif sayısı", len(t), "adet"),
        ("—— MALİYETLER ——", "", ""),
        ("Tünel maliyeti tablosu (çap)",
         ", ".join(f"{d:.1f}" for d in TUNEL_MALIYET_CAP), "m"),
        ("Tünel maliyeti tablosu (bedel)",
         ", ".join(f"{c:,.0f}" for c in TUNEL_MALIYET_EUR), "EUR"),
        ("Ara çaplar", "monoton eğri interpolasyonu", ""),
        ("Cebri boru hızları (taranan)",
         ", ".join(f"{v:.1f}" for v in CEBRI_HIZLARI), "m/s"),
        ("Çelik birim maliyeti", CELIK_BIRIM_EUR_KG, "EUR/kg"),
        ("Çelik akma dayanımı", CELIK_AKMA / 1e6, "MPa"),
        ("Güvenlik katsayısı", GUVENLIK_KATSAYISI, "-"),
        ("Kaynak verimi", KAYNAK_VERIMI, "-"),
        ("Korozyon payı", KOROZYON_PAYI * 1000, "mm"),
        ("Su darbesi faktörü", SU_DARBESI_FAKTORU, "-"),
        ("İmalat fazlası", IMALAT_FAZLASI, "-"),
        ("Et kalınlığı", "t = p·D/(2·σ_izin·η_kaynak) + korozyon payı; "
                         "asgari USBR (D+508)/400 mm", ""),
        ("EM birim maliyeti", EM_BIRIM_EUR_KW, "EUR/kW"),
        ("Santral + şalt sahası", SANTRAL_SALT_EUR_KW, "EUR/kW"),
        ("Cebri boru tüneli uzunluğu", BORU_TUNEL_UZUNLUK, "m"),
        ("Boru tüneli kazı payı", BORU_TUNEL_PAYI, "m (boru dış çapı üstüne)"),
        ("Boru tüneli birim maliyeti", "ana tünel maliyet eğrisinden (EUR/m)", ""),
        ("Yıllık gidere indirgeme oranı", INDIRGEME_ORANI, "-"),
        ("Gelirden kesinti oranı", GELIR_KESINTI_ORANI, "-"),
        ("Net gelir", "brüt gelir × (1 − kesinti oranı)", ""),
        ("Nihai net fayda", "net gelir − yıllık sabit gider", ""),
        ("—— YEKDEM ——", "", ""),
        ("YEKDEM kademeleri",
         " · ".join(f"{y} yıl × {f:.1f} EUR/MWh" for y, f in YEKDEM_KADEMELER),
         ""),
        ("YEKDEM sonrası", f"{PROJE_OMRU - sum(y for y, _ in YEKDEM_KADEMELER)} "
                           f"yıl serbest piyasa (PİK işletme)", ""),
        ("Sabit tarife dönemi işletmesi", "BANT (enerji maks.)", ""),
        ("Proje ömrü", PROJE_OMRU, "yıl"),
        ("İskonto oranı", ISKONTO, "-"),
        ("YEKDEM geliri", "nakit akışının PD'si × SGKF = eşdeğer yıllık gelir", ""),
        ("İşletme-bakım oranı", OM_ORANI, "-"),
        ("Yıllık gider", "(tünel + EM) × indirgeme oranı", ""),
        ("Net fayda", "yıllık gelir − yıllık gider", ""),
    ], columns=["Girdi", "Değer", "Birim"])

    ekon_bant = t_bant.loc[t_bant.groupby(["Tünel_D_m", "Q_tasarım_m3/s"])
                            ["Net_fayda_MEUR/yıl"].idxmax()].sort_values(
                                "Net_fayda_MEUR/yıl", ascending=False)[ekon.columns]

    # pik–bant karşılaştırma sayfası (aynı konfigürasyonlar yan yana)
    anahtar = ["Tünel_D_m", "Q_tasarım_m3/s", "Min_kot_m"]
    kars_tab = t.merge(t_bant, on=anahtar, suffixes=("_pik", "_bant"))[
        anahtar + ["Kurulu_güç_MW_pik",
                   "Enerji_GWh/yıl_pik", "Enerji_GWh/yıl_bant",
                   "Çalışma_saati_h/yıl_pik", "Çalışma_saati_h/yıl_bant",
                   "Yakalanan_fiyat_EUR/MWh_pik", "Yakalanan_fiyat_EUR/MWh_bant",
                   "Gelir_MEUR/yıl_pik", "Gelir_MEUR/yıl_bant",
                   "Net_fayda_MEUR/yıl_pik", "Net_fayda_MEUR/yıl_bant"]]
    kars_tab = kars_tab.assign(
        Enerji_farkı_GWh=(kars_tab["Enerji_GWh/yıl_pik"]
                          - kars_tab["Enerji_GWh/yıl_bant"]).round(2),
        Gelir_farkı_MEUR=(kars_tab["Gelir_MEUR/yıl_pik"]
                          - kars_tab["Gelir_MEUR/yıl_bant"]).round(3),
    ).sort_values("Net_fayda_MEUR/yıl_pik", ascending=False)

    # kayıp dökümü + ağırlıklı verim sayfası (her (çap, debi) için en iyi min kot)
    kayip_verim = t.loc[t.groupby(["Tünel_D_m", "Q_tasarım_m3/s"])
                         ["Net_fayda_MEUR/yıl"].idxmax()].sort_values(
        ["Tünel_D_m", "Q_tasarım_m3/s"])[[
            "Tünel_D_m", "Tünel_hızı_m/s", "Q_tasarım_m3/s", "Cebri_D_m",
            "Cebri_hızı_m/s", "Cebri_et_mm", "Kol_et_mm", "Çelik_ağırlık_t",
            "Kol_D_m", "Min_kot_m",
            "Giriş_kaybı_m", "Tünel_sürtünme_m", "Tünel_yerel_m",
            "Cebri_sürtünme_m", "Cebri_yerel_m", "Kol_sürtünme_m", "Kol_yerel_m",
            "SÜRTÜNME_toplam_m", "YEREL_toplam_m", "Yük_kaybı_m",
            "Sürtünme_payı_%", "Yerel_payı_%", "Kayıp/brüt_düşü_%",
            "Ağırlıklı_türbin_verimi_%", "Ağırlıklı_toplam_verim_%",
            "Sistem_verimi_%", "Ağırlıklı_brüt_düşü_m", "Ağırlıklı_yük_kaybı_m",
            "Ağırlıklı_net_düşü_m",
            "Rated_rezervuar_kotu_m", "Rated_brüt_düşü_m",
            "Rated_yük_kaybı_m", "Rated_net_düşü_m",
            "Rated_net_düşü_1Ü_m", "Rated_net_düşü_2Ü_m",
            "Tek_ünite_su_payı_%"]]

    # ---- dört senaryo özeti ve tam tablosu ----------------------------------
    ORTAK = ["Tünel_D_m", "Tünel_hızı_m/s", "Q_tasarım_m3/s", "Cebri_D_m",
             "Cebri_hızı_m/s", "Cebri_et_mm", "Çelik_ağırlık_t",
             "Boru_tüneli_kazı_D_m", "Min_kot_m", "Aktif_hacim_hm3",
             "Kurulu_güç_MW", "Yük_kaybı_m",
             "Ağırlıklı_toplam_verim_%", "Sistem_verimi_%",
             "Rated_rezervuar_kotu_m", "Rated_brüt_düşü_m", "Rated_net_düşü_m",
             "Rated_net_düşü_1Ü_m", "Rated_net_düşü_2Ü_m", "Tek_ünite_su_payı_%",
             "Rated_rezervuar_kotu_m_bant", "Rated_brüt_düşü_m_bant",
             "Rated_net_düşü_m_bant", "Rated_net_düşü_1Ü_m_bant",
             "Rated_net_düşü_2Ü_m_bant",
             "Enerji_GWh/yıl", "Enerji_GWh/yıl_bant",
             "Çalışma_saati_h/yıl", "Çalışma_saati_h/yıl_bant",
             "Regülasyon_oranı_%", "Yakalanan_fiyat_EUR/MWh",
             "Tünel_maliyeti_MEUR", "Cebri_maliyet_MEUR", "EM_maliyeti_MEUR",
             "Santral_şalt_MEUR", "Yatırım_MEUR", "Yıllık_gider_MEUR"]
    SEN_SUT = [f"{s}_{x}" for s, _, _ in SENARYOLAR
               for x in ("enerji_GWh", "brut_MEUR", "kesinti_MEUR",
                         "gelir_MEUR", "net_MEUR", "F/M")]
    senaryo_tam = yk[ORTAK + SEN_SUT].sort_values("S4_net_MEUR", ascending=False)

    # her senaryonun optimumu tek satırda
    satir = []
    for s, ad, _ in SENARYOLAR:
        b = optimumlar[s]
        satir.append({
            "Senaryo": ad, "Kod": s,
            "İşletme": {"S1": "PİK", "S2": "BANT", "S3": "BANT",
                        "S4": "BANT (10 yıl) → PİK (40 yıl)"}[s],
            **{k: b[k] for k in ORTAK},
            "Enerji_GWh/yıl_senaryo": b[f"{s}_enerji_GWh"],
            "Brüt_gelir_MEUR/yıl": b[f"{s}_brut_MEUR"],
            "Gelir_kesintisi_MEUR": b[f"{s}_kesinti_MEUR"],
            "Net_gelir_MEUR/yıl": b[f"{s}_gelir_MEUR"],
            "Net_fayda_MEUR/yıl": b[f"{s}_net_MEUR"],
            "Fayda_masraf": b[f"{s}_F/M"],
            "Birim_enerji_maliyeti_EUR/MWh":
                round(b["Yıllık_gider_MEUR"] * 1e6
                      / max(b[f"{s}_enerji_GWh"] * 1000.0, 1e-9), 2),
        })
    ozet_4s = pd.DataFrame(satir)

    sayfalar = [
        ("Girdiler", girdiler, False),
        ("Kayıp ve Verim", kayip_verim, False),
        ("Tüm Alternatifler", pd.concat([referans, hepsi], ignore_index=True), False),
        ("4 Senaryo Özeti", ozet_4s, False),
        ("Tüm Senaryolar", senaryo_tam, False),
        ("PİK vs BANT", kars_tab, False),
        ("En İyi 20", en_iyi, False),
        ("Referans", referans, False),
        ("Pivot-Net Fayda MEUR", piv_net.round(3), True),
        ("Pivot-Gelir MEUR", piv_gelir.round(3), True),
        ("Pivot-Enerji GWh", piv_enerji.round(2), True),
        ("Pivot-Kurulu Güç MW", piv_guc.round(2), True),
        ("Pivot-Kapasite Faktörü", piv_cf.round(1), True),
        ("Pivot-Regülasyon Oranı", piv_reg.round(1), True),
    ]

    def excel_yaz(yol):
        with pd.ExcelWriter(yol, engine="openpyxl") as xw:
            for ad, d, ix in sayfalar:
                d.to_excel(xw, sheet_name=ad, index=ix)
            for ws in xw.book.worksheets:
                for c in ws.columns:
                    w = max(len(str(x.value)) for x in c if x.value is not None)
                    ws.column_dimensions[c[0].column_letter].width = \
                        min(max(w + 2, 10), 34)
                ws.freeze_panes = "A2"

    # Hedef dosya Excel'de açıksa kilitlidir; hesabı kaybetmemek için yedek ada yaz
    px = os.path.join(kd, "hezil_alternatifler.xlsx")
    try:
        excel_yaz(px)
    except PermissionError:
        px = os.path.join(kd, "hezil_alternatifler_"
                              f"{time.strftime('%Y%m%d_%H%M%S')}.xlsx")
        print(f"\n!! hezil_alternatifler.xlsx kilitli (Excel'de açık olabilir).")
        print(f"!! Sonuçlar şu dosyaya yazıldı: {os.path.basename(px)}")
        excel_yaz(px)

    def png_yaz(ad, ciz):
        yol = os.path.join(kd, ad)
        try:
            ciz(yol)
            return yol
        except PermissionError:
            yol = os.path.join(kd, ad.replace(
                ".png", f"_{time.strftime('%Y%m%d_%H%M%S')}.png"))
            ciz(yol)
            return yol
        except Exception as e:
            return f"(grafik oluşturulamadı: {e})"

    pg = png_yaz("hezil_alternatifler.png", lambda y: grafikler(t, y))
    pe = png_yaz("hezil_ekonomi.png", lambda y: ekonomi_grafikleri(t, ptf_ort, y))
    pb = png_yaz("hezil_pik_vs_bant.png",
                 lambda y: pik_bant_grafikleri(t, t_bant, ptf_ort, y))
    p4 = png_yaz("hezil_4senaryo.png", lambda y: dort_senaryo_grafikleri(yk, y))

    print("\nÇIKTI DOSYALARI")
    for p in (px, p4, pg, pe, pb):
        print(f"   {p}")
    print("=" * 96)
    return t


if __name__ == "__main__":
    main()
