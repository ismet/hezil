# -*- coding: utf-8 -*-
"""
================================================================================
HEZİL HES — ELEKTROMEKANİK BİRİM MALİYETİNE DUYARLILIK
================================================================================

alternatifler.py taramasının sonucunu (hezil_alternatifler.xlsx) okur ve
elektromekanik teçhizat birim maliyeti değiştikçe OPTİMUM SEÇENEĞİN nasıl
kaydığını çıkarır. Dinamik programlama yeniden çözülmez — gelir, enerji ve
kurulu güç zaten hesaplanmıştır; yalnızca yıllık gider yeniden kurulur:

    Yatırım      = tünel maliyeti + kurulu güç × EM birim maliyeti
    Yıllık gider = yatırım × indirgeme oranı
    Net fayda    = yıllık gelir − yıllık gider

NEDEN ÖNEMLİ
------------
5.2 → 5.6 m adımında tünel maliyeti yalnızca +0.40 M EUR artarken kurulu güç
19 MW büyüdüğü için EM maliyeti +2.66 M EUR artıyor. Yani büyük çapların
avantajı tünel maliyet tablosundan değil, EM biriminin düşük varsayılmasından
geliyor. Bu betik, kararın hangi EM fiyatında değiştiğini gösterir.

ÇIKTI : hezil_em_duyarlilik.xlsx , hezil_em_duyarlilik.png
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

EM_ARALIGI = np.arange(0.0, 601.0, 5.0)      # taranacak EM birim maliyeti [EUR/kW]
ISARET_EM  = [140.0, 200.0, 250.0, 300.0, 400.0, 500.0]   # tabloya yazılacaklar


def net_fayda(t, em_eur_kw, indirgeme=None):
    """Verilen EM birim maliyetinde her alternatifin net faydası [M EUR/yıl]."""
    ind = A.INDIRGEME_ORANI + A.OM_ORANI if indirgeme is None else indirgeme
    # yatırım = tünel + cebri boru(+tüneli) + EM + santral/şalt
    yatirim = (t["Tünel_maliyeti_MEUR"] + t["Cebri_maliyet_MEUR"]
               + t["Kurulu_güç_MW"] * (em_eur_kw + A.SANTRAL_SALT_EUR_KW)
               / 1000.0)
    # Gelir_MEUR/yıl zaten NET gelirdir (brütten kesinti düşülmüş)
    return t["Gelir_MEUR/yıl"] - yatirim * ind, yatirim


def en_yeni_tarama(kd):
    """En GÜNCEL tarama dosyasını bulur. Hedef dosya Excel'de açıkken kilitli
    olduğu için alternatifler.py zaman damgalı yedeğe yazabilir; bu durumda
    eski dosyayı okumak bayat sonuç verir."""
    import glob
    ad = sorted(glob.glob(os.path.join(kd, "hezil_alternatifler*.xlsx")),
                key=os.path.getmtime)
    if not ad:
        raise SystemExit("Önce alternatifler.py çalıştırılmalı "
                         "(hezil_alternatifler*.xlsx bulunamadı)")
    return ad[-1]


def main():
    kd = os.path.dirname(os.path.abspath(__file__))
    yol = en_yeni_tarama(kd)

    t = pd.read_excel(yol, sheet_name="Tüm Alternatifler")
    t = t[t["Alt_No"] > 0].copy()             # referans satırını ayrı tut
    ref = pd.read_excel(yol, sheet_name="Referans").iloc[0]

    print("=" * 92)
    print("HEZİL HES — ELEKTROMEKANİK BİRİM MALİYETİNE DUYARLILIK")
    print("=" * 92)
    print(f"Kaynak     : {os.path.basename(yol)}  ({len(t)} alternatif)")
    print(f"İndirgeme  : {A.INDIRGEME_ORANI:.2f}")
    print(f"Tünel mal. : verilen tablodan (çap başına sabit, EM'den bağımsız)\n")

    # ---- her EM fiyatı için optimum -----------------------------------------
    kayit = []
    for em in EM_ARALIGI:
        nf, yat = net_fayda(t, em)
        i = int(nf.idxmax())
        r = t.loc[i]
        kayit.append({
            "EM_EUR/kW": em,
            "Optimum_D_m": r["Tünel_D_m"],
            "Optimum_Q_m3/s": r["Q_tasarım_m3/s"],
            "Optimum_min_kot_m": r["Min_kot_m"],
            "Kurulu_güç_MW": r["Kurulu_güç_MW"],
            "Enerji_GWh/yıl": r["Enerji_GWh/yıl"],
            "Yatırım_MEUR": round(float(yat.loc[i]), 3),
            "Gelir_MEUR/yıl": r["Gelir_MEUR/yıl"],
            "Net_fayda_MEUR/yıl": round(float(nf.loc[i]), 3),
            "Fayda_masraf": round(float(r["Gelir_MEUR/yıl"] /
                                        (yat.loc[i] * A.INDIRGEME_ORANI)), 3),
        })
    duy = pd.DataFrame(kayit)

    # ---- optimumun değiştiği eşikler ----------------------------------------
    print("OPTİMUM ÇAPIN DEĞİŞTİĞİ EM FİYATLARI")
    dg = duy[duy["Optimum_D_m"].ne(duy["Optimum_D_m"].shift())]
    onceki = None
    for _, r in dg.iterrows():
        if onceki is not None:
            print(f"   EM ≈ {r['EM_EUR/kW']:5.0f} EUR/kW üzerinde optimum "
                  f"D={onceki:.1f} m → D={r['Optimum_D_m']:.1f} m'ye kayıyor")
        onceki = r["Optimum_D_m"]
    print(f"   (EM = 0 iken optimum D={dg.iloc[0]['Optimum_D_m']:.1f} m, "
          f"EM = {EM_ARALIGI[-1]:.0f} iken D={duy.iloc[-1]['Optimum_D_m']:.1f} m)")

    # ---- işaret noktalarında tablo ------------------------------------------
    print(f"\n{'EM':>6} {'Opt.D':>6} {'Opt.Q':>7} {'P_kur':>7} {'Enerji':>8}"
          f" {'Yatırım':>9} {'Gelir':>7} {'Gider':>7} {'NET':>8} {'F/M':>6}")
    print(f"{'€/kW':>6} {'m':>6} {'m³/s':>7} {'MW':>7} {'GWh':>8}"
          f" {'M€':>9} {'M€':>7} {'M€':>7} {'M€':>8} {'-':>6}")
    for em in ISARET_EM:
        r = duy.iloc[int(np.argmin(np.abs(duy["EM_EUR/kW"] - em)))]
        gider = r["Yatırım_MEUR"] * A.INDIRGEME_ORANI
        print(f"{r['EM_EUR/kW']:6.0f} {r['Optimum_D_m']:6.1f} "
              f"{r['Optimum_Q_m3/s']:7.1f} {r['Kurulu_güç_MW']:7.2f}"
              f" {r['Enerji_GWh/yıl']:8.2f} {r['Yatırım_MEUR']:9.3f}"
              f" {r['Gelir_MEUR/yıl']:7.3f} {gider:7.3f}"
              f" {r['Net_fayda_MEUR/yıl']:8.3f} {r['Fayda_masraf']:6.3f}")

    # ---- çap bazında ikili karşılaştırma ------------------------------------
    print("\nÇAP BAZINDA NET FAYDA [M EUR/yıl] — her çapın kendi en iyi debisiyle")
    caplar = sorted(t["Tünel_D_m"].unique())
    print(f"   {'EM €/kW':>9}" + "".join(f"{d:>9.1f}" for d in caplar) + "   kazanan")
    cap_egri = {d: [] for d in caplar}
    for em in EM_ARALIGI:
        nf, _ = net_fayda(t, em)
        s = t.assign(NF=nf)
        for d in caplar:
            cap_egri[d].append(float(s[s["Tünel_D_m"] == d]["NF"].max()))
    for em in ISARET_EM:
        j = int(np.argmin(np.abs(EM_ARALIGI - em)))
        v = [cap_egri[d][j] for d in caplar]
        kazanan = caplar[int(np.argmax(v))]
        print(f"   {em:9.0f}" + "".join(f"{x:9.3f}" for x in v) +
              f"   D={kazanan:.1f} m")

    # ---- referansın kırılma noktası -----------------------------------------
    print("\nREFERANS TASARIM (D=4.4 m, Q=60 m³/s) ile karşılaştırma")
    for em in ISARET_EM:
        yat_ref = ref["Tünel_maliyeti_MEUR"] + ref["Kurulu_güç_MW"] * em / 1000.0
        nf_ref = ref["Gelir_MEUR/yıl"] - yat_ref * A.INDIRGEME_ORANI
        j = int(np.argmin(np.abs(EM_ARALIGI - em)))
        r = duy.iloc[j]
        print(f"   EM={em:5.0f} €/kW → referans {nf_ref:6.3f} M€/yıl | "
              f"optimum (D={r['Optimum_D_m']:.1f}, Q={r['Optimum_Q_m3/s']:.1f}) "
              f"{r['Net_fayda_MEUR/yıl']:6.3f} M€/yıl | fark "
              f"{r['Net_fayda_MEUR/yıl']-nf_ref:+6.3f}")

    # ---- grafik --------------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(16, 6.5))
    fig.suptitle("HEZİL HES — Elektromekanik birim maliyetine duyarlılık  "
                 f"(indirgeme oranı {A.INDIRGEME_ORANI:.2f})",
                 fontsize=13, fontweight="bold")

    a = ax[0]
    for d in caplar:
        a.plot(EM_ARALIGI, cap_egri[d], color=A.RENK.get(d), lw=1.8,
               label=f"D={d:.1f} m")
    a.axvline(A.EM_BIRIM_EUR_KW, color="#57606a", ls="--", lw=1.2)
    a.text(A.EM_BIRIM_EUR_KW + 6, a.get_ylim()[0] + 0.4,
           f"kullanılan varsayım\n{A.EM_BIRIM_EUR_KW:.0f} EUR/kW",
           fontsize=8, color="#57606a")
    a.axhline(0, color="#57606a", lw=1)
    a.set_title("Her çapın (en iyi debisiyle) net faydası")
    a.set_xlabel("EM birim maliyeti [EUR/kW]")
    a.set_ylabel("Net fayda [milyon EUR/yıl]")
    a.legend(fontsize=8); a.grid(alpha=.3)

    a = ax[1]
    a.step(duy["EM_EUR/kW"], duy["Optimum_D_m"], where="post",
           color="#0969da", lw=2, label="optimum tünel çapı")
    a.set_xlabel("EM birim maliyeti [EUR/kW]")
    a.set_ylabel("Optimum tünel çapı [m]", color="#0969da")
    a.set_yticks(caplar)
    a2 = a.twinx()
    a2.step(duy["EM_EUR/kW"], duy["Optimum_Q_m3/s"], where="post",
            color="#bf3989", lw=2, ls="--", label="optimum tasarım debisi")
    a2.set_ylabel("Optimum tasarım debisi [m³/s]", color="#bf3989")
    a.axvline(A.EM_BIRIM_EUR_KW, color="#57606a", ls="--", lw=1.2)
    a.set_title("EM fiyatı arttıkça optimum küçülüyor")
    a.grid(alpha=.3)
    h1, l1 = a.get_legend_handles_labels()
    h2, l2 = a2.get_legend_handles_labels()
    a.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper right")

    fig.tight_layout(rect=(0, 0, 1, 0.93))
    pg = os.path.join(kd, "hezil_em_duyarlilik.png")
    try:
        fig.savefig(pg, dpi=130)
    except PermissionError:
        pg = pg.replace(".png", f"_{time.strftime('%Y%m%d_%H%M%S')}.png")
        fig.savefig(pg, dpi=130)
    plt.close(fig)

    # ---- Excel ---------------------------------------------------------------
    cap_tab = pd.DataFrame({"EM_EUR/kW": EM_ARALIGI,
                            **{f"D={d:.1f} m": cap_egri[d] for d in caplar}})
    px = os.path.join(kd, "hezil_em_duyarlilik.xlsx")

    def yaz(p):
        with pd.ExcelWriter(p, engine="openpyxl") as xw:
            duy.to_excel(xw, sheet_name="Optimum vs EM", index=False)
            cap_tab.round(3).to_excel(xw, sheet_name="Çap Bazında Net Fayda",
                                      index=False)
            for ws in xw.book.worksheets:
                for c in ws.columns:
                    w = max(len(str(x.value)) for x in c if x.value is not None)
                    ws.column_dimensions[c[0].column_letter].width = \
                        min(max(w + 2, 10), 30)
                ws.freeze_panes = "A2"

    try:
        yaz(px)
    except PermissionError:
        px = px.replace(".xlsx", f"_{time.strftime('%Y%m%d_%H%M%S')}.xlsx")
        yaz(px)

    print("\nÇIKTI DOSYALARI")
    print(f"   {px}")
    print(f"   {pg}")
    print("=" * 92)


if __name__ == "__main__":
    main()
