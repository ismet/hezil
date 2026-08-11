# -*- coding: utf-8 -*-
"""
================================================================================
HEZİL HES — SEÇENEK BAZINDA İŞLETME DETAYI (pano için ön hesap)
================================================================================

Panoda bir seçeneğe tıklandığında o konfigürasyonun İŞLETME ÇALIŞMASI
gösterilir. Dinamik programlama tarayıcıda çözülemeyeceği için işletme serileri
burada önceden hesaplanır ve panoya gömülmek üzere JSON olarak yazılır.

TEMEL SADELEŞTİRME
------------------
Her konfigürasyonun yalnızca İKİ işletme çalışması vardır:
    "gelir"  → PİK işletme   (S1 bunu kullanır; S4'ün 11–50. yılları)
    "enerji" → BANT işletme  (S2 ve S3 bunu kullanır; S4'ün 1–10. yılları)
Dört senaryo bu iki çalışmanın değerlemesinden ibarettir; dolayısıyla
konfigürasyon başına 2 DP koşumu yeter.

HANGİ SEÇENEKLER HESAPLANIR
---------------------------
Panoya bütün 1512 alternatifin serisini gömmek dosyayı onlarca MB yapardı.
Bunun yerine gerçekte incelenmeye değer seçenekler hesaplanır:
    · dört senaryonun optimumu
    · her senaryo × her tünel çapı için en iyi seçenek
    · referans tasarım (D=4.4 m, Q=60 m³/s)
    · KONFIG_EK listesine elle eklenenler
Aynı konfigürasyon birden çok kez seçilse de bir kez çözülür.

ÇIKTI : hezil_isletme_detay.json   (dashboard.py bunu okuyup gömer)
================================================================================
"""

import os
import re
import sys
import glob
import json
import time
import numpy as np
import pandas as pd

import optimzasyon as opt
import alternatifler as A

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Elle eklenmek istenen konfigürasyonlar: (tünel D, tasarım debisi, cebri boru
# hızı, minimum kot). Panoda incelemek istediğiniz başka seçenek varsa buraya
# ekleyip betiği yeniden koşmanız yeterlidir.
KONFIG_EK = []

AMACLAR = ["gelir", "enerji"]


def konfig_anahtar(dt, q, vc, km):
    return f"{dt:.1f}|{q:.1f}|{vc:.1f}|{km:.0f}"


def isletme_serisi(dt, q, vc, km, amac, fse):
    """Bir konfigürasyonu kurup DP ile çöz, aylık işletme serisini döndür."""
    D_c = np.sqrt(4.0 * q / (np.pi * vc))
    opt.TUNEL_D, opt.TUNEL_L = dt, A.TUNEL_UZUNLUK
    opt.CEBRI_D, opt.CEBRI_L = D_c, A.CEBRI_UZUNLUK
    opt.KOL_D, opt.KOL_L = A.KOL_CAP_ORANI * D_c, A.KOL_UZUNLUK
    opt.Q_TASARIM = q
    opt.KOT_MIN = km
    opt.BASLANGIC_KOTU = km
    opt.AMAC = amac
    opt.yeniden_kur()

    V, Qg, pq, pm, _ = opt.dp_coz(opt.AKIMLAR, fse, ilerleme=False)
    df = opt.ileri_simulasyon(V, Qg, pq, pm, opt.AKIMLAR, fse)

    # ünite yük oranı: işletme debisi / o modda çalışan ünitelerin tasarım debisi
    q_un = opt.Q_TASARIM / opt.UNITE_SAYISI
    yuk, un = [], []
    for _, r in df.iterrows():
        qo = float(r["Q_isletme_m3s"])
        if qo <= 1e-9:
            yuk.append(0.0)
            un.append(0)
        else:
            k = int(np.argmin(np.abs(opt._MOD_Q - qo)))
            yuk.append(float(opt._MOD_YUK[k]))
            un.append(int(opt._MOD_N[k]))

    yil = df.groupby("SuYili")["Enerji_MWh"].sum() / 1000.0
    return {
        "kot":  [round(float(v), 1) for v in df["Kot_son"]],
        "gelen": [round(float(v), 2) for v in df["Gelen_m3s"]],
        "q":    [round(float(v), 2) for v in df["Turbin_m3s"]],
        "savak": [round(float(v), 2) for v in df["Savak_m3s"]],
        "hnet": [round(float(v), 1) for v in df["Net_Dusu_m"]],
        "guc":  [round(float(v), 2) for v in df["Guc_MW"]],
        "saat": [round(float(v), 0) for v in df["Calisma_saat"]],
        "yuk":  [round(v, 3) for v in yuk],
        "unite": un,
        "yillik_enerji": [round(float(v), 1) for v in yil],
        "ozet": {
            "P_kurulu": round(opt.P_KURULU, 2),
            "enerji": round(float(yil.mean()), 2),
            "firm": round(float(np.percentile(yil, 5)), 2),
            "calisma": round(float(df["Calisma_saat"].sum() /
                                   opt.AKIMLAR.shape[0]), 0),
            "kapasite_f": round(float(yil.mean() * 1000
                                      / (opt.P_KURULU * 8766.0) * 100), 1),
            "kot_min": round(float(df["Kot_son"].min()), 1),
            "kot_ort": round(float(df["Kot_son"].mean()), 1),
            "kot_maks": round(float(df["Kot_son"].max()), 1),
        },
    }


def secilecek_konfigler(x):
    """Tarama sonucundan detayı hesaplanacak konfigürasyonları belirle."""
    t = x.parse("Tüm Senaryolar")
    sec = {}

    def ekle(r, neden):
        a = konfig_anahtar(r["Tünel_D_m"], r["Q_tasarım_m3/s"],
                           r["Cebri_hızı_m/s"], r["Min_kot_m"])
        if a not in sec:
            sec[a] = {"dt": float(r["Tünel_D_m"]),
                      "q": float(r["Q_tasarım_m3/s"]),
                      "vc": float(r["Cebri_hızı_m/s"]),
                      "km": float(r["Min_kot_m"]),
                      "neden": []}
        if neden not in sec[a]["neden"]:
            sec[a]["neden"].append(neden)

    for s in ("S1", "S2", "S3", "S4"):
        ekle(t.loc[t[f"{s}_net_MEUR"].idxmax()], f"{s} optimumu")
        for D in sorted(t["Tünel_D_m"].unique()):
            g = t[t["Tünel_D_m"] == D]
            ekle(g.loc[g[f"{s}_net_MEUR"].idxmax()], f"{s} · D={D:.1f} m en iyi")

    # referansa en yakın ızgara noktası
    g = t[t["Tünel_D_m"] == 4.4]
    if len(g):
        g = g[g["Q_tasarım_m3/s"] == g["Q_tasarım_m3/s"].max()]
        ekle(g.loc[g["S1_net_MEUR"].idxmax()], "referansa en yakın")

    for dt, q, vc, km in KONFIG_EK:
        sec[konfig_anahtar(dt, q, vc, km)] = {
            "dt": dt, "q": q, "vc": vc, "km": km, "neden": ["elle eklendi"]}
    return sec


def main():
    kd = os.path.dirname(os.path.abspath(__file__))
    ad = sorted(glob.glob(os.path.join(kd, "hezil_alternatifler*.xlsx")),
                key=os.path.getmtime)
    if not ad:
        raise SystemExit("Önce alternatifler.py çalıştırılmalı")
    yol = ad[-1]

    print("=" * 92)
    print("HEZİL HES — SEÇENEK BAZINDA İŞLETME DETAYI")
    print("=" * 92)
    print(f"Kaynak : {os.path.basename(yol)}")

    ptf, kaynak = opt.ptf_oku(os.path.join(kd, opt.PTF_DOSYASI))
    fse = opt.FiyatSureEgrisi(ptf)

    sec = secilecek_konfigler(pd.ExcelFile(yol))
    print(f"Seçenek: {len(sec)} benzersiz konfigürasyon × {len(AMACLAR)} işletme "
          f"= {len(sec)*len(AMACLAR)} DP koşumu\n")

    detay, t0 = {}, time.time()
    for i, (a, k) in enumerate(sec.items(), 1):
        d = {"dt": k["dt"], "q": k["q"], "vc": k["vc"], "km": k["km"],
             "neden": k["neden"]}
        for amac in AMACLAR:
            d[amac] = isletme_serisi(k["dt"], k["q"], k["vc"], k["km"],
                                     amac, fse)
        detay[a] = d
        print(f"   {i:3d}/{len(sec)}  D={k['dt']:.1f} Q={k['q']:5.1f} "
              f"v_c={k['vc']:.1f} kot={k['km']:.0f}  "
              f"({', '.join(k['neden'][:2])}{'…' if len(k['neden']) > 2 else ''})")

    paket = {
        "konfig": detay,
        "yil0": int(opt.AKIM_YILLARI[0]),
        "yil_sayisi": int(opt.AKIMLAR.shape[0]),
        "ay_adlari": opt.AY_ADLARI,
        "kuyruk": float(opt.KOT_KUYRUK),
        "kot_maks": float(opt.KOT_MAKS),
        "verim_egrisi": {
            "yuk": [round(float(v), 4) for v in opt.VERIM_YUK],
            "eta": [round(float(v), 4) for v in opt.VERIM_TURBIN],
            "eta_jen": opt.ETA_JENERATOR, "eta_trafo": opt.ETA_TRAFO,
            "kaynak": "HPWE / KOCHENDÖRFER — Hezil 2 HPP, Francis, n=375 rpm",
        },
    }

    cikti = os.path.join(kd, "hezil_isletme_detay.json")
    with open(cikti, "w", encoding="utf-8") as f:
        json.dump(paket, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n{len(sec)*len(AMACLAR)} koşum {time.time()-t0:.0f} saniyede bitti.")
    print(f"Dosya boyu : {os.path.getsize(cikti)/1024:.0f} KB")
    print(f"ÇIKTI      : {cikti}")
    print("Şimdi dashboard.py çalıştırılırsa pano bu detayı gömer.")
    print("=" * 92)


if __name__ == "__main__":
    main()
