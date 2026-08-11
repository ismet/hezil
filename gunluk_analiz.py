# -*- coding: utf-8 -*-
"""
================================================================================
HEZİL HES — GÜNLÜK ZAMAN ADIMI ANALİZİ
(aylık modelin minimum su kotu sonucu günlük akımlarla değişir mi?)
================================================================================

SORU
----
Aylık ortalama akımla çözülen modelde minimum işletme kotunu 720 m'den 690 m'ye
indirmenin faydası çıkmamıştı. Aylık ortalama, ay içi değişkenliği tamamen
gizlediği için bu sonuç zaman adımının bir yan etkisi olabilir. Günlük çözümde
iki yeni mekanizma devreye girer:

  (1) SAVAKLAMA ARTAR — aylık ortalama 89 m³/s olan Nisan'da günlük debiler
      150–250 m³/s'ye çıkar; rezervuar doluyken bu tepeler savaklanır. Aylık
      model bunu göremez ve savaklamayı OLDUĞUNDAN AZ tahmin eder.
  (2) DEPOLAMANIN GÜNLÜK/HAFTALIK DÜZENLEME DEĞERİ — yüksek günlerde doldurup
      düşük günlerde çekmek aylık adımda görünmez.

Her iki mekanizma da "daha çok hacim iyidir" yönünde çalışır. Buna karşılık
minimum kotu düşürmenin bedeli değişmez: 690 m'de brüt düşü 116 m, 720 m'de
146 m — yani %20 düşü kaybı. Bu betik ödünleşmeyi günlük adımda çözer.

YÖNTEM
------
  · Zaman adımı : GÜN (su yılı sayısı × 365 aşama)
  · Fiyat       : her TAKVİM GÜNÜ için o günün 24 saatlik fiyat-süre eğrisi
                  (pik fayda gün içinde uygulanır; aylık modelde ay içindeydi)
  · Akım        : aylık ortalamalar iki biçimde günlüğe indirgenir
                    "duz"    → ay boyunca sabit (yalnız zaman adımı etkisi)
                    "gunluk" → AR(1) log-normal ay içi değişkenlik, aylık
                               hacim BİREBİR korunur (değişkenlik etkisi)
  · Karar       : günlük ortalama türbin debisi × işletme modu (aylıkla aynı)

UYARI — GERÇEK GÜNLÜK VERİ DEĞİLDİR
-----------------------------------
Elde gözlenmiş günlük akım serisi yoktur (proje dosyalarında yalnızca taşkın
tekerrür hidrografları var). Günlük seri, aylık ortalamalardan sentetik olarak
türetilmiştir; ay içi değişim katsayıları (AYLIK_CV) mühendislik kabulüdür.
Bu nedenle MUTLAK sonuçlar değil, minimum kot sonucunun bu kabullere karşı
DAYANIKLI olup olmadığı okunmalıdır. Kesin cevap için DSİ günlük akım gözlemleri
gereklidir.

ÇIKTI : hezil_gunluk_analiz.xlsx , hezil_gunluk_analiz.png
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
# TARAMA
# ==============================================================================
KONFIGLER = [                     # (ad, tünel D, tasarım debisi)
    ("REFERANS  D=4.4 / Q=60.0", 4.4, 60.0),
    ("OPTİMUM   D=5.6 / Q=93.6", 5.6, 93.6),
]
MIN_KOTLAR = [690.0, 700.0, 710.0, 720.0]
AKIM_TIPLERI = ["duz", "gunluk"]

# Ay içi günlük değişim katsayısı (CV) — takvim ayına göre.
# Kar erimesi ve yağışlı dönemde yüksek, resesyonda düşük.
AYLIK_CV = {1: 0.25, 2: 0.30, 3: 0.45, 4: 0.45, 5: 0.40, 6: 0.30,
            7: 0.15, 8: 0.12, 9: 0.10, 10: 0.15, 11: 0.20, 12: 0.25}
CV_CARPANI = 1.0        # duyarlılık için 1.5 yapılıp tekrar koşulabilir
AR1_RHO = 0.85          # günlük akımın 1 gün gecikmeli özilişkisi
TOHUM = 20260805

GUN_SAYISI = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
              7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


# ==============================================================================
# 1) GÜNLÜK AKIM SERİSİNİN ÜRETİLMESİ
# ==============================================================================
def gunluk_akim(akimlar, tip="gunluk"):
    """Aylık ortalamalardan günlük seri. Her ayın HACMİ birebir korunur.
    Döner: (debi [m3/s], takvim_ayı, gün_no) — su yılı sırasıyla (Ekim→Eylül)."""
    rng = np.random.default_rng(TOHUM)
    q, ay_list, gun_list = [], [], []
    x = 0.0                                     # AR(1) durumu (aylar arası sürer)
    for yil in range(akimlar.shape[0]):
        for j in range(12):
            ay = opt.TAKVIM_AYI[j]
            n = GUN_SAYISI[ay]
            ort = akimlar[yil, j]
            if tip == "duz":
                g = np.full(n, ort)
            else:
                cv = AYLIK_CV[ay] * CV_CARPANI
                s = np.sqrt(np.log(1.0 + cv**2))        # log-uzayda std
                eps_s = s * np.sqrt(1.0 - AR1_RHO**2)
                z = np.empty(n)
                for i in range(n):
                    x = AR1_RHO * x + rng.normal(0.0, eps_s)
                    z[i] = x
                g = np.exp(z - 0.5 * s**2)              # ortalaması ~1
                g = g / g.mean() * ort                  # aylık hacmi birebir koru
            q.append(g)
            ay_list.append(np.full(n, ay))
            gun_list.append(np.arange(1, n + 1))
    return (np.concatenate(q), np.concatenate(ay_list).astype(int),
            np.concatenate(gun_list).astype(int))


# ==============================================================================
# 2) GÜNLÜK FİYAT-SÜRE EĞRİLERİ
# ==============================================================================
class GunlukFiyat:
    """Her takvim günü için o günün 24 saatlik fiyat-süre eğrisi."""

    def __init__(self, ptf):
        self.kum, self.ort = {}, {}
        for (m, d), g in ptf.groupby([ptf.index.month, ptf.index.day]):
            p = np.sort(np.asarray(g.values, float))[::-1]
            self.kum[(m, d)] = np.concatenate([[0.0], np.cumsum(p)])
            self.ort[(m, d)] = float(p.mean())
        # 29 Şubat vb. eksik günler için yedek
        self.yedek = {m: np.mean([v for (mm, _), v in self.ort.items() if mm == m])
                      for m in range(1, 13)}

    def egri(self, m, d):
        return self.kum.get((m, d), self.kum.get((m, min(d, 28))))

    def gun_ort(self, m, d):
        return self.ort.get((m, d), self.yedek[m])


# ==============================================================================
# 3) GÜNLÜK ADIMLI DİNAMİK PROGRAMLAMA
# ==============================================================================
def dp_gunluk(q, aylar, gunler, gf, ilerleme=False):
    T = len(q)
    V_grid = np.linspace(opt.V_MIN, opt.V_MAKS, opt.N_DURUM)
    Q_grid = np.linspace(0.0, opt.Q_TASARIM, opt.N_KARAR)
    dt = 86400.0
    hrs = 24.0

    F_next = np.where(V_grid >= opt.V_BASLANGIC - 1e-9, 0.0, -opt.CEZA)
    pol_q = np.zeros((T, opt.N_DURUM), dtype=np.int16)
    pol_m = np.zeros((T, opt.N_DURUM), dtype=np.int16)
    idx_i = np.arange(opt.N_DURUM)
    aktif = opt._MOD_Q > 1e-6
    W_sabit = np.broadcast_to((Q_grid * dt)[None, :],
                              (opt.N_DURUM, opt.N_KARAR))

    # can suyu: su yılı ayına göre (takvim ayından bul)
    can_ay = {opt.TAKVIM_AYI[j]: opt.CAN_SUYU_AYLIK[j] for j in range(12)}

    for t in range(T - 1, -1, -1):
        ay, gun = aylar[t], gunler[t]
        giren = q[t] * dt / 1e6
        can_hac = can_ay[ay] * dt / 1e6
        mevcut = V_grid + giren - opt.V_MIN
        can_act = np.minimum(can_hac, np.maximum(mevcut, 0.0))

        Vn = V_grid[:, None] + giren - can_act[:, None] - (Q_grid * dt / 1e6)[None, :]
        uygun = Vn >= opt.V_MIN - 1e-9
        Vn = np.clip(Vn, opt.V_MIN, opt.V_MAKS)
        kot_ort = opt.kot(0.5 * (V_grid[:, None] + Vn))
        F_int = np.interp(Vn.ravel(), V_grid, F_next).reshape(Vn.shape)

        c = gf.egri(ay, gun)
        xs = np.arange(len(c))

        en_iyi = np.full((opt.N_DURUM, opt.N_KARAR), -np.inf)
        en_iyi_mod = np.zeros((opt.N_DURUM, opt.N_KARAR), dtype=np.int16)
        for k in range(len(opt._MOD_Q)):
            if not aktif[k]:
                continue
            N_saat = W_sabit / (opt._MOD_Q[k] * 3600.0)
            H_net = np.maximum(kot_ort - opt.KOT_KUYRUK - opt._MOD_KAYIP[k], 0.0)
            P = opt.G * opt._MOD_Q[k] * H_net * opt._MOD_ETA[k] / 1000.0
            fayda = P * np.interp(N_saat, xs, c)
            fayda = np.where(N_saat <= hrs + 1e-9, fayda, -np.inf)
            db = fayda > en_iyi
            en_iyi = np.where(db, fayda, en_iyi)
            en_iyi_mod = np.where(db, k, en_iyi_mod)
        en_iyi[:, 0] = 0.0
        en_iyi_mod[:, 0] = -1

        toplam = np.where(uygun & np.isfinite(en_iyi), en_iyi + F_int, -opt.CEZA)
        j = np.argmax(toplam, axis=1)
        F_next = toplam[idx_i, j]
        pol_q[t] = j
        pol_m[t] = en_iyi_mod[idx_i, j]
        if ilerleme and t % 2000 == 0:
            print(f"      günlük DP ... {t:6d}/{T}", end="\r")
    return V_grid, Q_grid, pol_q, pol_m


def sim_gunluk(V_grid, Q_grid, pol_q, pol_m, q, aylar, gunler, gf):
    T = len(q)
    dt = 86400.0
    can_ay = {opt.TAKVIM_AYI[j]: opt.CAN_SUYU_AYLIK[j] for j in range(12)}
    V = opt.V_BASLANGIC
    E = R = SAV = TUR = SAAT = 0.0
    kotlar = np.empty(T)
    for t in range(T):
        ay, gun = aylar[t], gunler[t]
        i = int(np.argmin(np.abs(V_grid - V)))
        j, k = int(pol_q[t, i]), int(pol_m[t, i])
        Qt = Q_grid[j]
        giren = q[t] * dt / 1e6
        can_act = min(can_ay[ay] * dt / 1e6, max(V + giren - opt.V_MIN, 0.0))
        Vn = V + giren - can_act - Qt * dt / 1e6
        sav = max(Vn - opt.V_MAKS, 0.0)
        Vn = min(max(Vn, opt.V_MIN), opt.V_MAKS)
        kot_ort = float(opt.kot(0.5 * (V + Vn)))
        if k >= 0 and Qt > 1e-9:
            Q_op = float(opt._MOD_Q[k])
            N = min(Qt * dt / (Q_op * 3600.0), 24.0)
            H = max(kot_ort - opt.KOT_KUYRUK - float(opt._MOD_KAYIP[k]), 0.0)
            P = opt.G * Q_op * H * float(opt._MOD_ETA[k]) / 1000.0
            c = gf.egri(ay, gun)
            E += P * N
            R += P * float(np.interp(N, np.arange(len(c)), c))
            SAAT += N
        SAV += sav
        TUR += Qt
        kotlar[t] = float(opt.kot(Vn))
        V = Vn
    yil = T / 365.0
    return dict(Enerji_GWh=E / 1000.0 / yil, Gelir_MEUR=R / 1e6 / yil,
                Savak_m3s=SAV * 1e6 / (T * dt), Turbin_m3s=TUR / T,
                Calisma_h=SAAT / yil, Fiyat=R / max(E, 1e-9),
                Kot_min=float(kotlar.min()),
                Kot_p5=float(np.percentile(kotlar, 5)),
                Kot_ort=float(kotlar.mean()),
                Gun_720_alti=int((kotlar < 719.9).sum()))


def kur(D_t, Q, kot_min):
    opt.TUNEL_D, opt.TUNEL_L = D_t, 4600.0
    opt.Q_TASARIM = Q
    opt.CEBRI_D = float(np.sqrt(4.0 * Q / (np.pi * 5.0)))
    opt.CEBRI_L = 300.0
    opt.KOL_D = (2.0 / 3.9) * opt.CEBRI_D
    opt.KOT_MIN = kot_min
    opt.BASLANGIC_KOTU = kot_min
    opt.AMAC = "gelir"
    opt.yeniden_kur()


def main():
    kd = os.path.dirname(os.path.abspath(__file__))
    ptf, kaynak = opt.ptf_oku(os.path.join(kd, opt.PTF_DOSYASI))
    gf = GunlukFiyat(ptf)
    fse = opt.FiyatSureEgrisi(ptf)

    print("=" * 104)
    print("HEZİL HES — GÜNLÜK ZAMAN ADIMI ANALİZİ (minimum su kotu sorusu)")
    print("=" * 104)
    print(f"Fiyat verisi : {kaynak}")
    print(f"Aşama sayısı : {opt.AKIMLAR.shape[0]*365} gün "
          f"({opt.AKIMLAR.shape[0]} su yılı)")
    print(f"Ay içi CV    : " + ", ".join(f"{m}:{AYLIK_CV[m]*CV_CARPANI:.2f}"
                                         for m in range(1, 13)))
    print(f"AR(1) rho    : {AR1_RHO}\n")

    seriler = {tip: gunluk_akim(opt.AKIMLAR, tip) for tip in AKIM_TIPLERI}
    g = seriler["gunluk"][0]
    print(f"Üretilen günlük seri kontrolü:")
    print(f"   ortalama {g.mean():.2f} m³/s (aylık seri {opt.AKIMLAR.mean():.2f})")
    print(f"   en yüksek gün {g.max():.1f} m³/s | %99 dilim "
          f"{np.percentile(g,99):.1f} | %1 dilim {np.percentile(g,1):.2f}")
    print(f"   Q_tasarım=60 m³/s'yi aşan gün oranı %"
          f"{(g>60).mean()*100:.1f} (aylık seride %"
          f"{(opt.AKIMLAR>60).mean()*100:.1f})\n")

    kayit = []
    t0 = time.time()
    print(f"{'Konfigürasyon':<26}{'Akım':>8}{'MinKot':>7}{'Enerji':>9}{'Gelir':>8}"
          f"{'Savak':>7}{'Fiyat':>7}{'Çalışma':>8}{'UlaşKot':>8}{'<720g':>7}")
    print(f"{'':<26}{'':>8}{'m':>7}{'GWh/yıl':>9}{'M€':>8}{'m³/s':>7}"
          f"{'€/MWh':>7}{'h/yıl':>8}{'m':>8}{'gün':>7}")
    print("-" * 104)
    for ad, D_t, Q in KONFIGLER:
        for tip in AKIM_TIPLERI:
            q, aylar, gunler = seriler[tip]
            for km in MIN_KOTLAR:
                kur(D_t, Q, km)
                Vg, Qg, pq, pm = dp_gunluk(q, aylar, gunler, gf)
                r = sim_gunluk(Vg, Qg, pq, pm, q, aylar, gunler, gf)
                r.update(Konfig=ad, Tunel_D=D_t, Q_tasarim=Q, Akim=tip,
                         Min_kot=km, Aktif_hacim=round(opt.V_AKTIF, 1),
                         P_kurulu=round(opt.P_KURULU, 2))
                kayit.append(r)
                print(f"{ad:<26}{tip:>8}{km:7.0f}{r['Enerji_GWh']:9.2f}"
                      f"{r['Gelir_MEUR']:8.3f}{r['Savak_m3s']:7.2f}"
                      f"{r['Fiyat']:7.2f}{r['Calisma_h']:8.0f}"
                      f"{r['Kot_min']:8.1f}{r['Gun_720_alti']:7d}")
    print("-" * 104)
    print(f"{len(kayit)} günlük DP koşumu {time.time()-t0:.0f} saniyede tamamlandı.\n")

    t = pd.DataFrame(kayit)[[
        "Konfig", "Tunel_D", "Q_tasarim", "Akim", "Min_kot", "Aktif_hacim",
        "P_kurulu", "Enerji_GWh", "Gelir_MEUR", "Fiyat", "Savak_m3s",
        "Turbin_m3s", "Calisma_h", "Kot_min", "Kot_p5", "Kot_ort",
        "Gun_720_alti"]].round(3)

    # ---- minimum kotun etkisi ------------------------------------------------
    print("=" * 104)
    print("MİNİMUM SU KOTUNUN ETKİSİ — 720 m'ye göre gelir farkı [%]")
    print("=" * 104)
    print(f"   {'Konfigürasyon':<26}{'Akım':>9}" +
          "".join(f"{k:>10.0f} m" for k in MIN_KOTLAR))
    for ad, D_t, Q in KONFIGLER:
        for tip in AKIM_TIPLERI:
            s = t[(t["Konfig"] == ad) & (t["Akim"] == tip)]
            taban = float(s[s["Min_kot"] == 720.0]["Gelir_MEUR"].iloc[0])
            sat = "".join(
                f"{(float(s[s['Min_kot']==k]['Gelir_MEUR'].iloc[0])/taban-1)*100:>+11.2f}"
                for k in MIN_KOTLAR)
            print(f"   {ad:<26}{tip:>9}{sat}")

    print("\nAYLIK MODELLE KARŞILAŞTIRMA (aynı konfigürasyon, min kot 720 m)")
    print(f"   {'Konfigürasyon':<26}{'Model':>16}{'Enerji':>10}{'Gelir':>9}"
          f"{'Savak':>8}{'Fiyat':>8}")
    for ad, D_t, Q in KONFIGLER:
        kur(D_t, Q, 720.0)
        Vm, Qm, pqm, pmm, _ = opt.dp_coz(opt.AKIMLAR, fse, ilerleme=False)
        dfm = opt.ileri_simulasyon(Vm, Qm, pqm, pmm, opt.AKIMLAR, fse)
        ny = opt.AKIMLAR.shape[0]
        ay_E = dfm["Enerji_MWh"].sum() / 1000.0 / ny
        ay_G = dfm["Gelir"].sum() / 1e6 / ny
        ay_S = dfm["Savak_m3s"].mean()
        ay_F = dfm["Gelir"].sum() / max(dfm["Enerji_MWh"].sum(), 1e-9)
        print(f"   {ad:<26}{'AYLIK':>16}{ay_E:10.2f}{ay_G:9.3f}{ay_S:8.2f}{ay_F:8.2f}")
        for tip in AKIM_TIPLERI:
            s = t[(t["Konfig"] == ad) & (t["Akim"] == tip) &
                  (t["Min_kot"] == 720.0)].iloc[0]
            et = "GÜNLÜK (düz akım)" if tip == "duz" else "GÜNLÜK (değişken)"
            print(f"   {'':<26}{et:>16}{s['Enerji_GWh']:10.2f}"
                  f"{s['Gelir_MEUR']:9.3f}{s['Savak_m3s']:8.2f}{s['Fiyat']:8.2f}")

    # ---- grafik --------------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle("HEZİL HES — GÜNLÜK ZAMAN ADIMI: minimum su kotu sonucu değişir mi?",
                 fontsize=13, fontweight="bold")

    stil = {"duz": ("o-", "düz akım"), "gunluk": ("s--", "değişken akım")}
    renk = {KONFIGLER[0][0]: "#0969da", KONFIGLER[1][0]: "#cf222e"}

    for kolon, (sut, bas, yb) in enumerate([
            ("Gelir_MEUR", "Yıllık gelir", "Gelir [milyon EUR/yıl]"),
            ("Enerji_GWh", "Yıllık enerji", "Enerji [GWh/yıl]")]):
        a = ax[0, kolon]
        vals = []
        for ad, _, _ in KONFIGLER:
            for tip in AKIM_TIPLERI:
                s = t[(t["Konfig"] == ad) & (t["Akim"] == tip)
                      ].sort_values("Min_kot")
                a.plot(s["Min_kot"], s[sut], stil[tip][0], color=renk[ad],
                       label=f"{ad.split()[0]} · {stil[tip][1]}")
                vals.append(s[sut])
        a.set_title(f"{bas} — minimum su kotuna göre")
        a.set_xlabel("Minimum su kotu [m]"); a.set_ylabel(yb)
        v = np.concatenate([x.values for x in vals])
        a.set_ylim(v.min() - 0.06*(v.max()-v.min()), v.max() + 0.06*(v.max()-v.min()))
        a.legend(fontsize=8); a.grid(alpha=.3)

    a = ax[1, 0]
    for ad, _, _ in KONFIGLER:
        for tip in AKIM_TIPLERI:
            s = t[(t["Konfig"] == ad) & (t["Akim"] == tip)].sort_values("Min_kot")
            taban = float(s[s["Min_kot"] == 720.0]["Gelir_MEUR"].iloc[0])
            a.plot(s["Min_kot"], (s["Gelir_MEUR"] / taban - 1) * 100,
                   stil[tip][0], color=renk[ad],
                   label=f"{ad.split()[0]} · {stil[tip][1]}")
    a.axhline(0, color="#57606a", lw=1)
    a.set_title("720 m'ye göre gelir değişimi — sıfıra yakınsa minimum kotu\n"
                "indirmenin faydası yok demektir")
    a.set_xlabel("Minimum su kotu [m]"); a.set_ylabel("Gelir farkı [%]")
    a.legend(fontsize=8); a.grid(alpha=.3)

    a = ax[1, 1]
    x = np.arange(len(KONFIGLER)); w = 0.26
    etiket = ["AYLIK", "GÜNLÜK düz", "GÜNLÜK değişken"]
    renkler = ["#57606a", "#0969da", "#cf222e"]
    aylik_sav = []
    for ad, D_t, Q in KONFIGLER:
        kur(D_t, Q, 720.0)
        Vm, Qm, pqm, pmm, _ = opt.dp_coz(opt.AKIMLAR, fse, ilerleme=False)
        dfm = opt.ileri_simulasyon(Vm, Qm, pqm, pmm, opt.AKIMLAR, fse)
        aylik_sav.append(dfm["Savak_m3s"].mean())
    for j, (et, c) in enumerate(zip(etiket, renkler)):
        if j == 0:
            v = aylik_sav
        else:
            tip = "duz" if j == 1 else "gunluk"
            v = [float(t[(t["Konfig"] == ad) & (t["Akim"] == tip) &
                         (t["Min_kot"] == 720.0)]["Savak_m3s"].iloc[0])
                 for ad, _, _ in KONFIGLER]
        a.bar(x + (j - 1) * w, v, w, color=c, label=et)
        for i, y in enumerate(v):
            a.text(i + (j-1)*w, y, f"{y:.2f}", ha="center", va="bottom", fontsize=8)
    a.set_xticks(x)
    a.set_xticklabels([k[0].split()[0] + f"\nQ={k[2]:.1f} m³/s" for k in KONFIGLER],
                      fontsize=8)
    a.set_ylabel("Ortalama savaklanan debi [m³/s]")
    a.set_title("Zaman adımının SAVAKLAMA tahminine etkisi (min kot 720 m)")
    a.legend(fontsize=8); a.grid(alpha=.3, axis="y")

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    pg = os.path.join(kd, "hezil_gunluk_analiz.png")
    try:
        fig.savefig(pg, dpi=130)
    except PermissionError:
        pg = pg.replace(".png", f"_{time.strftime('%Y%m%d_%H%M%S')}.png")
        fig.savefig(pg, dpi=130)
    plt.close(fig)

    # ---- Excel ---------------------------------------------------------------
    girdi = pd.DataFrame([
        ("Zaman adımı", "gün", ""),
        ("Aşama sayısı", opt.AKIMLAR.shape[0] * 365, "gün"),
        ("Fiyat modeli", "her takvim günü için 24 saatlik fiyat-süre eğrisi", ""),
        ("Akım — 'duz'", "ay boyunca sabit (yalnız zaman adımı etkisi)", ""),
        ("Akım — 'gunluk'", "AR(1) log-normal, aylık hacim korunur", ""),
        ("AR(1) rho", AR1_RHO, "-"),
        ("CV çarpanı", CV_CARPANI, "-"),
        ("Ay içi CV", ", ".join(f"{m}:{AYLIK_CV[m]:.2f}" for m in range(1, 13)), ""),
        ("UYARI", "gözlenmiş günlük veri değildir; sentetik türetme", ""),
    ], columns=["Girdi", "Değer", "Birim"])

    px = os.path.join(kd, "hezil_gunluk_analiz.xlsx")

    def yaz(p):
        with pd.ExcelWriter(p, engine="openpyxl") as xw:
            girdi.to_excel(xw, sheet_name="Girdiler", index=False)
            t.to_excel(xw, sheet_name="Sonuçlar", index=False)
            for ws in xw.book.worksheets:
                for c in ws.columns:
                    w = max(len(str(x.value)) for x in c if x.value is not None)
                    ws.column_dimensions[c[0].column_letter].width = \
                        min(max(w + 2, 10), 40)
                ws.freeze_panes = "A2"

    try:
        yaz(px)
    except PermissionError:
        px = px.replace(".xlsx", f"_{time.strftime('%Y%m%d_%H%M%S')}.xlsx")
        yaz(px)

    print("\nÇIKTI DOSYALARI")
    print(f"   {px}")
    print(f"   {pg}")
    print("=" * 104)


if __name__ == "__main__":
    main()
