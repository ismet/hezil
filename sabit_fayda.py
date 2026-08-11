# -*- coding: utf-8 -*-
"""
================================================================================
HEZİL HES — SABİT BİRİM FAYDA SENARYOSU
================================================================================

Enerjinin piyasada saatlik PTF'den değil, SABİT bir birim bedelden (alım
garantisi / sabit tarife) satıldığı durum:

        Yıllık gelir = Yıllık enerji [MWh] × BİRİM_FAYDA [EUR/MWh]

NEDEN YENİDEN DP ÇÖZÜLMÜYOR
---------------------------
Sabit tarifede bütün saatler aynı fiyattadır; puant saatleri kollamanın hiçbir
faydası yoktur. Gelir enerjiyle doğru orantılı olduğu için

        argmax (gelir) = argmax (BİRİM_FAYDA × enerji) = argmax (enerji)

yani optimal işletme politikası, alternatifler.py'de zaten çözülmüş olan
BANT (enerji maksimizasyonu) senaryosunun TAM OLARAK AYNISIDIR. Dolayısıyla
bu betik hezil_alternatifler.xlsx'teki BANT koşumlarının enerjilerini alıp
yalnızca değerlemeyi ve ekonomiyi yeniden kurar.

Bu, pik işletmeye göre önemli bir davranış değişikliğidir: sabit tarife hem
İŞLETME biçimini (puant → bant) hem de OPTİMAL BOYUTU değiştirir.

ÇIKTI : hezil_sabit_fayda.xlsx , hezil_sabit_fayda.png
================================================================================
"""

import os
import sys
import time
import numpy as np
import pandas as pd

import alternatifler as A

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ==============================================================================
BIRIM_FAYDA = 88.0          # sabit birim enerji faydası [EUR/MWh]
FAYDA_ARALIGI = np.arange(20.0, 161.0, 1.0)     # duyarlılık taraması [EUR/MWh]
ISARET_FAYDA = [40.0, 60.0, 88.0, 110.0, 140.0]
# ==============================================================================


def ekonomi_kur(d, birim_fayda, em=None, indirgeme=None):
    """Sabit birim faydayla yıllık gelir-gider. d: BANT koşumları tablosu."""
    em  = A.EM_BIRIM_EUR_KW if em is None else em
    ind = (A.INDIRGEME_ORANI + A.OM_ORANI) if indirgeme is None else indirgeme
    # yatırım = tünel + cebri boru(+tüneli) + EM + santral/şalt
    yatirim = (d["Tünel_maliyeti_MEUR"] + d["Cebri_maliyet_MEUR"]
               + d["Kurulu_güç_MW"] * (em + A.SANTRAL_SALT_EUR_KW) / 1000.0)
    gider   = yatirim * ind
    # brüt gelir → kesinti → NET gelir
    brut    = d["Enerji_GWh/yıl"] * birim_fayda / 1000.0        # GWh×€/MWh → M€
    gelir   = A.net_gelir(brut)
    return pd.DataFrame({
        "Yatırım_MEUR": yatirim.round(3),
        "Brüt_gelir_MEUR/yıl": brut.round(3),
        "Gelir_MEUR/yıl": gelir.round(3),
        "Yıllık_gider_MEUR": gider.round(3),
        "Net_fayda_MEUR/yıl": (gelir - gider).round(3),
        "Fayda_masraf_oranı": (gelir / gider).round(3),
        "Birim_enerji_maliyeti_EUR/MWh":
            (gider * 1e6 / (d["Enerji_GWh/yıl"] * 1000.0)).round(2),
    })


def main():
    kd = os.path.dirname(os.path.abspath(__file__))
    # En GÜNCEL tarama dosyası (hedef dosya Excel'de açıkken alternatifler.py
    # zaman damgalı yedeğe yazar; eski dosyayı okumak bayat sonuç verir)
    import glob
    ad = sorted(glob.glob(os.path.join(kd, "hezil_alternatifler*.xlsx")),
                key=os.path.getmtime)
    if not ad:
        raise SystemExit("Önce alternatifler.py çalıştırılmalı "
                         "(hezil_alternatifler*.xlsx bulunamadı)")
    yol = ad[-1]

    hepsi = pd.read_excel(yol, sheet_name="Tüm Alternatifler")
    bant = hepsi[(hepsi["Alt_No"] > 0) &
                 (hepsi["Amaç"].str.startswith("BANT"))].copy()
    pik  = hepsi[(hepsi["Alt_No"] > 0) &
                 (hepsi["Amaç"].str.startswith("PİK"))].copy()

    print("=" * 100)
    print(f"HEZİL HES — SABİT BİRİM FAYDA SENARYOSU  ({BIRIM_FAYDA:.0f} EUR/MWh)")
    print("=" * 100)
    print(f"Kaynak      : {os.path.basename(yol)}")
    print(f"İşletme     : BANT (enerji maks.) — sabit tarifede puant yapmanın "
          f"faydası yoktur")
    print(f"Gelir       : yıllık enerji × {BIRIM_FAYDA:.0f} EUR/MWh")
    print(f"Gider       : (tünel + EM) × {A.INDIRGEME_ORANI:.2f}, "
          f"EM = {A.EM_BIRIM_EUR_KW:.0f} EUR/kW\n")

    ek = ekonomi_kur(bant, BIRIM_FAYDA)
    t = pd.concat([bant.drop(columns=ek.columns, errors="ignore")
                   .reset_index(drop=True), ek.reset_index(drop=True)], axis=1)

    # ---- optimum -------------------------------------------------------------
    b = t.loc[t["Net_fayda_MEUR/yıl"].idxmax()]
    print("EN YÜKSEK NET FAYDALI ALTERNATİF")
    print(f"   Tünel D={b['Tünel_D_m']:.1f} m (v={b['Tünel_hızı_m/s']:.2f} m/s), "
          f"Q={b['Q_tasarım_m3/s']:.1f} m³/s, cebri boru D={b['Cebri_D_m']:.2f} m, "
          f"min kot {b['Min_kot_m']:.0f} m")
    print(f"   Kurulu güç {b['Kurulu_güç_MW']:.2f} MW | enerji "
          f"{b['Enerji_GWh/yıl']:.2f} GWh/yıl | regülasyon oranı "
          f"%{b['Regülasyon_oranı_%']:.1f} | çalışma "
          f"{b['Çalışma_saati_h/yıl']:.0f} h/yıl")
    print(f"   Yatırım {b['Yatırım_MEUR']:.3f} M€ | gelir "
          f"{b['Gelir_MEUR/yıl']:.3f} − gider {b['Yıllık_gider_MEUR']:.3f} = "
          f"NET FAYDA {b['Net_fayda_MEUR/yıl']:.3f} M€/yıl")
    print(f"   Fayda/masraf {b['Fayda_masraf_oranı']:.3f} | birim enerji maliyeti "
          f"{b['Birim_enerji_maliyeti_EUR/MWh']:.2f} EUR/MWh")

    print("\nHER ÇAP İÇİN EN İYİ SEÇENEK")
    print(f"   {'D':>5} {'Q':>6} {'Kot':>6} {'P_kur':>7} {'Enerji':>8}"
          f" {'Yatırım':>9} {'Gelir':>8} {'Gider':>7} {'NET':>8} {'F/M':>6}"
          f" {'Reg%':>6} {'Çalışma':>8}")
    print(f"   {'m':>5} {'m³/s':>6} {'m':>6} {'MW':>7} {'GWh':>8}"
          f" {'M€':>9} {'M€':>8} {'M€':>7} {'M€':>8} {'-':>6} {'%':>6} {'h/yıl':>8}")
    enler = []
    for D in sorted(t["Tünel_D_m"].unique()):
        g = t[t["Tünel_D_m"] == D]
        r = g.loc[g["Net_fayda_MEUR/yıl"].idxmax()]
        enler.append(r)
        print(f"   {D:5.1f} {r['Q_tasarım_m3/s']:6.1f} {r['Min_kot_m']:6.0f}"
              f" {r['Kurulu_güç_MW']:7.2f} {r['Enerji_GWh/yıl']:8.2f}"
              f" {r['Yatırım_MEUR']:9.3f} {r['Gelir_MEUR/yıl']:8.3f}"
              f" {r['Yıllık_gider_MEUR']:7.3f} {r['Net_fayda_MEUR/yıl']:8.3f}"
              f" {r['Fayda_masraf_oranı']:6.3f} {r['Regülasyon_oranı_%']:6.1f}"
              f" {r['Çalışma_saati_h/yıl']:8.0f}")
    enler = pd.DataFrame(enler)

    # ---- üç senaryonun karşılaştırması --------------------------------------
    pik_ek = pik.loc[pik["Net_fayda_MEUR/yıl"].idxmax()]
    bant_ek = bant.loc[bant["Net_fayda_MEUR/yıl"].idxmax()]
    print("\n" + "=" * 100)
    print("ÜÇ SENARYONUN OPTİMUMLARI")
    print("=" * 100)
    bas = ["PİK — piyasa fiyatı", "BANT — piyasa fiyatı",
           f"BANT — sabit {BIRIM_FAYDA:.0f} €/MWh"]
    sat = [pik_ek, bant_ek, b]
    print(f"   {'':<26}" + "".join(f"{x:>24}" for x in bas))
    for ad, k, fm in [
            ("Tünel çapı", "Tünel_D_m", "{:.1f} m"),
            ("Tasarım debisi", "Q_tasarım_m3/s", "{:.1f} m³/s"),
            ("Kurulu güç", "Kurulu_güç_MW", "{:.2f} MW"),
            ("Enerji", "Enerji_GWh/yıl", "{:.2f} GWh/yıl"),
            ("Çalışma süresi", "Çalışma_saati_h/yıl", "{:.0f} h/yıl"),
            ("Regülasyon oranı", "Regülasyon_oranı_%", "{:.1f} %"),
            ("Yatırım", "Yatırım_MEUR", "{:.3f} M€"),
            ("Yıllık gelir", "Gelir_MEUR/yıl", "{:.3f} M€"),
            ("Yıllık gider", "Yıllık_gider_MEUR", "{:.3f} M€"),
            ("NET FAYDA", "Net_fayda_MEUR/yıl", "{:.3f} M€"),
            ("Fayda/masraf", "Fayda_masraf_oranı", "{:.3f}")]:
        print(f"   {ad:<26}" + "".join(f"{fm.format(s[k]):>24}" for s in sat))

    # sabit tarifede pik işletme yapılsaydı (enerji düşük → gelir düşük)
    ayni = pik[(pik["Tünel_D_m"] == b["Tünel_D_m"]) &
               (pik["Q_tasarım_m3/s"] == b["Q_tasarım_m3/s"]) &
               (pik["Min_kot_m"] == b["Min_kot_m"])]
    if len(ayni):
        p = ayni.iloc[0]
        gp = p["Enerji_GWh/yıl"] * BIRIM_FAYDA / 1000.0
        print(f"\n   Aynı konfigürasyonda ({b['Tünel_D_m']:.1f} m / "
              f"{b['Q_tasarım_m3/s']:.1f} m³/s) sabit tarifeyle PİK işletilseydi:")
        print(f"      bant : {b['Enerji_GWh/yıl']:7.2f} GWh → "
              f"{b['Gelir_MEUR/yıl']:7.3f} M€ gelir, net "
              f"{b['Net_fayda_MEUR/yıl']:6.3f} M€")
        print(f"      pik  : {p['Enerji_GWh/yıl']:7.2f} GWh → {gp:7.3f} M€ gelir, "
              f"net {gp - b['Yıllık_gider_MEUR']:6.3f} M€")
        print(f"      → sabit tarifede puant işletme "
              f"{b['Gelir_MEUR/yıl']-gp:.3f} M€/yıl KAYBETTİRİR "
              f"(yük kaybı yüzünden üretilen enerji düşüyor, fiyat kazancı yok)")

    # ---- birim faydaya duyarlılık -------------------------------------------
    print("\nBİRİM FAYDAYA DUYARLILIK (optimum konfigürasyon nasıl kayıyor)")
    kayit = []
    for f in FAYDA_ARALIGI:
        e = ekonomi_kur(bant, f)
        i = int(e["Net_fayda_MEUR/yıl"].idxmax())
        r = bant.loc[i]
        kayit.append({"Birim_fayda_EUR/MWh": f,
                      "Optimum_D_m": r["Tünel_D_m"],
                      "Optimum_Q_m3/s": r["Q_tasarım_m3/s"],
                      "Kurulu_güç_MW": r["Kurulu_güç_MW"],
                      "Enerji_GWh/yıl": r["Enerji_GWh/yıl"],
                      "Net_fayda_MEUR/yıl": float(e.loc[i, "Net_fayda_MEUR/yıl"]),
                      "Fayda_masraf": float(e.loc[i, "Fayda_masraf_oranı"])})
    duy = pd.DataFrame(kayit)
    dg = duy[duy["Optimum_D_m"].ne(duy["Optimum_D_m"].shift())]
    onc = None
    for _, r in dg.iterrows():
        if onc is not None:
            print(f"   Birim fayda ≈ {r['Birim_fayda_EUR/MWh']:5.0f} €/MWh "
                  f"üzerinde optimum D={onc:.1f} m → D={r['Optimum_D_m']:.1f} m")
        onc = r["Optimum_D_m"]
    print(f"   {'Fayda':>7} {'Opt.D':>6} {'Opt.Q':>7} {'P_kur':>7} {'Enerji':>8}"
          f" {'NET':>8} {'F/M':>6}")
    for f in ISARET_FAYDA:
        r = duy.iloc[int(np.argmin(np.abs(duy["Birim_fayda_EUR/MWh"] - f)))]
        print(f"   {r['Birim_fayda_EUR/MWh']:7.0f} {r['Optimum_D_m']:6.1f}"
              f" {r['Optimum_Q_m3/s']:7.1f} {r['Kurulu_güç_MW']:7.2f}"
              f" {r['Enerji_GWh/yıl']:8.2f} {r['Net_fayda_MEUR/yıl']:8.3f}"
              f" {r['Fayda_masraf']:6.3f}")

    # ---- grafik --------------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = t.loc[t.groupby(["Tünel_D_m", "Q_tasarım_m3/s"])
               ["Net_fayda_MEUR/yıl"].idxmax()].sort_values(
                   ["Tünel_D_m", "Q_tasarım_m3/s"])

    fig, ax = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle(f"HEZİL HES — SABİT BİRİM FAYDA SENARYOSU ({BIRIM_FAYDA:.0f} "
                 f"EUR/MWh)  ·  bant işletme  ·  indirgeme {A.INDIRGEME_ORANI:.2f}"
                 f"  ·  EM {A.EM_BIRIM_EUR_KW:.0f} EUR/kW",
                 fontsize=13, fontweight="bold")

    a = ax[0, 0]
    for D, g in s.groupby("Tünel_D_m"):
        a.plot(g["Q_tasarım_m3/s"], g["Net_fayda_MEUR/yıl"], "o-",
               color=A.RENK[D], label=f"D={D:.1f} m")
    a.scatter([b["Q_tasarım_m3/s"]], [b["Net_fayda_MEUR/yıl"]], s=190,
              facecolors="none", edgecolors="#d1242f", linewidths=2, zorder=5)
    a.annotate(f"  optimum: D={b['Tünel_D_m']:.1f} m, "
               f"Q={b['Q_tasarım_m3/s']:.1f} m³/s\n"
               f"  {b['Net_fayda_MEUR/yıl']:.3f} M EUR/yıl",
               (b["Q_tasarım_m3/s"], b["Net_fayda_MEUR/yıl"]), fontsize=8, va="top")
    A._eksen_sik(a, s["Net_fayda_MEUR/yıl"])
    a.set_title("NET FAYDA — sabit tarife")
    a.set_xlabel("Tasarım debisi [m³/s]"); a.set_ylabel("Net fayda [milyon EUR/yıl]")
    a.legend(fontsize=8, ncol=2); a.grid(alpha=.3)

    a = ax[0, 1]
    for D, g in s.groupby("Tünel_D_m"):
        a.plot(g["Q_tasarım_m3/s"], g["Enerji_GWh/yıl"], "o-",
               color=A.RENK[D], label=f"D={D:.1f} m")
    A._eksen_sik(a, s["Enerji_GWh/yıl"])
    a.set_title("YILLIK ENERJİ (bant işletme) — gelirin tek belirleyicisi")
    a.set_xlabel("Tasarım debisi [m³/s]"); a.set_ylabel("Enerji [GWh/yıl]")
    a.legend(fontsize=8, ncol=2); a.grid(alpha=.3)

    a = ax[1, 0]
    a.step(duy["Birim_fayda_EUR/MWh"], duy["Optimum_D_m"], where="post",
           color="#0969da", lw=2, label="optimum tünel çapı")
    a.set_yticks(sorted(t["Tünel_D_m"].unique()))
    a.set_ylabel("Optimum tünel çapı [m]", color="#0969da")
    a2 = a.twinx()
    a2.step(duy["Birim_fayda_EUR/MWh"], duy["Optimum_Q_m3/s"], where="post",
            color="#bf3989", lw=2, ls="--", label="optimum tasarım debisi")
    a2.set_ylabel("Optimum tasarım debisi [m³/s]", color="#bf3989")
    a.axvline(BIRIM_FAYDA, color="#57606a", ls="--", lw=1.2)
    a.text(BIRIM_FAYDA + 2, a.get_ylim()[0] + 0.1,
           f"seçilen {BIRIM_FAYDA:.0f} €/MWh", fontsize=8, color="#57606a")
    a.set_title("Birim fayda arttıkça optimum büyüyor")
    a.set_xlabel("Sabit birim fayda [EUR/MWh]"); a.grid(alpha=.3)
    h1, l1 = a.get_legend_handles_labels(); h2, l2 = a2.get_legend_handles_labels()
    a.legend(h1 + h2, l1 + l2, fontsize=8, loc="lower right")

    a = ax[1, 1]
    kalem = ["Enerji_GWh/yıl", "Gelir_MEUR/yıl", "Yıllık_gider_MEUR",
             "Net_fayda_MEUR/yıl"]
    etiket = ["Enerji\n[GWh/yıl]", "Gelir\n[M€/yıl]", "Gider\n[M€/yıl]",
              "NET FAYDA\n[M€/yıl]"]
    olcek = [1 / 25.0, 1.0, 1.0, 1.0]
    x = np.arange(len(kalem)); w = 0.26
    for j, (sen, ad, c) in enumerate([
            (pik_ek, "PİK · piyasa", "#0969da"),
            (bant_ek, "BANT · piyasa", "#bf3989"),
            (b, f"BANT · sabit {BIRIM_FAYDA:.0f}", "#2da44e")]):
        v = [sen[k] * o for k, o in zip(kalem, olcek)]
        a.bar(x + (j - 1) * w, v, w, color=c,
              label=f"{ad}  (D={sen['Tünel_D_m']:.1f}, Q={sen['Q_tasarım_m3/s']:.1f})")
        for i, (k, o) in enumerate(zip(kalem, olcek)):
            a.text(i + (j - 1) * w, sen[k] * o, f"{sen[k]:.1f}",
                   ha="center", va="bottom", fontsize=7)
    a.set_xticks(x); a.set_xticklabels(etiket, fontsize=8)
    a.set_title("Üç senaryonun kendi optimum konfigürasyonu\n"
                "(enerji çubuğu görsel amaçla 25'e bölünmüştür)")
    a.legend(fontsize=8); a.grid(alpha=.3, axis="y")

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    pg = os.path.join(kd, "hezil_sabit_fayda.png")
    try:
        fig.savefig(pg, dpi=130)
    except PermissionError:
        pg = pg.replace(".png", f"_{time.strftime('%Y%m%d_%H%M%S')}.png")
        fig.savefig(pg, dpi=130)
    plt.close(fig)

    # ---- Excel ---------------------------------------------------------------
    girdi = pd.DataFrame([
        ("Birim enerji faydası", BIRIM_FAYDA, "EUR/MWh"),
        ("İşletme biçimi", "BANT (enerji maks.)", ""),
        ("Gerekçe", "sabit tarifede puant yapmanın faydası yok", ""),
        ("İndirgeme oranı", A.INDIRGEME_ORANI, "-"),
        ("EM birim maliyeti", A.EM_BIRIM_EUR_KW, "EUR/kW"),
        ("Alternatif sayısı", len(t), "adet"),
    ], columns=["Girdi", "Değer", "Birim"])

    px = os.path.join(kd, "hezil_sabit_fayda.xlsx")

    def yaz(p):
        with pd.ExcelWriter(p, engine="openpyxl") as xw:
            girdi.to_excel(xw, sheet_name="Girdiler", index=False)
            s.to_excel(xw, sheet_name="Ekonomi", index=False)
            enler.to_excel(xw, sheet_name="Çap Bazında En İyi", index=False)
            duy.to_excel(xw, sheet_name="Birim Fayda Duyarlılığı", index=False)
            t.sort_values("Net_fayda_MEUR/yıl", ascending=False).to_excel(
                xw, sheet_name="Tüm Alternatifler", index=False)
            for ws in xw.book.worksheets:
                for c in ws.columns:
                    w = max(len(str(x.value)) for x in c if x.value is not None)
                    ws.column_dimensions[c[0].column_letter].width = \
                        min(max(w + 2, 10), 32)
                ws.freeze_panes = "A2"

    try:
        yaz(px)
    except PermissionError:
        px = px.replace(".xlsx", f"_{time.strftime('%Y%m%d_%H%M%S')}.xlsx")
        yaz(px)

    print("\nÇIKTI DOSYALARI")
    print(f"   {px}")
    print(f"   {pg}")
    print("=" * 100)


if __name__ == "__main__":
    main()
