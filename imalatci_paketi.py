# -*- coding: utf-8 -*-
"""
================================================================================
HEZİL HES — TÜRBİN İMALATÇISI VERİ PAKETİ
================================================================================

Seçilen bir konfigürasyon için türbin imalatçısına verilecek grafik ve tabloları
üretir. Mevcut panoya (hezil_dashboard.html) DOKUNMAZ; ayrı çıktı dosyaları
oluşturur.

ÜRETİLEN 9 GRAFİK
-----------------
  1  İşletme zarfı (Q–H alanı) — dış zarf + eş-güç eğrileri + köşe noktaları
  2  Net düşü süreklilik eğrisi (çalışma saatine göre)
  3  Türbinlenen debi süreklilik eğrisi
  4  Enerjinin yük bandına dağılımı (verim garantisi bu eğriye göre pazarlanır)
  5  Ünite kombinasyonu + başlatma-durdurma çevrim istatistiği
  6  Güç süreklilik eğrisi
  7  Rezervuar kotu süreklilik eğrisi
  8  Yük kaybı – debi eğrisi (kalem dökümüyle)
  9  Tipik yıl aylık işletme programı

BAŞLATMA-DURDURMA
-----------------
Puant işletmede santral ayın en pahalı saatlerinde çalışır. Bu saatlerin
gerçek PTF serisindeki gün/blok dağılımından yıllık başlatma-durdurma sayısı
ve blok süresi dağılımı çıkarılır — imalatçının yatak, salmastra, ayar kanadı
ve regülatör seçimini doğrudan etkileyen veridir.

KULLANIM
--------
    python imalatci_paketi.py                     → S1 optimumu
    python imalatci_paketi.py --senaryo S4        → YEKDEM optimumu
    python imalatci_paketi.py --konfig 4.4 60 5.0 720   → elle (D, Q, v_c, kot)
    python imalatci_paketi.py --amac enerji       → bant işletme

ÇIKTI : hezil_imalatci_paketi.png  ·  hezil_imalatci_paketi.xlsx
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KD = os.path.dirname(os.path.abspath(__file__))


# ==============================================================================
# YARDIMCILAR
# ==============================================================================
def sureklilik(deger, agirlik, n=200):
    """Ağırlıklı süreklilik eğrisi → (aşılma yüzdesi, değer)."""
    d = np.asarray(deger, float)
    w = np.asarray(agirlik, float)
    m = w > 0
    d, w = d[m], w[m]
    if not len(d):
        return np.array([]), np.array([])
    i = np.argsort(d)[::-1]
    d, w = d[i], w[i]
    kum = np.cumsum(w) / w.sum() * 100.0
    return kum, d


def baslatma_sayisi(df, ptf):
    """Aylık çalışma saatlerinden yıllık başlatma-durdurma sayısını kestir.
    Puant işletmede santral ayın EN PAHALI N saatinde çalışır; bu saatlerin
    takvimdeki ardışık blokları başlatma sayısını verir."""
    sat = []
    for ay in range(1, 13):
        s = df.loc[df["TakvimAy"] == ay, "Calisma_saat"]
        N = int(round(float(s.mean())))
        p = ptf[ptf.index.month == ay]
        if N <= 0 or not len(p):
            sat.append({"TakvimAy": ay, "Saat": 0, "Gün": 0, "Başlatma": 0,
                        "Blok_süresi_h": 0.0})
            continue
        N = min(N, len(p))
        esik = np.sort(p.values)[::-1][N - 1]
        c = (p.values >= esik)
        gun = len(set(p.index[c].date))
        blok = int(np.sum(np.diff(np.concatenate([[0], c.astype(int)])) == 1))
        sat.append({"TakvimAy": ay, "Saat": N, "Gün": gun, "Başlatma": blok,
                    "Blok_süresi_h": round(N / max(blok, 1), 1)})
    return pd.DataFrame(sat)


def konfig_kur(dt, q, vc, km, amac):
    D_c = np.sqrt(4.0 * q / (np.pi * vc))
    opt.TUNEL_D, opt.TUNEL_L = dt, A.TUNEL_UZUNLUK
    opt.CEBRI_D, opt.CEBRI_L = D_c, A.CEBRI_UZUNLUK
    opt.KOL_D, opt.KOL_L = A.KOL_CAP_ORANI * D_c, A.KOL_UZUNLUK
    opt.Q_TASARIM, opt.KOT_MIN, opt.BASLANGIC_KOTU = q, km, km
    opt.AMAC = amac
    opt.yeniden_kur()
    return D_c


# ==============================================================================
# GRAFİKLER
# ==============================================================================
def grafikler(df, ptf, bd, K, yol):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    u = df[df["Calisma_saat"] > 0].copy()
    w = u["Calisma_saat"].to_numpy(float)
    qop = u["Q_isletme_m3s"].to_numpy(float)
    hn = u["Net_Dusu_m"].to_numpy(float)
    gu = u["Guc_MW"].to_numpy(float)

    fig, ax = plt.subplots(3, 3, figsize=(19, 15))
    fig.suptitle(
        f"HEZİL HES — TÜRBİN İMALATÇISI VERİ PAKETİ\n"
        f"Tünel D={K['dt']:.1f} m · Q_tasarım={K['q']:.1f} m³/s · "
        f"cebri boru D={K['dc']:.2f} m · min. su kotu {K['km']:.0f} m · "
        f"{K['amac_ad']} işletme · {K['unite']} ünite × "
        f"{K['q']/K['unite']:.1f} m³/s",
        fontsize=14, fontweight="bold")

    # --- 1) İşletme zarfı ----------------------------------------------------
    a = ax[0, 0]
    qq = np.linspace(qop.min() * .9, K["q"] * 1.05, 60)
    hh = np.linspace(hn.min() * .97, hn.max() * 1.03, 60)
    QQ, HH = np.meshgrid(qq, hh)
    eta = np.array([[float(opt.turbin_verimi(min(q_ / (K["q"] / K["unite"]), 1.0)))
                     for q_ in qq]] * len(hh))
    PP = opt.G * QQ * HH * eta * opt.ETA_JENERATOR * opt.ETA_TRAFO / 1000.0
    cs = a.contour(QQ, HH, PP, levels=8, colors="#8b949e", linewidths=.8)
    a.clabel(cs, inline=True, fontsize=7, fmt="%.0f MW")
    a.scatter(qop, hn, s=6 + 60 * w / w.max(), c="#0969da", alpha=.35,
              edgecolors="none", zorder=3)
    # dış zarf (convex hull)
    try:
        from scipy.spatial import ConvexHull
        pts = np.column_stack([qop, hn])
        h = ConvexHull(pts)
        z = np.append(h.vertices, h.vertices[0])
        a.plot(pts[z, 0], pts[z, 1], "-", color="#d1242f", lw=1.8, zorder=4,
               label="işletme zarfı")
    except Exception:
        pass
    for q_, h_, ad in [(qop.min(), hn.max(), "Q_min/H_maks"),
                       (qop.max(), hn.max(), "Q_maks/H_maks"),
                       (qop.min(), hn.min(), "Q_min/H_min"),
                       (qop.max(), hn.min(), "Q_maks/H_min")]:
        a.plot(q_, h_, "s", color="#d1242f", ms=6, zorder=5)
        a.annotate(f"{ad}\n{q_:.1f} m³/s · {h_:.1f} m", (q_, h_), fontsize=7,
                   ha="center", va="bottom" if h_ > hn.mean() else "top")
    a.axhline(K["rated_net"], color="#1a7f37", ls="--", lw=1.4,
              label=f"anma net düşü {K['rated_net']:.1f} m")
    a.set_title("1 · İŞLETME ZARFI — eş-güç eğrileriyle", fontweight="bold")
    a.set_xlabel("İşletme debisi [m³/s]"); a.set_ylabel("Net düşü [m]")
    a.legend(fontsize=8); a.grid(alpha=.25)

    # --- 2) Net düşü süreklilik ---------------------------------------------
    a = ax[0, 1]
    x, y = sureklilik(hn, w)
    a.plot(x, y, color="#0969da", lw=2)
    for pct, c in [(10, "#8b949e"), (50, "#1a7f37"), (90, "#8b949e")]:
        v = float(np.interp(pct, x, y))
        a.axvline(pct, color=c, ls=":", lw=1)
        a.annotate(f"%{pct} → {v:.1f} m", (pct, v), fontsize=8,
                   xytext=(4, 4), textcoords="offset points")
    a.axhline(K["rated_net"], color="#d1242f", ls="--", lw=1.2,
              label=f"anma {K['rated_net']:.1f} m")
    a.set_title("2 · NET DÜŞÜ SÜREKLİLİK EĞRİSİ", fontweight="bold")
    a.set_xlabel("Çalışma süresinin aşılma yüzdesi [%]")
    a.set_ylabel("Net düşü [m]"); a.legend(fontsize=8); a.grid(alpha=.3)

    # --- 3) Debi süreklilik --------------------------------------------------
    a = ax[0, 2]
    x, y = sureklilik(qop, w)
    a.plot(x, y, color="#2da44e", lw=2)
    a.axhline(K["q"], color="#d1242f", ls="--", lw=1.2, label="Q_tasarım")
    a.axhline(K["q"] / K["unite"], color="#8250df", ls="--", lw=1.2,
              label="1 ünite tam yük")
    a.axhline(K["q"] / K["unite"] * opt.UNITE_MIN_YUK, color="#9a6700",
              ls=":", lw=1.2, label="asgari sürekli debi")
    a.set_title("3 · TÜRBİNLENEN DEBİ SÜREKLİLİK EĞRİSİ", fontweight="bold")
    a.set_xlabel("Çalışma süresinin aşılma yüzdesi [%]")
    a.set_ylabel("İşletme debisi [m³/s]"); a.legend(fontsize=8); a.grid(alpha=.3)

    # --- 4) Enerjinin yük bandına dağılımı ----------------------------------
    a = ax[1, 0]
    yuk = (u["Q_isletme_m3s"] / (u["Calisan_Unite"].clip(lower=1)
                                 * K["q"] / K["unite"])).to_numpy(float)
    ban = np.round(yuk, 3)
    tab = pd.DataFrame({"yuk": ban, "E": u["Enerji_MWh"].to_numpy(float),
                        "h": w}).groupby("yuk").sum()
    tab["E%"] = tab["E"] / tab["E"].sum() * 100
    tab["h%"] = tab["h"] / tab["h"].sum() * 100
    xw = np.arange(len(tab)); bw = .38
    a.bar(xw - bw/2, tab["E%"], bw, color="#0969da", label="enerji payı")
    a.bar(xw + bw/2, tab["h%"], bw, color="#2da44e", label="çalışma süresi payı")
    for i, (e, h_) in enumerate(zip(tab["E%"], tab["h%"])):
        a.text(i - bw/2, e, f"{e:.0f}", ha="center", va="bottom", fontsize=8)
        a.text(i + bw/2, h_, f"{h_:.0f}", ha="center", va="bottom", fontsize=8)
    a.set_xticks(xw)
    a.set_xticklabels([f"%{v*100:.0f}" for v in tab.index], fontsize=9)
    a2 = a.twinx()
    a2.plot(xw, [float(opt.turbin_verimi(v))*100 for v in tab.index], "o-",
            color="#bf3989", lw=2, label="türbin verimi")
    a2.set_ylabel("Türbin verimi [%]", color="#bf3989")
    a.set_title("4 · ENERJİNİN YÜK BANDINA DAĞILIMI\n"
                "(ağırlıklı verim garantisi bu dağılıma göre tanımlanır)",
                fontweight="bold")
    a.set_xlabel("Ünite yük oranı"); a.set_ylabel("Pay [%]")
    a.legend(fontsize=8, loc="upper left"); a.grid(alpha=.3, axis="y")

    # --- 5) Ünite kombinasyonu + çevrim -------------------------------------
    a = ax[1, 1]
    ay = np.arange(1, 13)
    bl = bd.set_index("TakvimAy").reindex(ay).fillna(0)
    a.bar(ay, bl["Başlatma"], color="#d1242f", alpha=.75, label="başlatma sayısı")
    a2 = a.twinx()
    a2.plot(ay, bl["Blok_süresi_h"], "o-", color="#0969da", lw=2,
            label="ortalama blok süresi")
    a2.set_ylabel("Blok süresi [saat]", color="#0969da")
    a.set_xticks(ay); a.set_xticklabels(opt.AY_ADLARI[3:] + opt.AY_ADLARI[:3]
                                        if False else [str(m) for m in ay])
    a.set_title(f"5 · ÇEVRİM İSTATİSTİĞİ — yılda ~{bd['Başlatma'].sum():.0f} "
                f"başlatma-durdurma\n"
                f"(1 ünite ile {K['pay1u']:.0f}%, 2 ünite ile {100-K['pay1u']:.0f}%"
                f" of türbinlenen su)", fontweight="bold")
    a.set_xlabel("Takvim ayı"); a.set_ylabel("Başlatma sayısı [adet/ay]")
    a.legend(fontsize=8, loc="upper left"); a.grid(alpha=.3, axis="y")

    # --- 6) Güç süreklilik ---------------------------------------------------
    a = ax[1, 2]
    x, y = sureklilik(gu, w)
    a.plot(x, y, color="#953800", lw=2)
    a.axhline(K["P_kurulu"], color="#d1242f", ls="--", lw=1.2,
              label=f"kurulu güç {K['P_kurulu']:.1f} MW")
    a.set_title("6 · GÜÇ SÜREKLİLİK EĞRİSİ", fontweight="bold")
    a.set_xlabel("Çalışma süresinin aşılma yüzdesi [%]")
    a.set_ylabel("Güç [MW]"); a.legend(fontsize=8); a.grid(alpha=.3)

    # --- 7) Rezervuar kotu süreklilik ---------------------------------------
    a = ax[2, 0]
    x, y = sureklilik(df["Kot_son"].to_numpy(float),
                      np.ones(len(df)))
    a.plot(x, y, color="#8250df", lw=2)
    a.axhline(opt.KOT_MAKS, color="#d1242f", ls="--", lw=1.2, label="maks. kot")
    a.axhline(K["km"], color="#8250df", ls="--", lw=1.2, label="min. kot")
    a.axhline(K["rated_kot"], color="#1a7f37", ls="-.", lw=1.4,
              label=f"anma kotu {K['rated_kot']:.1f} m")
    a.set_title("7 · REZERVUAR KOTU SÜREKLİLİK EĞRİSİ\n"
                "(emme yüksekliği ve santral taban kotu kararı)",
                fontweight="bold")
    a.set_xlabel("Zamanın aşılma yüzdesi [%]")
    a.set_ylabel("Rezervuar kotu [m]"); a.legend(fontsize=8); a.grid(alpha=.3)

    # --- 8) Yük kaybı – debi -------------------------------------------------
    a = ax[2, 1]
    qs = np.linspace(K["q"] * .2, K["q"] * 1.02, 40)
    kalem = {}
    for q_ in qs:
        d = opt.yuk_kaybi_detay(q_)
        for k_, v_ in d.items():
            kalem.setdefault(k_, []).append(v_)
    a.stackplot(qs,
                kalem["Giriş yapısı (yerel)"], kalem["Tünel — sürtünme"],
                kalem["Tünel — yerel"], kalem["Cebri boru — sürtünme"],
                kalem["Cebri boru — yerel"], kalem["Kol — sürtünme"],
                kalem["Kol — yerel"],
                labels=["giriş yapısı", "tünel sürtünme", "tünel yerel",
                        "cebri sürtünme", "cebri yerel", "kol sürtünme",
                        "kol yerel"],
                colors=["#8b949e", "#0969da", "#54aeff", "#1a7f37", "#4ac26b",
                        "#953800", "#e0a86b"], alpha=.9)
    a.axvline(K["q"], color="#d1242f", ls="--", lw=1.2)
    a.set_title("8 · YÜK KAYBI – DEBİ (kalem dökümü)", fontweight="bold")
    a.set_xlabel("Toplam debi [m³/s]"); a.set_ylabel("Yük kaybı [m]")
    a.legend(fontsize=7, loc="upper left"); a.grid(alpha=.25)

    # --- 9) Tipik yıl aylık işletme -----------------------------------------
    a = ax[2, 2]
    g = df.groupby("AyNo").agg(
        gelen=("Gelen_m3s", "mean"), turbin=("Turbin_m3s", "mean"),
        savak=("Savak_m3s", "mean"), kot=("Kot_son", "mean"),
        saat=("Calisma_saat", "mean"))
    x = np.arange(1, 13)
    a.bar(x, g["turbin"], .6, color="#2da44e", label="türbinlenen")
    a.bar(x, g["savak"], .6, bottom=g["turbin"], color="#d1242f",
          label="savaklanan")
    a.plot(x, g["gelen"], "o-", color="#8b949e", lw=2, label="gelen akım")
    a2 = a.twinx()
    a2.plot(x, g["kot"], "s--", color="#0969da", lw=2, label="rezervuar kotu")
    a2.set_ylabel("Rezervuar kotu [m]", color="#0969da")
    a.set_xticks(x); a.set_xticklabels(opt.AY_ADLARI, rotation=45, fontsize=8)
    a.set_title("9 · TİPİK YIL AYLIK İŞLETME PROGRAMI", fontweight="bold")
    a.set_ylabel("Debi [m³/s]"); a.legend(fontsize=8, loc="upper left")
    a.grid(alpha=.3, axis="y")

    fig.tight_layout(rect=(0, 0, 1, 0.955))
    fig.savefig(yol, dpi=120)
    plt.close(fig)


# ==============================================================================
def paket_uret(dt, q, vc, km, amac, fse=None, etiket=None, yaz=print):
    """Bir konfigürasyon için imalatçı paketini üretir.
    Döner: {"png":…, "xlsx":…, "ozet":{…}} — dosya adları KD'ye görelidir."""
    amac_ad = "PİK (gelir maks.)" if amac == "gelir" else "BANT (enerji maks.)"

    if fse is None:
        ptf, kaynak = opt.ptf_oku(os.path.join(KD, opt.PTF_DOSYASI))
        fse = opt.FiyatSureEgrisi(ptf)
    else:
        ptf, kaynak = opt.ptf_oku(os.path.join(KD, opt.PTF_DOSYASI))

    D_c = konfig_kur(dt, q, vc, km, amac)
    V, Qg, pq, pm, _ = opt.dp_coz(opt.AKIMLAR, fse, ilerleme=False)
    df = opt.ileri_simulasyon(V, Qg, pq, pm, opt.AKIMLAR, fse)

    su_hac = df["Turbin_m3s"] * df["AyNo"].map(
        {i + 1: opt.AY_GUN[opt.TAKVIM_AYI[i]] * 86400.0 for i in range(12)})
    rk = float(np.average(df["Kot_ort"], weights=su_hac))
    rn = float(np.average(df["Net_Dusu_m"], weights=su_hac))
    m1 = (df["Calisan_Unite"] == 1) & (su_hac > 0)
    pay1 = float(su_hac[m1].sum() / su_hac.sum() * 100) if m1.any() else 0.0
    rn1 = (float(np.average(df.loc[m1, "Net_Dusu_m"], weights=su_hac[m1]))
           if m1.any() else 0.0)
    m2 = (df["Calisan_Unite"] == opt.UNITE_SAYISI) & (su_hac > 0)
    rn2 = (float(np.average(df.loc[m2, "Net_Dusu_m"], weights=su_hac[m2]))
           if m2.any() else 0.0)

    bd = baslatma_sayisi(df, ptf)
    yil = df.groupby("SuYili")["Enerji_MWh"].sum() / 1000.0

    K = {"dt": dt, "q": q, "vc": vc, "km": km, "dc": D_c,
         "unite": opt.UNITE_SAYISI, "amac_ad": amac_ad,
         "rated_kot": rk, "rated_net": rn, "pay1u": pay1,
         "P_kurulu": opt.P_KURULU}

    yaz(f"   anma kotu {rk:.2f} m · anma net düşü {rn:.2f} m "
        f"(1Ü {rn1:.2f} / 2Ü {rn2:.2f}) · {bd['Başlatma'].sum():.0f} başlatma/yıl")

    # ---- dosya adları: konfigürasyona özel, üzerine yazmasın --------------
    et = etiket or (f"D{dt:.1f}_Q{q:.1f}_vc{vc:.1f}_kot{km:.0f}_"
                    f"{'pik' if amac == 'gelir' else 'bant'}")
    pg_ad = f"hezil_imalatci_{et}.png"
    px_ad = f"hezil_imalatci_{et}.xlsx"
    pg, px = os.path.join(KD, pg_ad), os.path.join(KD, px_ad)

    grafikler(df, ptf, bd, K, pg)

    u = df[df["Calisma_saat"] > 0]
    w = u["Calisma_saat"].to_numpy(float)
    sur = {}
    for ad_, dz in [("Net düşü [m]", u["Net_Dusu_m"]),
                    ("İşletme debisi [m3/s]", u["Q_isletme_m3s"]),
                    ("Güç [MW]", u["Guc_MW"])]:
        x, y = sureklilik(dz.to_numpy(float), w)
        sur[ad_] = np.interp(np.arange(0, 101), x, y)
    xk, yk = sureklilik(df["Kot_son"].to_numpy(float), np.ones(len(df)))
    sur["Rezervuar kotu [m]"] = np.interp(np.arange(0, 101), xk, yk)
    sur_df = pd.DataFrame(sur, index=pd.Index(np.arange(0, 101),
                                              name="Aşılma [%]"))

    ozet = pd.DataFrame([
        ("Tünel çapı", dt, "m"), ("Tasarım debisi", q, "m³/s"),
        ("Cebri boru çapı", round(D_c, 3), "m"),
        ("Cebri boru hızı", vc, "m/s"), ("Minimum su kotu", km, "m"),
        ("Maksimum su kotu", opt.KOT_MAKS, "m"),
        ("Kuyruk suyu kotu (KABUL: sabit)", opt.KOT_KUYRUK, "m"),
        ("Ünite sayısı", opt.UNITE_SAYISI, "adet"),
        ("Ünite tasarım debisi", round(q / opt.UNITE_SAYISI, 2), "m³/s"),
        ("Kurulu güç", round(opt.P_KURULU, 2), "MW"),
        ("ANMA rezervuar kotu", round(rk, 2), "m"),
        ("ANMA brüt düşü", round(rk - opt.KOT_KUYRUK, 2), "m"),
        ("ANMA net düşü", round(rn, 2), "m"),
        ("ANMA net düşü — 1 ünite", round(rn1, 2), "m"),
        ("ANMA net düşü — 2 ünite", round(rn2, 2), "m"),
        ("Tek ünite işletmesinin su payı", round(pay1, 1), "%"),
        ("Maks. net düşü", round(float(u["Net_Dusu_m"].max()), 2), "m"),
        ("Min. net düşü", round(float(u["Net_Dusu_m"].min()), 2), "m"),
        ("Yük kaybı @Q_tasarım", round(float(opt.yuk_kaybi(q)), 2), "m"),
        ("Ortalama yıllık enerji", round(float(yil.mean()), 2), "GWh/yıl"),
        ("Yıllık çalışma süresi",
         round(float(df["Calisma_saat"].sum() / len(yil))), "h"),
        ("Başlatma-durdurma", int(bd["Başlatma"].sum()), "adet/yıl"),
        ("Ortalama blok süresi",
         round(bd["Saat"].sum() / max(bd["Başlatma"].sum(), 1), 1), "h"),
        ("Çalışılan gün", int(bd["Gün"].sum()), "gün/yıl"),
        ("İşletme biçimi", amac_ad, ""),
        ("Fiyat verisi", kaynak, ""),
        ("— EKSİK VERİLER —", "", ""),
        ("Kuyruk suyu anahtar eğrisi", "GEREKLİ — sabit kot kabul edildi", ""),
        ("Emme yüksekliği / σ_Thoma", "GEREKLİ", ""),
        ("Su darbesi / transient analizi",
         f"GEREKLİ — et kalınlığı {A.SU_DARBESI_FAKTORU} faktörüyle ön hesap", ""),
        ("Kaçak devir (runaway), GD²", "İMALATÇIDAN", ""),
    ], columns=["Büyüklük", "Değer", "Birim"])

    kayip = pd.DataFrame([{"Debi_m3s": round(q_, 1),
                           **{k_: round(v_, 3)
                              for k_, v_ in opt.yuk_kaybi_detay(q_).items()}}
                          for q_ in np.linspace(q * .2, q, 17)])

    def _yaz_excel(p):
        with pd.ExcelWriter(p, engine="openpyxl") as xw:
            ozet.to_excel(xw, sheet_name="Özet", index=False)
            sur_df.round(2).to_excel(xw, sheet_name="Süreklilik Eğrileri")
            bd.to_excel(xw, sheet_name="Çevrim İstatistiği", index=False)
            kayip.to_excel(xw, sheet_name="Yük Kaybı", index=False)
            u[["SuYili", "Ay", "Q_isletme_m3s", "Calisan_Unite", "Net_Dusu_m",
               "Brut_Dusu_m", "Yuk_Kaybi_m", "Guc_MW", "Calisma_saat",
               "Enerji_MWh", "Kot_ort"]].round(3).to_excel(
                   xw, sheet_name="İşletme Noktaları", index=False)
            df.round(3).to_excel(xw, sheet_name="Aylık İşletme", index=False)
            for ws in xw.book.worksheets:
                for c in ws.columns:
                    ln = max(len(str(x.value)) for x in c if x.value is not None)
                    ws.column_dimensions[c[0].column_letter].width = \
                        min(max(ln + 2, 10), 38)
                ws.freeze_panes = "A2"
    try:
        _yaz_excel(px)
    except PermissionError:
        import time as _t
        px_ad = px_ad.replace(".xlsx", f"_{_t.strftime('%H%M%S')}.xlsx")
        px = os.path.join(KD, px_ad)
        _yaz_excel(px)

    return {"png": pg_ad, "xlsx": px_ad, "ozet": {
        "P_kurulu": round(opt.P_KURULU, 2),
        "rated_kot": round(rk, 2), "rated_net": round(rn, 2),
        "rated_net_1u": round(rn1, 2), "rated_net_2u": round(rn2, 2),
        "pay1u": round(pay1, 1),
        "enerji": round(float(yil.mean()), 2),
        "calisma": round(float(df["Calisma_saat"].sum() / len(yil))),
        "baslatma": int(bd["Başlatma"].sum()),
        "blok_h": round(bd["Saat"].sum() / max(bd["Başlatma"].sum(), 1), 1),
        "gun": int(bd["Gün"].sum()),
        "amac_ad": amac_ad, "dc": round(D_c, 2)}}


def main():
    ap = argparse.ArgumentParser(description="Türbin imalatçısı veri paketi")
    ap.add_argument("--senaryo", default="S1", choices=["S1", "S2", "S3", "S4"])
    ap.add_argument("--konfig", nargs=4, type=float, metavar=("D", "Q", "VC", "KOT"))
    ap.add_argument("--amac", default=None, choices=["gelir", "enerji"])
    ar = ap.parse_args()

    ad = sorted(glob.glob(os.path.join(KD, "hezil_alternatifler*.xlsx")),
                key=os.path.getmtime)
    if not ad:
        raise SystemExit("Önce alternatifler.py çalıştırılmalı")
    t = pd.read_excel(ad[-1], sheet_name="Tüm Senaryolar")

    if ar.konfig:
        dt, q, vc, km = ar.konfig
    else:
        sat = t.loc[t[f"{ar.senaryo}_net_MEUR"].idxmax()]
        dt, q = float(sat["Tünel_D_m"]), float(sat["Q_tasarım_m3/s"])
        vc, km = float(sat["Cebri_hızı_m/s"]), float(sat["Min_kot_m"])

    amac = ar.amac or ("gelir" if ar.senaryo == "S1" else "enerji")

    print("=" * 92)
    print("HEZİL HES — TÜRBİN İMALATÇISI VERİ PAKETİ")
    print("=" * 92)
    print(f"Konfigürasyon : D_tünel {dt:.1f} m · Q {q:.1f} m³/s · "
          f"v_cebri {vc:.1f} m/s · min kot {km:.0f} m")
    r = paket_uret(dt, q, vc, km, amac)
    o = r["ozet"]
    print(f"\nANMA (RATED) İŞLETME NOKTASI — türbinlenen hacme ağırlıklı")
    print(f"   rezervuar kotu      : {o['rated_kot']:8.2f} m")
    print(f"   net düşü            : {o['rated_net']:8.2f} m")
    print(f"   · 1 ünite işletmede : {o['rated_net_1u']:8.2f} m  "
          f"(türbinlenen suyun %{o['pay1u']:.0f}'i)")
    print(f"   · 2 ünite işletmede : {o['rated_net_2u']:8.2f} m")
    print(f"   kurulu güç          : {o['P_kurulu']:8.2f} MW")
    print(f"\nÇEVRİM İSTATİSTİĞİ")
    print(f"   yıllık çalışma      : {o['calisma']:8.0f} h")
    print(f"   başlatma-durdurma   : {o['baslatma']:8.0f} /yıl")
    print(f"   ortalama blok       : {o['blok_h']:8.1f} h")
    print(f"   çalışılan gün       : {o['gun']:8.0f} /yıl")
    print(f"\nÇIKTI\n   {os.path.join(KD, r['png'])}\n   "
          f"{os.path.join(KD, r['xlsx'])}")
    print("=" * 92)


if __name__ == "__main__":
    main()
