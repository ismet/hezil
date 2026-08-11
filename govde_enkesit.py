# -*- coding: utf-8 -*-
"""
================================================================================
HEZİL BARAJI — ŞEMATİK RCC GÖVDE EN KESİTİ (ölçekli)
================================================================================

Seçilen konfigürasyon için gövde en kesitini ÖLÇEKLİ olarak çizer ve su alma
yapısı taban kotunu VORTEKS BATIKLIĞI kriterlerinden hesaplar.

GÖSTERİLEN KOTLAR
-----------------
  · NSS (normal su seviyesi)            — 755.00 m
  · RATED (anma) su seviyeleri          — pik ve bant işletme için ayrı ayrı
  · Ortalama su seviyesi                — 36 yıllık işletme simülasyonundan
  · Minimum işletme su seviyesi         — seçilen konfigürasyondan
  · Su alma yapısı taban kotu           — vorteks batıklığından hesaplanır
  · Talveg (temel) kotu                 — 650.00 m

VORTEKS BATIKLIĞI
-----------------
Hava emen girdap (vorteks) oluşmaması için su alma ağzının MİNİMUM işletme
seviyesinde yeterince batık olması gerekir. İki yaygın kriter hesaplanıp
BÜYÜK olanı esas alınır:

  Gordon (1970)  :  S = c · V · √D          c = 0.55 (asimetrik yaklaşım)
  Knauss (1987)  :  S = D · (1 + 2.3·Fr)    Fr = V / √(g·D)

  S : su yüzü ile ağız ÜST kotu arasındaki batıklık [m]
  D : ağız yüksekliği [m] ·  V : ağızdaki hız [m/s]

  Taban kotu = min. işletme kotu − S − D

GÖVDE GEOMETRİSİ
----------------
  Menba şevi 1:0.20 (D:Y) · mansap şevi 1:0.70 · kret genişliği ve hava payı
  aşağıdaki sabitlerden. Bunlar ÖN TASARIM kabulüdür; stabilite, taşkın
  kabartması ve dalga tırmanması hesapları ayrıca yapılmalıdır.

KULLANIM
--------
    python govde_enkesit.py                    → S1 optimumu
    python govde_enkesit.py --senaryo S4       → YEKDEM optimumu
    python govde_enkesit.py --konfig 4.4 60 5.0 720

ÇIKTI : hezil_govde_enkesit_<konfig>.png
================================================================================
"""

import os
import sys
import glob
import argparse
import numpy as np
import pandas as pd

import optimzasyon as opt
import alternatifler as A
from imalatci_paketi import konfig_kur

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KD = os.path.dirname(os.path.abspath(__file__))

# ---- GÖVDE GEOMETRİSİ (ön tasarım kabulleri) --------------------------------
TALVEG        = 650.0     # temel / talveg kotu                              [m]
MENBA_SEV     = 0.20      # menba şevi  1 : 0.20  (düşey : yatay)
MANSAP_SEV    = 0.70      # mansap şevi 1 : 0.70
KRET_GENISLIK = 6.0       # kret genişliği                                   [m]
HAVA_PAYI     = 3.0       # NSS üzeri hava payı (KABUL — taşkın kabartması ve
                          # dalga tırmanması hesabı YAPILMADI)               [m]

# ---- SU ALMA YAPISI ----------------------------------------------------------
# Ağızdaki hız, yük kaybı modelindeki "giriş yapısı" hız yükü (0.30 m) ile
# tutarlı seçilmiştir:  V = √(2·g·0.30) ≈ 2.43 m/s
GIRIS_HIZ_YUKU = 0.30     # [m]
AGIZ_ORAN      = 1.25     # ağız genişliği / yüksekliği (B/D)
GORDON_C       = 0.55     # asimetrik yaklaşım akımı (simetrikte 0.40)


def vorteks_batiklik(Q, min_kot):
    """Su alma ağzı boyutları ve vorteks batıklığı."""
    V = np.sqrt(2.0 * opt.G * GIRIS_HIZ_YUKU)
    A_agiz = Q / V
    D = np.sqrt(A_agiz / AGIZ_ORAN)          # ağız yüksekliği
    B = AGIZ_ORAN * D                        # ağız genişliği
    Fr = V / np.sqrt(opt.G * D)
    S_gordon = GORDON_C * V * np.sqrt(D)
    S_knauss = D * (1.0 + 2.3 * Fr)
    S = max(S_gordon, S_knauss)
    return {"V": V, "A": A_agiz, "D": D, "B": B, "Fr": Fr,
            "S_gordon": S_gordon, "S_knauss": S_knauss, "S": S,
            "belirleyen": "Knauss" if S_knauss >= S_gordon else "Gordon",
            "agiz_ust": min_kot - S,
            "taban": min_kot - S - D}


def govde_koordinat(kret_kot):
    """Gövde poligonu (menba tepe noktası orijin)."""
    H = kret_kot - TALVEG
    x_mu, x_md = 0.0, KRET_GENISLIK                      # kret menba / mansap
    x_tu = -MENBA_SEV * H                                # temel menba
    x_td = KRET_GENISLIK + MANSAP_SEV * H                # temel mansap
    return {"H": H, "x_kret_m": x_mu, "x_kret_d": x_md,
            "x_taban_m": x_tu, "x_taban_d": x_td,
            "taban_genislik": x_td - x_tu,
            "poligon": [(x_tu, TALVEG), (x_mu, kret_kot),
                        (x_md, kret_kot), (x_td, TALVEG)]}


def menba_x(kot, G, kret_kot):
    """Verilen kotta menba yüzünün x koordinatı."""
    return -MENBA_SEV * (kret_kot - kot)


def ciz(K, G, vx, kotlar, yol):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon, Rectangle

    fig = plt.figure(figsize=(17, 10.5))
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 0.36], wspace=0.02)
    ax = fig.add_subplot(gs[0, 0])
    bilgi = fig.add_subplot(gs[0, 1]); bilgi.axis("off")

    kret = K["kret"]
    x0, x1 = G["x_taban_m"] - 74, G["x_taban_d"] + 20
    y0, y1 = TALVEG - 16, kret + 12

    # --- rezervuar suyu ------------------------------------------------------
    nss = kotlar["NSS"][0]
    ax.fill_between([x0, menba_x(nss, G, kret)], TALVEG - 16, nss,
                    color="#9ec9f0", alpha=.55, zorder=1)
    ax.plot([x0, menba_x(nss, G, kret)], [nss, nss], color="#0969da", lw=2,
            zorder=4)

    # --- temel kayası --------------------------------------------------------
    ax.fill_between([x0, x1], y0, TALVEG, color="#c9b79c", zorder=2)
    ax.add_patch(Rectangle((x0, y0), x1 - x0, TALVEG - y0, facecolor="none",
                           edgecolor="#8a7861", hatch="///", lw=0, zorder=2))
    ax.plot([x0, x1], [TALVEG, TALVEG], color="#6b5c48", lw=1.6, zorder=3)

    # --- gövde ---------------------------------------------------------------
    ax.add_patch(Polygon(G["poligon"], closed=True, facecolor="#b9bfc6",
                         edgecolor="#2b3137", lw=2.0, zorder=5))
    # RCC tabaka çizgileri (her 3 m)
    for z in np.arange(TALVEG + 3, kret, 3.0):
        xa = menba_x(z, G, kret)
        xb = KRET_GENISLIK + MANSAP_SEV * (kret - z)
        ax.plot([xa, xb], [z, z], color="#9aa2ab", lw=.45, zorder=6)
    ax.text((G["x_taban_m"] + G["x_taban_d"]) / 2 + 8, TALVEG + G["H"] * .33,
            "RCC\nGÖVDE", ha="center", va="center", fontsize=15,
            fontweight="bold", color="#2b3137", zorder=7)

    # --- su alma yapısı ------------------------------------------------------
    taban, ust = vx["taban"], vx["agiz_ust"]
    xm_t = menba_x(taban, G, kret)
    D_ag = vx["D"]
    # ağız (menba yüzünde açıklık)
    ax.add_patch(Rectangle((xm_t, taban), 7.0, D_ag, facecolor="#ffffff",
                           edgecolor="#0f4c81", lw=1.8, zorder=8))
    # ızgara
    for xx in np.linspace(xm_t - 2.6, xm_t - 0.4, 7):
        ax.plot([xx, xx], [taban - .5, ust + .5], color="#0f4c81", lw=1.2,
                zorder=8)
    ax.plot([xm_t - 3.0, xm_t - 3.0], [taban - .8, ust + .8], color="#0f4c81",
            lw=2, zorder=8)
    ax.text(xm_t - 6.5, (taban + ust) / 2, "ızgara", fontsize=9, ha="right",
            va="center", color="#0f4c81", rotation=90)
    # tünele geçiş
    ax.annotate("", xy=(G["x_taban_d"] - 4, taban + D_ag / 2),
                xytext=(xm_t + 7, taban + D_ag / 2),
                arrowprops=dict(arrowstyle="-|>", lw=2.2, color="#0f4c81"),
                zorder=9)
    ax.text((xm_t + G["x_taban_d"]) / 2 + 6, taban + D_ag / 2 + 4.5,
            f"enerji tüneli  D={K['dt']:.1f} m", fontsize=10.5,
            color="#0f4c81", ha="center", fontweight="bold", zorder=10,
            bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#0f4c81",
                      alpha=.9))

    # --- kot çizgileri -------------------------------------------------------
    # Etiketler birbirine çok yakın kotlarda üst üste bineceği için önce
    # yerleri ayrıştırılır, sonra gerçek kota kılavuz çizgiyle bağlanır.
    sirali = sorted(kotlar.items(), key=lambda kv: kv[1][0])
    dy_min = (y1 - y0) * 0.038
    ye = [kv[1][0] for kv in sirali]
    for _ in range(60):                       # yinelemeli ayrıştırma
        degisti = False
        for i in range(1, len(ye)):
            if ye[i] - ye[i - 1] < dy_min:
                orta = (ye[i] + ye[i - 1]) / 2
                ye[i - 1], ye[i] = orta - dy_min / 2, orta + dy_min / 2
                degisti = True
        if not degisti:
            break
    x_et = x0 + 2.0
    for (ad, (kot, renk, stil)), yy in zip(sirali, ye):
        xs = menba_x(kot, G, kret) if kot <= kret else G["x_kret_m"]
        ax.plot([x_et + 26, xs], [kot, kot], color=renk, lw=1.6, ls=stil,
                zorder=4)
        # etiket → gerçek kot kılavuzu
        ax.plot([x_et + 24, x_et + 26], [yy, kot], color=renk, lw=.9,
                ls="-", alpha=.75, zorder=5)
        ax.plot(x_et + 26, kot, "o", color=renk, ms=4.5, zorder=5)
        ax.text(x_et, yy, f"{ad}  {kot:.2f} m", fontsize=9.5, color=renk,
                fontweight="bold", va="center", ha="left", zorder=6)

    # --- vorteks batıklığı ölçüsü -------------------------------------------
    xv = menba_x(kotlar["Min. işletme"][0], G, kret) - 17
    ax.annotate("", xy=(xv, kotlar["Min. işletme"][0]), xytext=(xv, ust),
                arrowprops=dict(arrowstyle="<->", lw=1.8, color="#9a6700"))
    ax.text(xv - 1.5, (kotlar["Min. işletme"][0] + ust) / 2,
            f"vorteks batıklığı\nS = {vx['S']:.2f} m", fontsize=10,
            color="#9a6700", ha="right", va="center", fontweight="bold")
    ax.annotate("", xy=(xv, ust), xytext=(xv, taban),
                arrowprops=dict(arrowstyle="<->", lw=1.8, color="#0f4c81"))
    ax.text(xv - 1.5, (ust + taban) / 2, f"ağız\nD = {D_ag:.2f} m", fontsize=10,
            color="#0f4c81", ha="right", va="center", fontweight="bold")
    ax.plot([xv, xm_t], [ust, ust], color="#9a6700", lw=.9, ls=":")
    ax.plot([xv, xm_t], [taban, taban], color="#0f4c81", lw=.9, ls=":")

    # --- gövde ölçüleri ------------------------------------------------------
    yk = kret + 5
    ax.annotate("", xy=(G["x_kret_m"], yk), xytext=(G["x_kret_d"], yk),
                arrowprops=dict(arrowstyle="<->", lw=1.4, color="#2b3137"))
    ax.text(KRET_GENISLIK / 2, yk + 1.0, f"kret {KRET_GENISLIK:.1f} m",
            fontsize=9, ha="center")
    yt = TALVEG - 7
    ax.annotate("", xy=(G["x_taban_m"], yt), xytext=(G["x_taban_d"], yt),
                arrowprops=dict(arrowstyle="<->", lw=1.4, color="#2b3137"))
    ax.text((G["x_taban_m"] + G["x_taban_d"]) / 2, yt - 3.5,
            f"taban genişliği {G['taban_genislik']:.1f} m", fontsize=10,
            ha="center", fontweight="bold")
    xh = G["x_taban_d"] + 10
    ax.annotate("", xy=(xh, TALVEG), xytext=(xh, kret),
                arrowprops=dict(arrowstyle="<->", lw=1.4, color="#2b3137"))
    ax.text(xh - 2.0, (TALVEG + kret) / 2,
            f"gövde yüksekliği {G['H']:.1f} m", fontsize=10.5, va="center",
            ha="center", rotation=90, fontweight="bold", zorder=9,
            bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#2b3137",
                      alpha=.85))

    # şev üçgenleri (etiketler gövde yüzünden uzağa yerleştirilir)
    zc = TALVEG + G["H"] * .62
    xa = menba_x(zc, G, kret)
    ax.plot([xa, xa, xa - MENBA_SEV * 16, xa], [zc, zc - 16, zc - 16, zc],
            color="#d1242f", lw=1.6, zorder=9)
    ax.text(xa - MENBA_SEV * 16 - 2.5, zc - 8, f"MENBA\n1 : {MENBA_SEV:.2f}",
            fontsize=10.5, color="#d1242f", ha="right", va="center",
            fontweight="bold", zorder=9,
            bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#d1242f",
                      alpha=.9))
    zc2 = TALVEG + G["H"] * .38
    xb = KRET_GENISLIK + MANSAP_SEV * (kret - zc2)
    ax.plot([xb, xb, xb + MANSAP_SEV * 18, xb], [zc2, zc2 - 18, zc2 - 18, zc2],
            color="#d1242f", lw=1.6, zorder=9)
    ax.text(xb + MANSAP_SEV * 18 + 2.5, zc2 - 9,
            f"MANSAP\n1 : {MANSAP_SEV:.2f}", fontsize=10.5, color="#d1242f",
            ha="left", va="center", fontweight="bold", zorder=9,
            bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#d1242f",
                      alpha=.9))

    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xlabel("Yatay mesafe [m]", fontsize=11)
    ax.set_ylabel("Kot [m]", fontsize=11)
    ax.grid(alpha=.22, ls=":")
    ax.set_title("HEZİL BARAJI — ŞEMATİK RCC GÖVDE EN KESİTİ  (ölçekli)",
                 fontsize=14, fontweight="bold", pad=12)

    # --- bilgi paneli --------------------------------------------------------
    L = [
        ("KONFİGÜRASYON", "", True),
        ("Senaryo / işletme", K["etiket"], False),
        ("Tünel çapı", f"{K['dt']:.1f} m", False),
        ("Tasarım debisi", f"{K['q']:.1f} m³/s", False),
        ("Kurulu güç", f"{K['P']:.2f} MW", False),
        ("", "", False),
        ("SU SEVİYELERİ", "", True),
    ]
    for ad, (kot, _, _) in kotlar.items():
        L.append((ad, f"{kot:.2f} m", False))
    L += [
        ("", "", False),
        ("SU ALMA YAPISI", "", True),
        ("Ağızdaki hız  V", f"{vx['V']:.2f} m/s", False),
        ("Ağız alanı", f"{vx['A']:.2f} m²", False),
        ("Ağız yüksekliği  D", f"{vx['D']:.2f} m", False),
        ("Ağız genişliği  B", f"{vx['B']:.2f} m", False),
        ("Froude sayısı  Fr", f"{vx['Fr']:.3f}", False),
        ("Gordon batıklığı", f"{vx['S_gordon']:.2f} m", False),
        ("Knauss batıklığı", f"{vx['S_knauss']:.2f} m", False),
        ("BELİRLEYEN  S", f"{vx['S']:.2f} m  ({vx['belirleyen']})", False),
        ("Ağız üst kotu", f"{vx['agiz_ust']:.2f} m", False),
        ("TABAN KOTU", f"{vx['taban']:.2f} m", False),
        ("Talveg üzeri", f"{vx['taban'] - TALVEG:.2f} m", False),
        ("", "", False),
        ("GÖVDE", "", True),
        ("Kret kotu", f"{kret:.2f} m", False),
        ("Talveg kotu", f"{TALVEG:.2f} m", False),
        ("Gövde yüksekliği", f"{G['H']:.2f} m", False),
        ("Taban genişliği", f"{G['taban_genislik']:.2f} m", False),
        ("Taban / yükseklik", f"{G['taban_genislik']/G['H']:.3f}", False),
        ("Menba şevi", f"1 : {MENBA_SEV:.2f}", False),
        ("Mansap şevi", f"1 : {MANSAP_SEV:.2f}", False),
        ("Kret genişliği", f"{KRET_GENISLIK:.1f} m", False),
        ("Gövde kesit alanı", f"{K['alan']:.0f} m²", False),
    ]
    y = 0.985
    for ad, deg, bas in L:
        if bas:
            bilgi.text(0.02, y, ad, fontsize=10.5, fontweight="bold",
                       color="#0969da", transform=bilgi.transAxes)
            y -= 0.026
        elif ad:
            bilgi.text(0.03, y, ad, fontsize=9.5, color="#444",
                       transform=bilgi.transAxes)
            bilgi.text(0.99, y, deg, fontsize=9.5, ha="right",
                       fontweight="bold", transform=bilgi.transAxes)
            y -= 0.0235
        else:
            y -= 0.013
    bilgi.text(0.02, y - 0.01,
               "KABULLER / EKSİKLER\n"
               f"· Hava payı {HAVA_PAYI:.1f} m KABUL — taşkın kabartması ve\n"
               "  dalga tırmanması hesabı yapılmadı\n"
               "· Kret genişliği ön tasarım değeri\n"
               "· Stabilite (kayma, devrilme, gerilme) hesabı yapılmadı\n"
               "· Rusubat kotu bilinmiyor; taban kotu yalnız vorteks\n"
               "  kriterinden belirlendi\n"
               "· Enjeksiyon perdesi, drenaj, galeri gösterilmemiştir\n"
               "· Kuyruk suyu (574 m) mansapta ~4.6 km ötede olduğundan\n"
               "  bu kesitte yer almaz",
               fontsize=8.2, va="top", color="#9a6700",
               transform=bilgi.transAxes,
               bbox=dict(boxstyle="round,pad=0.5", fc="#fff8e6", ec="#d4a72c"))

    fig.subplots_adjust(left=.055, right=.985, top=.94, bottom=.07)
    fig.savefig(yol, dpi=130)
    plt.close(fig)


def enkesit_uret(dt, q, vc, km, etiket="seçilen", ana_amac="gelir",
                 fse=None, yaz=print):
    """Bir konfigürasyon için ölçekli gövde en kesitini üretir.
    Döner: {"png": dosya_adı, "kotlar": {…}, "vorteks": {…}, "govde": {…}}"""
    if fse is None:
        ptf, _ = opt.ptf_oku(os.path.join(KD, opt.PTF_DOSYASI))
        fse = opt.FiyatSureEgrisi(ptf)

    # iki işletmenin anma ve ortalama seviyeleri
    anma, ortalama = {}, {}
    for amac in ("gelir", "enerji"):
        konfig_kur(dt, q, vc, km, amac)
        V, Qg, pq, pm, _ = opt.dp_coz(opt.AKIMLAR, fse, ilerleme=False)
        df = opt.ileri_simulasyon(V, Qg, pq, pm, opt.AKIMLAR, fse)
        hac = df["Turbin_m3s"] * df["AyNo"].map(
            {i + 1: opt.AY_GUN[opt.TAKVIM_AYI[i]] * 86400.0 for i in range(12)})
        anma[amac] = float(np.average(df["Kot_ort"], weights=hac))
        ortalama[amac] = float(df["Kot_son"].mean())

    kret = opt.KOT_MAKS + HAVA_PAYI
    G = govde_koordinat(kret)
    vx = vorteks_batiklik(q, km)

    kotlar = {
        "Kret":             (kret, "#2b3137", "-"),
        "NSS":              (opt.KOT_MAKS, "#d1242f", "-"),
        "RATED (bant)":     (anma["enerji"], "#1a7f37", "-."),
        "RATED (pik)":      (anma["gelir"], "#953800", "-."),
        "Ortalama su sev.": (ortalama[ana_amac], "#8250df", "--"),
        "Min. işletme":     (km, "#0969da", "-"),
        "Su alma tabanı":   (vx["taban"], "#0f4c81", ":"),
        "Talveg":           (TALVEG, "#6b5c48", "-"),
    }
    alan = 0.5 * (KRET_GENISLIK + G["taban_genislik"]) * G["H"]
    K = {"dt": dt, "q": q, "vc": vc, "km": km, "kret": kret,
         "etiket": etiket, "P": opt.P_KURULU, "alan": alan}

    yaz(f"   taban kotu {vx['taban']:.2f} m · batıklık {vx['S']:.2f} m "
        f"({vx['belirleyen']}) · gövde {G['H']:.1f} m")

    et = f"D{dt:.1f}_Q{q:.1f}_vc{vc:.1f}_kot{km:.0f}"
    ad = f"hezil_govde_enkesit_{et}.png"
    ciz(K, G, vx, kotlar, os.path.join(KD, ad))

    return {"png": ad,
            "kotlar": {a: round(v[0], 2) for a, v in kotlar.items()},
            "vorteks": {k: (round(v, 3) if isinstance(v, float) else v)
                        for k, v in vx.items()},
            "govde": {"kret": round(kret, 2), "talveg": TALVEG,
                      "yukseklik": round(G["H"], 2),
                      "taban_genislik": round(G["taban_genislik"], 2),
                      "taban_yukseklik": round(G["taban_genislik"] / G["H"], 3),
                      "alan": round(alan), "menba_sev": MENBA_SEV,
                      "mansap_sev": MANSAP_SEV, "kret_genislik": KRET_GENISLIK,
                      "hava_payi": HAVA_PAYI}}


def main():
    ap = argparse.ArgumentParser(description="Şematik RCC gövde en kesiti")
    ap.add_argument("--senaryo", default="S1", choices=["S1", "S2", "S3", "S4"])
    ap.add_argument("--konfig", nargs=4, type=float, metavar=("D", "Q", "VC", "KOT"))
    ar = ap.parse_args()

    ad = sorted(glob.glob(os.path.join(KD, "hezil_alternatifler*.xlsx")),
                key=os.path.getmtime)
    if not ad:
        raise SystemExit("Önce alternatifler.py çalıştırılmalı")
    t = pd.read_excel(ad[-1], sheet_name="Tüm Senaryolar")

    if ar.konfig:
        dt, q, vc, km = ar.konfig
        etiket = "elle seçilen"
    else:
        s = t.loc[t[f"{ar.senaryo}_net_MEUR"].idxmax()]
        dt, q = float(s["Tünel_D_m"]), float(s["Q_tasarım_m3/s"])
        vc, km = float(s["Cebri_hızı_m/s"]), float(s["Min_kot_m"])
        etiket = f"{ar.senaryo} optimumu"

    print("=" * 88)
    print("HEZİL BARAJI — ŞEMATİK RCC GÖVDE EN KESİTİ")
    print("=" * 88)
    print(f"Konfigürasyon : D_tünel {dt:.1f} m · Q {q:.1f} m³/s · min kot {km:.0f} m"
          f"  ({etiket})")

    r = enkesit_uret(dt, q, vc, km, etiket,
                     "gelir" if ar.senaryo == "S1" else "enerji")
    vx, gv = r["vorteks"], r["govde"]

    print(f"\nSU SEVİYELERİ")
    for a_, k_ in r["kotlar"].items():
        print(f"   {a_:<20}{k_:9.2f} m")
    print(f"\nSU ALMA YAPISI — VORTEKS BATIKLIĞI")
    print(f"   ağızdaki hız V      : {vx['V']:8.2f} m/s")
    print(f"   ağız  B × D         : {vx['B']:8.2f} × {vx['D']:.2f} m "
          f"(alan {vx['A']:.2f} m²)")
    print(f"   Froude sayısı       : {vx['Fr']:8.3f}")
    print(f"   Gordon              : {vx['S_gordon']:8.2f} m")
    print(f"   Knauss              : {vx['S_knauss']:8.2f} m")
    print(f"   BELİRLEYEN          : {vx['S']:8.2f} m  ({vx['belirleyen']})")
    print(f"   TABAN KOTU          : {vx['taban']:8.2f} m  "
          f"(talvegin {vx['taban']-TALVEG:.2f} m üstünde)")
    print(f"\nGÖVDE")
    print(f"   kret kotu           : {gv['kret']:8.2f} m")
    print(f"   gövde yüksekliği    : {gv['yukseklik']:8.2f} m")
    print(f"   taban genişliği     : {gv['taban_genislik']:8.2f} m  "
          f"(taban/yükseklik {gv['taban_yukseklik']:.3f})")
    print(f"   kesit alanı         : {gv['alan']:8.0f} m²")
    print(f"\nÇIKTI\n   {os.path.join(KD, r['png'])}")
    print("=" * 88)


if __name__ == "__main__":
    main()
