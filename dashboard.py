# -*- coding: utf-8 -*-
"""
================================================================================
HEZİL HES — İNTERAKTİF SONUÇ PANOSU (DASHBOARD)
================================================================================

alternatifler.py taramasının sonucunu (hezil_alternatifler.xlsx → "Tüm Senaryolar")
okur ve TEK DOSYALIK, BAĞIMLILIKSIZ bir HTML panosu üretir. Dosya çift tıkla
tarayıcıda açılır; internet, kütüphane veya sunucu gerekmez (veri HTML'in içine
gömülür, çizim saf SVG + JavaScript ile yapılır).

PANODA NE VAR
-------------
  · Dört senaryo ÇOKLU seçilebilir — üst üste bindirilerek karşılaştırılır
      S1 PİK·piyasa · S2 BANT·piyasa · S3 SABİT 88 €/MWh · S4 YEKDEM
  · X ve Y ekseni için seçilebilir 18 büyüklük (debi, çap, güç, enerji,
    yatırım, gelir, net fayda, F/M, birim maliyet, kayıp, verim …)
  · Serileri renklendirme: senaryo / tünel çapı / cebri boru hızı
  · Çizgi biçimi: en iyi zarf · alt seriler · sadece nokta
  · Tünel çapı ve cebri boru hızı için açılıp kapanabilen filtreler
  · Noktaların üzerine gelince tam konfigürasyon bilgisi
  · Seçili her senaryonun optimumu daire içine alınır ve kart olarak özetlenir
  · Gelir zinciri: brüt gelir → (−kesinti) → net gelir → (−sabit gider)
    → NİHAİ NET FAYDA
  · Alt tabloda filtrelenmiş alternatifler (çoklu seçimde senaryo sütunuyla);
    satıra tıklayınca grafikte işaretlenir

ÇIKTI : hezil_dashboard.html
================================================================================
"""

import os
import re
import sys
import glob
import json
import time
import pandas as pd

def _indirgeme_oku(varsayilan=0.12):
    """alternatifler.py'deki indirgeme oranını kaynaktan okur.

    Modül olarak ithal etmek optimzasyon.py'yi de yükleyip Excel girdilerini
    okutacağı için yalnızca sabitin yazıldığı satır aranır.
    """
    try:
        yol = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "alternatifler.py")
        with open(yol, encoding="utf-8") as f:
            m = re.search(r"^INDIRGEME_ORANI\s*=\s*([\d.]+)", f.read(), re.M)
        return float(m.group(1)) if m else varsayilan
    except Exception:
        return varsayilan


INDIRGEME_ORANI = _indirgeme_oku()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


SENARYOLAR = [
    {"kod": "S1", "ad": "PİK · piyasa", "renk": "#0969da",
     "aciklama": "Ömür boyu puant işletme · saatlik piyasa fiyatı",
     "isletme": "PİK"},
    {"kod": "S2", "ad": "BANT · piyasa", "renk": "#bf3989",
     "aciklama": "Ömür boyu enerji maksimizasyonu · ay ortalama fiyatı",
     "isletme": "BANT"},
    {"kod": "S3", "ad": "SABİT 88 €/MWh", "renk": "#1a7f37",
     "aciklama": "Ömür boyu sabit birim fayda · enerji maksimizasyonu",
     "isletme": "BANT"},
    {"kod": "S4", "ad": "YEKDEM", "renk": "#953800",
     "aciklama": "5 yıl 85 + 5 yıl 75 €/MWh (bant) → 40 yıl piyasa (pik)",
     "isletme": "BANT → PİK"},
]

# Panoda seçilebilecek büyüklükler.  "$" senaryo koduyla değiştirilir.
METRIKLER = [
    ("net",    "Net fayda",                "M€/yıl",  "$_net"),
    ("gelir",  "Yıllık NET gelir",         "M€/yıl",  "$_gelir"),
    ("brut",   "Yıllık BRÜT gelir",        "M€/yıl",  "$_brut"),
    ("enerji", "Yıllık enerji",            "GWh/yıl", "$_enerji"),
    ("fm",     "Fayda / masraf",           "-",       "$_fm"),
    ("bem",    "Birim enerji maliyeti",    "€/MWh",   "$_bem"),
    ("q",      "Tasarım debisi",           "m³/s",    "q"),
    ("dt",     "Tünel çapı",               "m",       "dt"),
    ("vt",     "Tünel hızı",               "m/s",     "vt"),
    ("dc",     "Cebri boru çapı",          "m",       "dc"),
    ("vc",     "Cebri boru hızı",          "m/s",     "vc"),
    ("km",     "Minimum su kotu",          "m",       "km"),
    ("vakt",   "Aktif hacim",              "hm³",     "vakt"),
    ("et",     "Cebri boru et kalınlığı",  "mm",      "et"),
    ("celik",  "Çelik ağırlığı",           "ton",     "celik"),
    ("pkur",   "Kurulu güç",               "MW",      "pkur"),
    ("yat",    "Toplam yatırım",           "M€",      "yat"),
    ("gid",    "Yıllık gider",             "M€/yıl",  "gid"),
    ("kayip",  "Yük kaybı",                "m",       "kayip"),
    ("rkot",   "RATED rezervuar kotu",     "m",       "rkot"),
    ("rnet",   "RATED net düşü",           "m",       "rnet"),
    ("rnet1",  "RATED net düşü — 1 ünite", "m",       "rnet1"),
    ("rnetB",  "RATED net düşü — bant",    "m",       "rnetB"),
    ("sisv",   "Sistem verimi",            "%",       "sisv"),
    ("reg",    "Regülasyon oranı",         "%",       "reg"),
]

RENK_TUNEL = {4.0: "#0969da", 4.4: "#2da44e", 4.8: "#bf3989",
              5.0: "#8250df", 5.2: "#953800", 5.6: "#cf222e", 6.0: "#1b7c83"}
RENK_VC = ["#0969da", "#1b7c83", "#2da44e", "#bf8700", "#953800", "#cf222e"]


DETAY_DOSYASI = "hezil_isletme_detay.json"

# İşletme çalışması artık pano_sunucu.py tarafından ANLIK çözülür; HTML'e seri
# gömmek gerekmez. Yine de sunucusuz (çift tıkla) kullanımda bir şeyler
# görünsün diye küçük bir çekirdek küme gömülebilir:
#   "yok"  → hiç gömme (en küçük dosya; işletme detayı yalnız sunucuyla)
#   "az"   → sadece dört senaryonun optimumu
#   "hepsi"→ isletme_detay.py'nin hesapladığı bütün konfigürasyonlar
DETAY_GOMME = "az"


def detay_oku(kd):
    """Gömülecek işletme serileri (sunucu yoksa yedek olarak kullanılır)."""
    bos = {"konfig": {}}
    y = os.path.join(kd, DETAY_DOSYASI)
    if DETAY_GOMME == "yok" or not os.path.exists(y):
        if DETAY_GOMME != "yok":
            print(f"!! {DETAY_DOSYASI} yok — sunucusuz yedek gömülmeyecek.")
        # meta bilgi (yıl, verim eğrisi …) sunucu yanıtını çizmek için gerekli
        if os.path.exists(y):
            with open(y, encoding="utf-8") as f:
                d = json.load(f)
            d["konfig"] = {}
            return d
        return bos
    with open(y, encoding="utf-8") as f:
        d = json.load(f)
    if DETAY_GOMME == "az":
        # yalnızca "… optimumu" gerekçesiyle hesaplananları tut
        d["konfig"] = {k: v for k, v in d["konfig"].items()
                       if any("optimum" in n for n in v.get("neden", []))}
    return d


def en_yeni_tarama(kd):
    ad = sorted(glob.glob(os.path.join(kd, "hezil_alternatifler*.xlsx")),
                key=os.path.getmtime)
    if not ad:
        raise SystemExit("Önce alternatifler.py çalıştırılmalı "
                         "(hezil_alternatifler*.xlsx bulunamadı)")
    return ad[-1]


def veri_hazirla(df):
    """DataFrame → panoya gömülecek kompakt kayıt listesi."""
    kayit = []
    for _, r in df.iterrows():
        d = {
            "dt": round(float(r["Tünel_D_m"]), 2),
            "vt": round(float(r["Tünel_hızı_m/s"]), 2),
            "q":  round(float(r["Q_tasarım_m3/s"]), 1),
            "dc": round(float(r["Cebri_D_m"]), 2),
            "vc": round(float(r["Cebri_hızı_m/s"]), 2),
            "km": round(float(r["Min_kot_m"]), 0),
            "vakt": round(float(r["Aktif_hacim_hm3"]), 2),
            "et": round(float(r["Cebri_et_mm"]), 1),
            "celik": round(float(r["Çelik_ağırlık_t"]), 0),
            "dkazi": round(float(r["Boru_tüneli_kazı_D_m"]), 2),
            "pkur": round(float(r["Kurulu_güç_MW"]), 2),
            "kayip": round(float(r["Yük_kaybı_m"]), 2),
            "rkot": round(float(r["Rated_rezervuar_kotu_m"]), 2),
            "rbrut": round(float(r["Rated_brüt_düşü_m"]), 2),
            "rnet": round(float(r["Rated_net_düşü_m"]), 2),
            "rnet1": round(float(r["Rated_net_düşü_1Ü_m"]), 2),
            "rnet2": round(float(r["Rated_net_düşü_2Ü_m"]), 2),
            "pay1": round(float(r["Tek_ünite_su_payı_%"]), 1),
            "rkotB": round(float(r["Rated_rezervuar_kotu_m_bant"]), 2),
            "rnetB": round(float(r["Rated_net_düşü_m_bant"]), 2),
            "rnet1B": round(float(r["Rated_net_düşü_1Ü_m_bant"]), 2),
            "rnet2B": round(float(r["Rated_net_düşü_2Ü_m_bant"]), 2),
            "sisv": round(float(r["Sistem_verimi_%"]), 2),
            "reg": round(float(r["Regülasyon_oranı_%"]), 1),
            "mtun": round(float(r["Tünel_maliyeti_MEUR"]), 3),
            "mceb": round(float(r["Cebri_maliyet_MEUR"]), 3),
            "mem": round(float(r["EM_maliyeti_MEUR"]), 3),
            "msan": round(float(r["Santral_şalt_MEUR"]), 3),
            "yat": round(float(r["Yatırım_MEUR"]), 3),
            "gid": round(float(r["Yıllık_gider_MEUR"]), 3),
        }
        for s in ("S1", "S2", "S3", "S4"):
            e = float(r[f"{s}_enerji_GWh"])
            d[f"{s}_enerji"] = round(e, 2)
            d[f"{s}_brut"] = round(float(r[f"{s}_brut_MEUR"]), 3)
            d[f"{s}_kes"] = round(float(r[f"{s}_kesinti_MEUR"]), 3)
            d[f"{s}_gelir"] = round(float(r[f"{s}_gelir_MEUR"]), 3)
            d[f"{s}_net"] = round(float(r[f"{s}_net_MEUR"]), 3)
            d[f"{s}_fm"] = round(float(r[f"{s}_F/M"]), 3)
            d[f"{s}_bem"] = round(d["gid"] * 1e6 / max(e * 1000.0, 1e-9), 2)
        kayit.append(d)
    return kayit


HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hezil HES — Alternatif Analiz Panosu</title>
<style>
  :root{
    --bg:#f6f8fa; --panel:#ffffff; --kenar:#d0d7de; --yazi:#1f2328;
    --soluk:#656d76; --vurgu:#0969da; --iyi:#1a7f37;
  }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#0d1117; --panel:#161b22; --kenar:#30363d; --yazi:#e6edf3;
           --soluk:#8b949e; --vurgu:#4493f8; --iyi:#3fb950; }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--yazi);
       font:14px/1.5 "Segoe UI",system-ui,-apple-system,sans-serif}
  header{padding:14px 20px;border-bottom:1px solid var(--kenar);
         background:var(--panel);position:sticky;top:0;z-index:20}
  h1{margin:0;font-size:17px;letter-spacing:.2px}
  .altbaslik{color:var(--soluk);font-size:12px;margin-top:2px}
  .sekmeler{display:flex;gap:6px;margin-top:12px;flex-wrap:wrap;align-items:center}
  .sekme{padding:7px 14px;border:2px solid var(--kenar);border-radius:7px;
         background:transparent;color:var(--soluk);cursor:pointer;font-size:13px;
         user-select:none}
  .sekme:hover{opacity:.85}
  .sekme.acik{color:#fff;font-weight:600}
  .ipucumetin{color:var(--soluk);font-size:11px;margin-left:6px}
  main{padding:16px 20px;display:grid;gap:16px;
       grid-template-columns:minmax(0,1fr) 310px}
  @media(max-width:1150px){main{grid-template-columns:minmax(0,1fr)}}
  .kutu{background:var(--panel);border:1px solid var(--kenar);border-radius:9px;
        padding:14px}
  .kutu h2{margin:0 0 10px;font-size:13px;text-transform:uppercase;
           letter-spacing:.6px;color:var(--soluk)}
  .kontroller{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end;
              margin-bottom:10px}
  label{display:block;font-size:11px;color:var(--soluk);margin-bottom:3px}
  select{padding:6px 8px;border:1px solid var(--kenar);border-radius:6px;
         background:var(--panel);color:var(--yazi);font-size:13px;min-width:150px}
  .filtre{display:flex;gap:5px;flex-wrap:wrap;margin-top:4px}
  .cip{padding:4px 9px;border:1px solid var(--kenar);border-radius:20px;
       cursor:pointer;font-size:12px;user-select:none;background:transparent;
       color:var(--soluk)}
  .cip.acik{color:#fff;font-weight:600;border-color:transparent}
  svg{width:100%;height:auto;display:block;overflow:visible}
  .eksen{stroke:var(--kenar)}
  .izgara{stroke:var(--kenar);opacity:.45;stroke-dasharray:3 3}
  .etiket{fill:var(--soluk);font-size:11px}
  .eksenad{fill:var(--yazi);font-size:12px;font-weight:600}
  .nokta{cursor:pointer}
  .nokta:hover{stroke:var(--yazi);stroke-width:2}
  #ipucu{position:fixed;pointer-events:none;background:var(--panel);
         border:1px solid var(--kenar);border-radius:7px;padding:9px 11px;
         font-size:12px;box-shadow:0 6px 20px rgba(0,0,0,.22);display:none;
         z-index:50;max-width:300px}
  #ipucu b{color:var(--vurgu)}
  #ipucu table{border-collapse:collapse;margin-top:5px;width:100%}
  #ipucu td{padding:1px 0}
  #ipucu td:first-child{color:var(--soluk);padding-right:10px}
  #ipucu td:last-child{text-align:right;font-variant-numeric:tabular-nums}
  .gosterge{display:flex;gap:16px;flex-wrap:wrap;margin:8px 0 2px;font-size:11px;
            color:var(--soluk)}
  .gosterge span{display:flex;align-items:center;gap:5px}
  .kart{border:1px solid var(--kenar);border-radius:8px;padding:11px;
        margin-bottom:9px}
  .kart .ad{font-weight:600;font-size:13px}
  .kart .not{color:var(--soluk);font-size:11px;margin:2px 0 8px}
  .kart table{width:100%;border-collapse:collapse;font-size:12px}
  .kart td{padding:2px 0}
  .kart td:first-child{color:var(--soluk)}
  .kart td:last-child{text-align:right;font-variant-numeric:tabular-nums;
                      font-weight:600}
  .buyuk{font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}
  table.veri{width:100%;border-collapse:collapse;font-size:12px;
             font-variant-numeric:tabular-nums}
  table.veri th{text-align:right;padding:6px 7px;border-bottom:2px solid var(--kenar);
                color:var(--soluk);font-size:11px;cursor:pointer;
                white-space:nowrap;position:sticky;top:0;background:var(--panel)}
  table.veri th:first-child,table.veri td:first-child{text-align:left}
  table.veri td{text-align:right;padding:5px 7px;
                border-bottom:1px solid var(--kenar)}
  table.veri tbody tr{cursor:pointer}
  table.veri tbody tr:hover{background:rgba(9,105,218,.09)}
  table.veri tbody tr.secili{background:rgba(9,105,218,.18);font-weight:600}
  .tablosar{max-height:430px;overflow:auto}
  .rozet{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;
         background:rgba(9,105,218,.14);color:var(--vurgu);font-weight:600}
  .aciklama{color:var(--soluk);font-size:11px;margin-top:8px;line-height:1.45}
  .snokta{display:inline-block;width:9px;height:9px;border-radius:50%}
  .detaySer{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:16px}
  @media(max-width:1150px){.detaySer{grid-template-columns:minmax(0,1fr)}}
  .detayIki{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:6px}
  @media(max-width:800px){.detayIki{grid-template-columns:1fr}}
  .dbaslik{fill:var(--yazi);font-size:12px;font-weight:600}
  .dugme{padding:8px 15px;border:1px solid var(--vurgu);border-radius:7px;
         background:var(--vurgu);color:#fff;font-size:13px;font-weight:600;
         cursor:pointer;font-family:inherit}
  .dugme:hover{opacity:.88}
  .dugme:disabled{opacity:.5;cursor:progress}
  .paketkutu{border:1px solid var(--iyi);border-radius:8px;padding:11px 13px;
             margin-top:10px;background:rgba(26,127,55,.08);font-size:12px}
  .paketkutu a{color:var(--vurgu);font-weight:600;text-decoration:none;
               margin-right:16px}
  .paketkutu a:hover{text-decoration:underline}
  .paketkutu table{border-collapse:collapse;margin-top:7px;width:100%}
  .paketkutu td{padding:1px 0;font-variant-numeric:tabular-nums}
  .paketkutu td:first-child{color:var(--soluk);padding-right:14px}
  .kutucuk{font-family:ui-monospace,Consolas,monospace;font-size:12px;
           background:rgba(127,127,127,.16);padding:2px 7px;border-radius:5px}
  .kopyala{padding:4px 10px;border:1px solid var(--kenar);border-radius:6px;
           background:transparent;color:var(--yazi);font-size:11px;cursor:pointer;
           font-family:inherit;margin-left:8px}
  .kopyala:hover{border-color:var(--vurgu);color:var(--vurgu)}
  .sabitkutu{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-end;
             border:1px solid var(--kenar);border-radius:9px;padding:10px 13px;
             margin-top:12px;background:rgba(130,80,223,.05)}
  .sabitkutu input[type=number]{width:110px;padding:5px 8px;font-size:13px;
             border:1px solid var(--kenar);border-radius:6px;
             background:var(--kart);color:var(--yazi);font-family:inherit}
  .onay{display:flex;align-items:center;gap:7px;font-size:13px;cursor:pointer;
        user-select:none;padding-bottom:5px}
  .onay input{width:15px;height:15px;accent-color:#8250df;cursor:pointer}
  .sabitnot{flex:1 1 100%;font-size:12px;line-height:1.65;color:var(--soluk);
            border-top:1px dashed var(--kenar);padding-top:8px;margin-top:2px}
  .sabitnot b{color:var(--yazi)}
  .degismedi{color:#1a7f37;font-weight:600}
  .kaydi{color:#cf222e;font-weight:600}
  .duyari{background:rgba(154,103,0,.12);border:1px solid rgba(154,103,0,.4);
          border-radius:7px;padding:9px 11px;font-size:12px;color:var(--yazi);
          margin-top:8px}
</style>
</head>
<body>
<header>
  <h1>Hezil Barajı ve HES — Alternatif Analiz Panosu</h1>
  <div class="altbaslik" id="ustbilgi"></div>
  <div class="sekmeler" id="sekmeler"></div>
</header>

<main>
  <div>
    <div class="kutu">
      <div class="kontroller">
        <div><label>Y ekseni</label><select id="ySec"></select></div>
        <div><label>X ekseni</label><select id="xSec"></select></div>
        <div><label>Renk / seri</label>
          <select id="seriSec">
            <option value="senaryo">Senaryo</option>
            <option value="dt">Tünel çapı</option>
            <option value="vc">Cebri boru hızı</option>
            <option value="km">Minimum su kotu</option>
            <option value="">— tek renk —</option>
          </select>
        </div>
        <div><label>Çizgi</label>
          <select id="cizgiSec">
            <option value="zarf">En iyi zarf (önerilen)</option>
            <option value="alt">Alt serilerle</option>
            <option value="yok">Sadece nokta</option>
          </select>
        </div>
      </div>
      <div class="sabitkutu">
        <div><label>Sabit maliyet (konfigürasyondan bağımsız)</label>
          <input type="number" id="sabitDeger" value="0" min="0" step="1"
                 placeholder="0"></div>
        <div><label>Girilen büyüklük</label>
          <select id="sabitTip">
            <option value="yat">Toplam yatırım [M€] → yıllığa indirgenir</option>
            <option value="yil">Doğrudan yıllık gider [M€/yıl]</option>
          </select></div>
        <label class="onay" for="sabitAcik">
          <input type="checkbox" id="sabitAcik">
          <span>Optimizasyon problemine dahil et</span></label>
        <label class="onay" for="elemeBC" title="Fizibilite eşiği: B/C &lt; 1 olan
alternatifler zarar ettirir; grafikten, tablodan ve optimum aramasından çıkarılır.">
          <input type="checkbox" id="elemeBC">
          <span>B/C &lt; 1 olanları ele <span id="elemeSayi"
                style="color:var(--soluk)"></span></span></label>
        <div><label>Sıralama ölçütü</label>
          <select id="olcutSec">
            <option value="net">Net fayda — maksimum</option>
            <option value="fm">Fayda / masraf oranı — maksimum</option>
          </select></div>
        <div class="sabitnot" id="sabitNot"></div>
      </div>

      <div style="display:flex;gap:22px;flex-wrap:wrap">
        <div><label>Tünel çapı filtresi</label><div class="filtre" id="fDt"></div></div>
        <div><label>Cebri boru hızı filtresi</label><div class="filtre" id="fVc"></div></div>
        <div><label>Minimum su kotu filtresi</label><div class="filtre" id="fKm"></div></div>
      </div>
      <div class="gosterge" id="gosterge"></div>
      <svg id="grafik" viewBox="0 0 900 470" preserveAspectRatio="xMidYMid meet"></svg>
      <div class="aciklama" id="grafikNot"></div>
    </div>

    <div class="kutu" id="detayKutu" style="margin-top:16px;display:none">
      <h2>İşletme çalışması <span class="rozet" id="detayBaslik"></span></h2>
      <label>Senaryo — düğmeye basınca o senaryonun işletmesi ve kartı gelir</label>
      <div class="sekmeler" id="dSekme" style="margin:4px 0 12px"></div>
      <div class="kontroller">
        <div><label>İşletme biçimi</label>
          <select id="dAmac">
            <option value="gelir">PİK — gelir maksimizasyonu</option>
            <option value="enerji">BANT — enerji maksimizasyonu</option>
          </select></div>
        <div><label>Gösterilen dönem</label><select id="dYil"></select></div>
        <div class="aciklama" style="margin:0;max-width:430px" id="dNeden"></div>
        <div id="dDurum" class="rozet" style="display:none"></div>
        <div style="margin-left:auto">
          <label>Türbin imalatçısı</label>
          <button id="dPaket" class="dugme">📐 İmalatçı paketi üret</button>
          <button id="dKesit" class="dugme"
                  style="background:#8250df;border-color:#8250df;margin-left:6px">
            🏗 Gövde en kesiti</button>
        </div>
      </div>
      <div class="detaySer">
        <div>
          <svg id="dG1" viewBox="0 0 900 320" preserveAspectRatio="xMidYMid meet"></svg>
          <div class="detayIki">
            <svg id="dG2" viewBox="0 0 440 340" preserveAspectRatio="xMidYMid meet"></svg>
            <svg id="dG3" viewBox="0 0 440 340" preserveAspectRatio="xMidYMid meet"></svg>
          </div>
          <div id="dPaketSonuc"></div>
        </div>
        <div id="dKart"></div>
      </div>
    </div>

    <div class="kutu" style="margin-top:16px">
      <h2>Filtrelenmiş alternatifler <span class="rozet" id="satirSayi"></span></h2>
      <div class="tablosar"><table class="veri" id="tablo"></table></div>
    </div>
  </div>

  <aside>
    <div class="kutu">
      <h2>Seçili senaryoların optimumu</h2>
      <div id="optKart"></div>
    </div>
  </aside>
</main>

<div id="ipucu"></div>

<script>
const VERI = __VERI__;
const SENARYOLAR = __SENARYOLAR__;
const METRIKLER = __METRIKLER__;
const RENK_TUNEL = __RENK_TUNEL__;
const RENK_VC = __RENK_VC__;
const URETIM = __URETIM__;
const DETAY = __DETAY__;

/* Çoklu senaryo seçimi: en az bir senaryo daima açık kalır. */
let secSen = new Set(["S1"]);
let yMet = "net", xMet = "q", seriAlan = "senaryo", cizgi = "zarf";
let kapaliDt = new Set(), kapaliVc = new Set(), kapaliKm = new Set();
let secili = null;                       /* {d, s} */
let dAmac = "gelir", dYil = "hepsi";
let dSen = null;          /* detay bölümünde gösterilen senaryo */
let dAmacElle = false;    /* işletme biçimi elle mi seçildi */

/* ---------- sabit (konfigürasyondan bağımsız) maliyet -------------------
   Böyle bir maliyet bütün alternatiflere AYNI miktarda eklenir; net fayda
   eğrisini sabit bir miktar aşağı kaydırır, eğimini değiştirmez.  Bu yüzden
   NET FAYDA ölçütünde optimumu kaydırması matematiksel olarak imkânsızdır
   (d/dx sabit = 0).  Buna karşılık FAYDA/MASRAF bir ORAN olduğundan paydaya
   giren sabit terim sıralamayı değiştirebilir; fizibilite eşiğini de
   (kaç alternatifin kârlı kaldığını) doğrudan etkiler.               */
const INDIRGEME = __INDIRGEME__;
let sabitDeger = 0, sabitTip = "yat", sabitAcik = false, olcut = "net";
/* Fizibilite süzgeci: B/C < 1 olan (zarar ettiren) alternatifleri eler.
   B/C'nin geçerli tek kullanımı budur — eşik sınavı, seçim ölçütü değil.
   Eleme SENARYOYA BAĞLIDIR: bir konfigürasyon S4'te fizibl olup S1'de
   olmayabilir, bu yüzden konfigürasyon değil NOKTA bazında uygulanır. */
let elemeBC = false;

/* seçili sabit maliyetin YILLIK karşılığı [M€/yıl] */
const sabitYil = () => !sabitAcik || !(sabitDeger > 0) ? 0
      : (sabitTip === "yat" ? sabitDeger * INDIRGEME : sabitDeger);
/* sabit maliyetin YATIRIM karşılığı [M€] */
const sabitYat = () => !sabitAcik || !(sabitDeger > 0) ? 0
      : (sabitTip === "yat" ? sabitDeger : sabitDeger / INDIRGEME);

/* Sabit maliyetle düzeltilmiş büyüklükler — her yerde bunlar kullanılır. */
const gGid = d => d.gid + sabitYil();
const gYat = d => d.yat + sabitYat();
const gNet = (d, s) => d[s + "_net"] - sabitYil();
const gFm  = (d, s) => d[s + "_gelir"] / gGid(d);
const gBem = (d, s) => gGid(d) * 1e6 / Math.max(d[s + "_enerji"] * 1000, 1e-9);

const $ = s => document.querySelector(s);
const met = m => METRIKLER.find(x => x[0] === m);
const alan = (m, s) => met(m)[3].replace("$", s);
/* Nokta = konfigürasyon (d) × senaryo (s) çifti.
   Sabit maliyetten etkilenen dört büyüklük yeniden hesaplanır. */
function deger(p, m){
  if (sabitYil()){
    if (m === "net")   return gNet(p.d, p.s);
    if (m === "fm")    return gFm(p.d, p.s);
    if (m === "bem")   return gBem(p.d, p.s);
    if (m === "gid")   return gGid(p.d);
    if (m === "yat")   return gYat(p.d);
  }
  return p.d[alan(m, p.s)];
}
const senBilgi = k => SENARYOLAR.find(x => x.kod === k);
const sayi = (v, n) => (v === undefined || v === null || isNaN(v)) ? "–"
      : Number(v).toLocaleString("tr-TR", {minimumFractionDigits: n,
                                           maximumFractionDigits: n});
const KESIK = ["", "7 3", "2 3", "10 3 2 3"];   /* senaryo başına çizgi deseni */

const capListesi = [...new Set(VERI.map(d => d.dt))].sort((a, b) => a - b);
const vcListesi  = [...new Set(VERI.map(d => d.vc))].sort((a, b) => a - b);
const kmListesi  = [...new Set(VERI.map(d => d.km))].sort((a, b) => a - b);
const RENK_KM = ["#0969da","#1b7c83","#2da44e","#bf8700","#953800","#cf222e","#8250df"];
const renkKm = v => RENK_KM[kmListesi.indexOf(v) % RENK_KM.length];
const renkVc = v => RENK_VC[vcListesi.indexOf(v) % RENK_VC.length];
/* JSON anahtarları "4.0" biçiminde; JS sayı indeksi 4.0'ı "4" yapacağı için
   arama daima toFixed(1) ile yapılır. */
const renkDt = v => RENK_TUNEL[Number(v).toFixed(1)] || "#888";
const sirali = () => SENARYOLAR.filter(s => secSen.has(s.kod));
const kesikli = k => KESIK[SENARYOLAR.findIndex(s => s.kod === k) % KESIK.length];

function renk(p){
  if (seriAlan === "senaryo") return senBilgi(p.s).renk;
  if (seriAlan === "dt") return renkDt(p.d.dt);
  if (seriAlan === "vc") return renkVc(p.d.vc);
  if (seriAlan === "km") return renkKm(p.d.km);
  return "#0969da";
}
function seriAnahtar(p){
  if (seriAlan === "senaryo") return p.s;
  if (seriAlan === "dt") return p.s + "|" + p.d.dt;
  if (seriAlan === "vc") return p.s + "|" + p.d.vc;
  if (seriAlan === "km") return p.s + "|" + p.d.km;
  return p.s;
}

function konfigSuz(){
  return VERI.filter(d => !kapaliDt.has(d.dt) && !kapaliVc.has(d.vc)
                          && !kapaliKm.has(d.km));
}
/* B/C >= 1 mi?  Süzgeç kapalıyken her nokta geçerlidir. */
const fizibl = (d, s) => !elemeBC || gFm(d, s) >= 1;
function noktalar(){
  const k = konfigSuz(), r = [];
  sirali().forEach(s => k.forEach(d => {
    if (fizibl(d, s.kod)) r.push({d: d, s: s.kod});
  }));
  return r;
}
/* Süzgecin kaç noktayı elediği — etikette gösterilir */
function elenenSayi(){
  const k = konfigSuz(), ss = sirali();
  let n = 0;
  ss.forEach(s => k.forEach(d => { if (gFm(d, s.kod) < 1) n++; }));
  return {elenen: n, toplam: k.length * ss.length};
}
/* Seçili ölçüte göre alternatifin başarım değeri (büyük = iyi) */
function olcutDeger(d, kod){
  return olcut === "fm" ? gFm(d, kod) : gNet(d, kod);
}
function optimum(kod, kume){
  return (kume || konfigSuz())
    .filter(d => fizibl(d, kod))
    .reduce((e, d) => (e === null || olcutDeger(d, kod) > olcutDeger(e, kod))
            ? d : e, null);
}
/* Sabit maliyet YOK sayıldığında bulunan optimum — karşılaştırma için */
function optimumSabitsiz(kod, kume){
  const eski = [sabitAcik, sabitDeger];
  sabitAcik = false; sabitDeger = 0;
  const o = optimum(kod, kume);
  [sabitAcik, sabitDeger] = eski;
  return o;
}
const konfigAdi = d => d === null ? "–"
  : `D=${sayi(d.dt,1)} · Q=${sayi(d.q,1)} · v_c=${sayi(d.vc,1)} · kot ${sayi(d.km,0)}`;

/* ---------- kurulum ---------- */
function kurSekmeler(){
  $("#sekmeler").innerHTML = SENARYOLAR.map(s => {
    const a = secSen.has(s.kod);
    return `<span class="sekme${a ? " acik" : ""}" data-k="${s.kod}"
      style="border-color:${s.renk};${a ? "background:" + s.renk : ""}">
      ${s.kod} · ${s.ad}</span>`;
  }).join("") +
  `<span class="ipucumetin">↑ birden çok senaryo seçilebilir
     (en az biri açık kalmalı)</span>`;
  document.querySelectorAll(".sekme").forEach(b => b.onclick = () => {
    const k = b.dataset.k;
    if (secSen.has(k)){ if (secSen.size > 1) secSen.delete(k); }
    else secSen.add(k);
    sirala = null; siraTers = true;
    kurSekmeler(); ciz();
  });
  const ss = sirali();
  $("#ustbilgi").textContent = `${VERI.length} alternatif × ${ss.length} senaryo `
    + `= ${VERI.length * ss.length} nokta · `
    + (ss.length === 1 ? ss[0].aciklama : ss.map(s => s.kod).join(" + "))
    + ` · ${URETIM}`;
}
function kurSecimler(){
  const opsiyon = m => METRIKLER.map(x =>
    `<option value="${x[0]}"${x[0] === m ? " selected" : ""}>${x[1]} [${x[2]}]</option>`
  ).join("");
  $("#ySec").innerHTML = opsiyon(yMet);
  $("#xSec").innerHTML = opsiyon(xMet);
  $("#seriSec").value = seriAlan;
  $("#cizgiSec").value = cizgi;
  $("#sabitDeger").value = sabitDeger;
  $("#sabitTip").value = sabitTip;
  $("#sabitAcik").checked = sabitAcik;
  $("#olcutSec").value = olcut;
  $("#sabitDeger").oninput = e => {
    sabitDeger = parseFloat(e.target.value) || 0; ciz(); };
  $("#sabitTip").onchange = e => { sabitTip = e.target.value; ciz(); };
  $("#sabitAcik").onchange = e => { sabitAcik = e.target.checked; ciz(); };
  $("#olcutSec").onchange = e => { olcut = e.target.value; ciz(); };
  $("#elemeBC").checked = elemeBC;
  $("#elemeBC").onchange = e => { elemeBC = e.target.checked; ciz(); };
  $("#ySec").onchange = e => { yMet = e.target.value; ciz(); };
  $("#xSec").onchange = e => { xMet = e.target.value; ciz(); };
  $("#seriSec").onchange = e => { seriAlan = e.target.value; ciz(); };
  $("#cizgiSec").onchange = e => { cizgi = e.target.value; ciz(); };

  $("#fDt").innerHTML = capListesi.map(v =>
    `<span class="cip acik" data-t="dt" data-v="${v}"
       style="background:${renkDt(v)}">${v.toFixed(1)} m</span>`).join("");
  $("#fVc").innerHTML = vcListesi.map(v =>
    `<span class="cip acik" data-t="vc" data-v="${v}"
       style="background:${renkVc(v)}">${v.toFixed(1)} m/s</span>`).join("");
  $("#fKm").innerHTML = kmListesi.map(v =>
    `<span class="cip acik" data-t="km" data-v="${v}"
       style="background:${renkKm(v)}">${v.toFixed(0)} m</span>`).join("");
  document.querySelectorAll(".cip").forEach(c => c.onclick = () => {
    const kume = c.dataset.t === "dt" ? kapaliDt
                 : c.dataset.t === "vc" ? kapaliVc : kapaliKm;
    const v = parseFloat(c.dataset.v);
    if (kume.has(v)){ kume.delete(v); c.classList.add("acik");
      c.style.background = c.dataset.t === "dt" ? renkDt(v)
                           : c.dataset.t === "vc" ? renkVc(v) : renkKm(v);
    } else { kume.add(v); c.classList.remove("acik"); c.style.background = "transparent"; }
    ciz();
  });
}

/* ---------- grafik ---------- */
function ciz(){
  const G = {sol: 76, sag: 22, ust: 18, alt: 54}, W = 900, H = 470;
  const gw = W - G.sol - G.sag, gh = H - G.ust - G.alt;
  const nk = noktalar();
  const svg = $("#grafik");
  gostergeCiz();
  sabitNotCiz();          /* her çizimde sabit maliyet açıklaması tazelenir */
  if (!nk.length){ svg.innerHTML =
      `<text x="450" y="230" text-anchor="middle" class="etiket">${elemeBC
        ? "B/C &#8805; 1 koşulunu sağlayan alternatif yok — proje fizibl değil"
        : "Filtreler tüm alternatifleri gizliyor"}</text>`;
    $("#satirSayi").textContent = "0 kayıt"; $("#tablo").innerHTML = "";
    optKartCiz(); return; }

  const xs = nk.map(p => deger(p, xMet)), ys = nk.map(p => deger(p, yMet));
  const genislet = (a, b) => { const r = (b - a) || Math.abs(b) * .1 || 1;
                               return [a - r * .07, b + r * .07]; };
  const [x0, x1] = genislet(Math.min(...xs), Math.max(...xs));
  const [y0, y1] = genislet(Math.min(...ys), Math.max(...ys));
  const X = v => G.sol + (v - x0) / (x1 - x0) * gw;
  const Y = v => G.ust + gh - (v - y0) / (y1 - y0) * gh;

  /* Eksen işaretleri: ondalık basamak ADIMDAN türetilir, böylece bir eksendeki
     bütün etiketler aynı biçimde yazılır. */
  const isaret = (a, b) => {
    const ham = (b - a) / 6, us = Math.pow(10, Math.floor(Math.log10(ham)));
    const n = ham / us, adim = us * (n >= 5 ? 5 : n >= 2 ? 2 : 1);
    const r = [];
    for (let v = Math.ceil(a / adim) * adim; v <= b + adim * 1e-9; v += adim) r.push(v);
    return {deger: r, ond: Math.max(0, Math.min(3, -Math.floor(Math.log10(adim))))};
  };

  let p = "";
  const iy = isaret(y0, y1), ix = isaret(x0, x1);
  iy.deger.forEach(v => {
    p += `<line class="izgara" x1="${G.sol}" y1="${Y(v)}" x2="${W - G.sag}" y2="${Y(v)}"/>`;
    p += `<text class="etiket" x="${G.sol - 9}" y="${Y(v) + 4}"
            text-anchor="end">${sayi(v, iy.ond)}</text>`;
  });
  ix.deger.forEach(v => {
    p += `<line class="izgara" x1="${X(v)}" y1="${G.ust}" x2="${X(v)}" y2="${G.ust + gh}"/>`;
    p += `<text class="etiket" x="${X(v)}" y="${G.ust + gh + 19}"
            text-anchor="middle">${sayi(v, ix.ond)}</text>`;
  });
  p += `<line class="eksen" x1="${G.sol}" y1="${G.ust + gh}" x2="${W - G.sag}" y2="${G.ust + gh}"/>`;
  p += `<line class="eksen" x1="${G.sol}" y1="${G.ust}" x2="${G.sol}" y2="${G.ust + gh}"/>`;
  const my = met(yMet), mx = met(xMet);
  p += `<text class="eksenad" x="${G.sol + gw / 2}" y="${H - 12}"
          text-anchor="middle">${mx[1]} [${mx[2]}]</text>`;
  p += `<text class="eksenad" transform="translate(16,${G.ust + gh / 2}) rotate(-90)"
          text-anchor="middle">${my[1]} [${my[2]}]</text>`;

  /* Çizgiler
       zarf → her seride aynı X'teki noktalardan EN İYİSİ birleştirilir
       alt  → seri + ikincil boyutla gruplanır (dikey zikzak oluşmaz)
       yok  → yalnız nokta
     Çizgi deseni daima SENARYOYU gösterir. */
  if (cizgi !== "yok"){
    const ikincil = seriAlan === "dt" ? "vc" : seriAlan === "vc" ? "dt"
                  : seriAlan === "km" ? "dt" : "vc";
    const grup = {};
    nk.forEach(pt => {
      const k = cizgi === "zarf" ? seriAnahtar(pt)
                                 : seriAnahtar(pt) + "|" + pt.d[ikincil];
      (grup[k] ||= []).push(pt);
    });
    Object.values(grup).forEach(g => {
      let n = g;
      if (cizgi === "zarf"){
        const eni = {};
        g.forEach(pt => {
          const x = deger(pt, xMet);
          if (!(x in eni) || deger(pt, yMet) > deger(eni[x], yMet)) eni[x] = pt;
        });
        n = Object.values(eni);
      }
      if (n.length < 2) return;
      n.sort((a, b) => deger(a, xMet) - deger(b, xMet));
      const dd = n.map((pt, i) => (i ? "L" : "M") + X(deger(pt, xMet)).toFixed(1)
                                  + "," + Y(deger(pt, yMet)).toFixed(1)).join(" ");
      p += `<path d="${dd}" fill="none" stroke="${renk(n[0])}"
              stroke-width="${cizgi === "zarf" ? 2.2 : 1.2}"
              stroke-dasharray="${kesikli(n[0].s)}"
              opacity="${cizgi === "zarf" ? .9 : .4}"/>`;
    });
  }

  nk.forEach((pt, i) => {
    const sec = secili && secili.d === pt.d && secili.s === pt.s;
    if (dYerel(pt.d, "gelir") && !sec)
      p += `<circle cx="${X(deger(pt, xMet)).toFixed(1)}"
              cy="${Y(deger(pt, yMet)).toFixed(1)}" r="8" fill="none"
              stroke="${renk(pt)}" stroke-width="1" opacity=".55"/>`;
    p += `<circle class="nokta" cx="${X(deger(pt, xMet)).toFixed(1)}"
            cy="${Y(deger(pt, yMet)).toFixed(1)}" r="${sec ? 7 : 4.2}"
            fill="${renk(pt)}" data-i="${i}"
            ${sec ? 'stroke="var(--yazi)" stroke-width="2"' : ""}/>`;
  });

  /* Seçili her senaryonun optimumu kendi renginde halkalanır */
  const kf = konfigSuz();
  sirali().forEach(s => {
    const o = optimum(s.kod, kf);
    if (!o) return;
    const pt = {d: o, s: s.kod};
    p += `<circle cx="${X(deger(pt, xMet)).toFixed(1)}"
            cy="${Y(deger(pt, yMet)).toFixed(1)}" r="11" fill="none"
            stroke="${s.renk}" stroke-width="2.4"/>`;
  });

  svg.innerHTML = p;
  svg.querySelectorAll(".nokta").forEach(c => {
    const pt = nk[+c.dataset.i];
    c.onmousemove = e => ipucuGoster(e, pt);
    c.onmouseleave = () => $("#ipucu").style.display = "none";
    c.onclick = () => { secili = pt; ciz(); };
  });

  detayCiz();
  $("#grafikNot").textContent =
    `Halkalar: her senaryonun kendi renginde optimumu. Noktaya tıklayınca alt `
    + `tabloda işaretlenir. ${nk.length} nokta gösteriliyor `
    + (elemeBC ? `(${kf.length} konfigürasyon × ${sirali().length} senaryo `
                 + `içinden B/C ≥ 1 olanlar). `
               : `(${kf.length} konfigürasyon × ${sirali().length} senaryo). `)
    + (SUNUCU === false
        ? `İnce halkalı noktaların işletme çalışması gömülü — tıklayınca açılır.`
        : `Herhangi bir noktaya tıklayın: işletme çalışması sunucuda çözülür `
          + `(ince halkalılar önbellekte hazır).`);
  optKartCiz(); tabloCiz();
}

function gostergeCiz(){
  const ss = sirali();
  let h = ss.map(s =>
    `<span><span class="snokta" style="background:${s.renk}"></span>
       ${s.kod} ${s.ad}</span>`).join("");
  if (ss.length > 1 && seriAlan !== "senaryo")
    h += `<span style="opacity:.8">renk = ${seriAlan === "dt" ? "tünel çapı"
          : seriAlan === "vc" ? "cebri boru hızı"
          : seriAlan === "km" ? "minimum su kotu" : "tek renk"},
          çizgi deseni = senaryo</span>`;
  $("#gosterge").innerHTML = h;
}

function ipucuGoster(e, pt){
  const d = pt.d, s = senBilgi(pt.s), t = $("#ipucu");
  const sat = (a, b) => `<tr><td>${a}</td><td>${b}</td></tr>`;
  t.innerHTML = `<b>Tünel ${sayi(d.dt,1)} m · Q ${sayi(d.q,1)} m³/s</b>
    <div style="color:${s.renk};font-weight:600;font-size:11px">
      ${s.kod} · ${s.ad}</div>
    <table>
    ${sat("Tünel hızı", sayi(d.vt,2) + " m/s")}
    ${sat("Cebri boru", sayi(d.dc,2) + " m @ " + sayi(d.vc,1) + " m/s")}
    ${sat("Et kalınlığı / çelik", sayi(d.et,1) + " mm · " + sayi(d.celik,0) + " t")}
    ${sat("Boru tüneli kazı", sayi(d.dkazi,2) + " m")}
    ${sat("Minimum su kotu", sayi(d.km,0) + " m · aktif " + sayi(d.vakt,1) + " hm³")}
    ${sat("Kurulu güç", sayi(d.pkur,2) + " MW")}
    ${sat("Yük kaybı", sayi(d.kayip,2) + " m")}
    ${sat("RATED kot / net düşü", sayi(d.rkot,1) + " m · " + sayi(d.rnet,1) + " m")}
    ${sat("Sistem verimi", sayi(d.sisv,2) + " %")}
    ${sat("Yatırım", sayi(gYat(d),3) + " M€" + (sabitYat() ? " (sabit dahil)" : ""))}
    ${sat("Yıllık gider", sayi(gGid(d),3) + " M€")}
    ${sat("Enerji", sayi(d[pt.s+"_enerji"],2) + " GWh/yıl")}
    ${sat("Brüt gelir", sayi(d[pt.s+"_brut"],3) + " M€/yıl")}
    ${sat("− kesinti", sayi(d[pt.s+"_kes"],3) + " M€/yıl")}
    ${sat("Net gelir", sayi(d[pt.s+"_gelir"],3) + " M€/yıl")}
    ${sabitYil() ? sat("− sabit maliyet", sayi(sabitYil(),3) + " M€/yıl") : ""}
    ${sat("<b>Net fayda</b>", "<b>" + sayi(gNet(d,pt.s),3) + " M€/yıl</b>")}
    ${sat("Fayda/masraf", sayi(gFm(d,pt.s),3))}
    </table>`;
  t.style.display = "block";
  const g = t.getBoundingClientRect();
  t.style.left = Math.min(e.clientX + 16, innerWidth - g.width - 12) + "px";
  t.style.top  = Math.min(e.clientY + 16, innerHeight - g.height - 12) + "px";
}

/* Anma (rated) değerleri senaryonun İŞLETME BİÇİMİNDEN gelir:
     S1 → pik · S2, S3 → bant · S4 → 1–10. yıl bant, 11–50. yıl pik      */
function dRated(o, kod){
  const sat = (a, b) => `<tr><td>${a}</td><td>${b}</td></tr>`;
  const P = k => sayi(o[k], 2) + " m", B = k => sayi(o[k + "B"], 2) + " m";
  if (kod === "S4")
    return sat("RATED rezervuar kotu", `${sayi(o.rkotB,1)} → ${sayi(o.rkot,1)} m`)
         + sat("RATED net düşü", `${sayi(o.rnetB,1)} → ${sayi(o.rnet,1)} m`)
         + sat("&nbsp;&nbsp;· 1 ünite", `${sayi(o.rnet1B,1)} → ${sayi(o.rnet1,1)} m`)
         + sat("&nbsp;&nbsp;· 2 ünite", `${sayi(o.rnet2B,1)} → ${sayi(o.rnet2,1)} m`)
         + sat("<i>1–10. yıl (bant) → 11–50. yıl (pik)</i>", "");
  const b = (kod === "S2" || kod === "S3");
  return sat("RATED rezervuar kotu", b ? B("rkot") : P("rkot"))
       + sat("RATED brüt düşü", b ? sayi(o.rkotB - 574, 2) + " m" : P("rbrut"))
       + sat("RATED net düşü", b ? B("rnet") : P("rnet"))
       + sat("&nbsp;&nbsp;· 1 ünite işletmesinde", b ? B("rnet1") : P("rnet1"))
       + sat("&nbsp;&nbsp;· 2 ünite işletmesinde", b ? B("rnet2") : P("rnet2"))
       + sat("&nbsp;&nbsp;· tek ünitenin su payı", sayi(o.pay1,1) + " %");
}

/* Sabit maliyetin optimumu kaydırıp kaydırmadığını canlı gösterir. */
function sabitNotCiz(){
  const C = sabitYil(), kf = konfigSuz(), ss = sirali();
  const el = $("#sabitNot");
  /* süzgeç etiketi — her çizimde tazelenir */
  const es = elenenSayi();
  $("#elemeSayi").textContent = es.elenen
    ? `(${es.elenen}/${es.toplam} nokta)` : "(eleyecek nokta yok)";
  const eleNot = !elemeBC ? "" :
    `<div style="margin-top:6px;padding-top:6px;border-top:1px dashed var(--kenar)">
       <b>Fizibilite süzgeci açık.</b> B/C &lt; 1 olan
       <b>${es.elenen}</b> nokta grafikten, tablodan ve optimum aramasından
       çıkarıldı; <b>${es.toplam - es.elenen}</b> nokta kaldı.
       ${es.elenen === es.toplam
         ? " <span class=\"kaydi\">Hiçbir alternatif eşiği geçmiyor — "
           + "bu koşullarda proje fizibl değil.</span>" : ""}
       <span style="font-style:italic">Eleme bir eşik sınavıdır; kalanlar
       arasında seçim yine net faydaya göre yapılır.</span></div>`;
  if (!C){
    el.innerHTML = (sabitAcik && sabitDeger <= 0
      ? "Sabit maliyet <b>0</b> girildi — etkisiz."
      : "Sabit maliyet <b>devre dışı</b>. Bir tutar girip kutucuğu "
        + "işaretleyin; net fayda ve fayda/masraf ölçütleri için optimumun "
        + "kayıp kaymadığı burada karşılaştırmalı gösterilir.") + eleNot;
    return;
  }
  const bas = sabitTip === "yat"
    ? `Sabit yatırım <b>${sayi(sabitDeger,1)} M€</b> × ${INDIRGEME} = `
      + `<b>${sayi(C,3)} M€/yıl</b>`
    : `Sabit yıllık gider <b>${sayi(C,3)} M€/yıl</b> `
      + `(≈ ${sayi(sabitYat(),1)} M€ yatırım)`;
  const satirlar = ss.map(sn => {
    const k = sn.kod;
    /* Karşılaştırma sabit maliyetin optimumu kaydırıp kaydırmadığını ölçer;
       fizibilite süzgeci ayrı bir etki olduğu için burada devre dışı bırakılır
       (elenen nokta sayısı aşağıda ayrıca raporlanıyor). */
    const es = [sabitAcik, sabitDeger, olcut, elemeBC];
    elemeBC = false;
    olcut = "net"; const oN0 = optimumSabitsiz(k, kf), oN1 = optimum(k, kf);
    olcut = "fm";  const oF0 = optimumSabitsiz(k, kf), oF1 = optimum(k, kf);
    [sabitAcik, sabitDeger, olcut, elemeBC] = es;
    const karli = kf.filter(d => gNet(d, k) > 0).length;
    const et = (a, b) => (a === null || b === null)
      ? `<span class="kaydi">fizibl alternatif yok</span>`
      : a === b
      ? `<span class="degismedi">DEĞİŞMEDİ</span> — ${konfigAdi(b)}`
      : `<span class="kaydi">KAYDI</span> — ${konfigAdi(a)} → ${konfigAdi(b)}`;
    return `<div style="margin-top:5px">
      <b style="color:${sn.renk}">${k}</b> ·
      net fayda ölçütü: ${et(oN0, oN1)} &nbsp;|&nbsp;
      F/M ölçütü: ${et(oF0, oF1)} &nbsp;|&nbsp;
      kârlı kalan: <b>${karli}/${kf.length}</b></div>`;
  }).join("");
  el.innerHTML = bas
    + ` bütün alternatiflere eşit eklendi. Etkin ölçüt: `
    + `<b>${olcut === "fm" ? "fayda/masraf" : "net fayda"}</b>.`
    + satirlar
    + `<div style="margin-top:6px;font-style:italic">Net fayda eğrisi sabit `
    + `bir miktar aşağı kayar, eğimi değişmez (d/dx sabit = 0) — bu yüzden `
    + `net fayda ölçütünde optimum konum ilkesel olarak kaymaz. `
    + `Fayda/masraf bir orandır; sabit terim paydaya girdiğinden sıralamayı `
    + `değiştirebilir.</div>` + eleNot;
}

function optKartCiz(){
  const kf = konfigSuz(), sat = (a, b) => `<tr><td>${a}</td><td>${b}</td></tr>`;
  const ss = sirali();
  const tek = ss.length === 1;
  $("#optKart").innerHTML = ss.map(s => {
    const o = optimum(s.kod, kf);
    if (!o) return "";
    const ayrinti = tek ? `
      ${sat("Tünel hızı", sayi(o.vt,2) + " m/s")}
      ${sat("Cebri boru hızı", sayi(o.vc,1) + " m/s")}
      ${sat("Et kalınlığı", sayi(o.et,1) + " mm")}
      ${sat("Çelik ağırlığı", sayi(o.celik,0) + " ton")}
      ${sat("Yük kaybı", sayi(o.kayip,2) + " m")}
      ${dRated(o, s.kod)}
      ${sat("Sistem verimi", sayi(o.sisv,2) + " %")}
      ${sat("Regülasyon oranı", sayi(o.reg,1) + " %")}
      <tr><td colspan="2" style="padding-top:7px"></td></tr>
      ${sat("Tünel", sayi(o.mtun,3) + " M€")}
      ${sat("Cebri boru + tünel", sayi(o.mceb,3) + " M€")}
      ${sat("Elektromekanik", sayi(o.mem,3) + " M€")}
      ${sat("Santral + şalt", sayi(o.msan,3) + " M€")}
      ${sabitYil() ? sat("Sabit maliyet", sayi(sabitYil(),3) + " M€/yıl") : ""}
      ${sat("Yıllık gider", sayi(gGid(o),3) + " M€")}
      ${sat("Birim enerji maliyeti", sayi(gBem(o,s.kod),2) + " €/MWh")}` : "";
    return `<div class="kart" style="border-left:4px solid ${s.renk}">
      <div class="ad">${s.kod} · ${s.ad}</div>
      <div class="not">${s.isletme}</div>
      <div class="buyuk" style="color:${s.renk}">
        ${sayi(olcut === "fm" ? gFm(o,s.kod) : gNet(o,s.kod),3)}${
          olcut === "fm" ? "" : " M€/yıl"}</div>
      <div class="not">${olcut === "fm" ? "fayda / masraf oranı" : "net fayda"}${
        sabitYil() ? " · sabit maliyet dahil" : ""}</div>
      <table>
        ${sat("Tünel çapı", sayi(o.dt,1) + " m")}
        ${sat("Tasarım debisi", sayi(o.q,1) + " m³/s")}
        ${sat("Cebri boru çapı", sayi(o.dc,2) + " m")}
        ${sat("Minimum su kotu", sayi(o.km,0) + " m")}
        ${sat("Kurulu güç", sayi(o.pkur,2) + " MW")}
        ${sat("Enerji", sayi(o[s.kod+"_enerji"],2) + " GWh/yıl")}
        ${sat("Yatırım", sayi(gYat(o),3) + " M€")}
        ${sat("Brüt gelir", sayi(o[s.kod+"_brut"],3) + " M€")}
        ${sat("Net gelir", sayi(o[s.kod+"_gelir"],3) + " M€")}
        ${sat("Fayda/masraf", sayi(gFm(o,s.kod),3))}
        ${ayrinti}
      </table></div>`;
  }).join("");
}

let sirala = null, siraTers = true;
function tabloCiz(){
  const ss = sirali(), coklu = ss.length > 1;
  const kol = [];
  if (coklu) kol.push(["_sen", "Senaryo", null]);
  kol.push(["dt","D_tün [m]",1],["vt","v_tün [m/s]",2],["q","Q [m³/s]",1],
           ["dc","D_ceb [m]",2],["vc","v_ceb [m/s]",1],
           ["km","min kot [m]",0],["et","et [mm]",1],
           ["pkur","P_kur [MW]",2],["kayip","kayıp [m]",2],
           ["_enerji","Enerji [GWh]",2],["yat","Yatırım [M€]",3],
           ["_brut","Brüt gelir [M€]",3],["_gelir","Net gelir [M€]",3],
           ["gid","Sabit gider [M€]",3],
           ["_net","NET [M€/yıl]",3],["_fm","F/M",3]);
  /* "_" ile başlayan sütunlar senaryoya bağlıdır */
  const oku = (pt, k) => k === "_sen" ? pt.s
              : k === "_net" ? gNet(pt.d, pt.s)
              : k === "_fm"  ? gFm(pt.d, pt.s)
              : k === "gid"  ? gGid(pt.d)
              : k === "yat"  ? gYat(pt.d)
              : k.startsWith("_") ? pt.d[pt.s + k] : pt.d[k];
  const anahtar = sirala || "_net";
  const nk = noktalar().sort((a, b) => {
    const x = oku(a, anahtar), y = oku(b, anahtar);
    if (typeof x === "string") return siraTers ? y.localeCompare(x) : x.localeCompare(y);
    return siraTers ? y - x : x - y;
  });
  $("#satirSayi").textContent = nk.length + " kayıt";
  $("#tablo").innerHTML =
    "<thead><tr>" + kol.map(k =>
      `<th data-k="${k[0]}">${k[1]}${anahtar === k[0]
        ? (siraTers ? " ▼" : " ▲") : ""}</th>`).join("") + "</tr></thead><tbody>" +
    nk.slice(0, 150).map((pt, i) => {
      const sec = secili && secili.d === pt.d && secili.s === pt.s;
      return `<tr data-i="${i}" class="${sec ? "secili" : ""}">` +
        kol.map(k => k[0] === "_sen"
          ? `<td><span class="snokta" style="background:${senBilgi(pt.s).renk}">
             </span> ${pt.s}</td>`
          : `<td>${sayi(oku(pt, k[0]), k[2])}</td>`).join("") + "</tr>";
    }).join("") + "</tbody>";
  $("#tablo").querySelectorAll("th").forEach(h => h.onclick = () => {
    const k = h.dataset.k;
    if (sirala === k) siraTers = !siraTers; else { sirala = k; siraTers = true; }
    tabloCiz();
  });
  $("#tablo").querySelectorAll("tbody tr").forEach(r => r.onclick = () => {
    secili = nk[+r.dataset.i]; ciz();
  });
}

/* ==========================================================================
   İŞLETME ÇALIŞMASI DETAYI
   Seçilen konfigürasyonun DP ile çözülmüş aylık işletme serisi gösterilir.
   Seriler isletme_detay.py tarafından önceden hesaplanıp gömülür.
   ========================================================================== */
const dAnahtar = d => `${d.dt.toFixed(1)}|${d.q.toFixed(1)}|${d.vc.toFixed(1)}`
                      + `|${d.km.toFixed(0)}`;

/* İşletme serileri üç kaynaktan gelebilir:
     1) dOnbellek — bu oturumda sunucudan alınanlar
     2) DETAY     — HTML'e gömülü çekirdek küme (sunucusuz yedek)
     3) sunucu    — pano_sunucu.py, herhangi bir alternatifi anlık çözer     */
let dOnbellek = {};
let SUNUCU = null;              /* null: bilinmiyor · true/false: var/yok */

function dYerel(d, amac){
  const a = dAnahtar(d);
  if (dOnbellek[a + "|" + amac]) return dOnbellek[a + "|" + amac];
  if (DETAY.konfig && DETAY.konfig[a]) return DETAY.konfig[a][amac];
  return null;
}
/* Detay bölümü sunucu varsa HER nokta için, yoksa yalnız gömülü olanlar için */
const dVar = d => SUNUCU !== false || dYerel(d, "gelir") !== null;

/* Tarayıcı bir sayfadan yerel program BAŞLATAMAZ (güvenlik kısıtı).
   Sunucu çalışmıyorsa kullanıcıya tek tıkla başlatma yolu gösterilir. */
function sunucuUyari(baslik){
  return `<div class="duyari">
    <b>${baslik}</b><br><br>
    Bunun için yerel sunucunun çalışıyor olması gerekir. Klasördeki
    <span class="kutucuk">pano_baslat.bat</span> dosyasına <b>çift tıklayın</b> —
    sunucu başlar ve pano otomatik açılır.<br><br>
    Komut satırını tercih ederseniz:
    <span class="kutucuk" id="kmt">python pano_sunucu.py</span>
    <button class="kopyala" onclick="navigator.clipboard.writeText(
      'python pano_sunucu.py'); this.textContent='kopyalandı ✓'">kopyala</button>
    <br><br><span style="opacity:.75">Tarayıcı güvenlik kuralları gereği bu
    sayfa sunucuyu kendisi başlatamaz.</span></div>`;
}

async function sunucuYokla(){
  if (SUNUCU !== null) return SUNUCU;
  try{
    const y = await fetch("api/durum", {cache: "no-store"});
    SUNUCU = y.ok;
  }catch(e){ SUNUCU = false; }
  return SUNUCU;
}

async function dGetir(d, amac){
  const y = dYerel(d, amac);
  if (y) return y;
  if (!(await sunucuYokla())) return null;
  const u = `api/isletme?dt=${d.dt}&q=${d.q}&vc=${d.vc}&km=${d.km}&amac=${amac}`;
  const c = await fetch(u, {cache: "no-store"});
  if (!c.ok) throw new Error("sunucu hatası " + c.status);
  const j = await c.json();
  if (j.hata) throw new Error(j.hata);
  dOnbellek[dAnahtar(d) + "|" + amac] = j.veri;
  return j.veri;
}

function dEksen(a, b){
  const ham = (b - a) / 5, us = Math.pow(10, Math.floor(Math.log10(ham || 1)));
  const n = ham / us, adim = us * (n >= 5 ? 5 : n >= 2 ? 2 : 1);
  const r = [];
  for (let v = Math.ceil(a / adim) * adim; v <= b + adim * 1e-9; v += adim) r.push(v);
  return {d: r, o: Math.max(0, Math.min(2, -Math.floor(Math.log10(adim))))};
}

/* Senaryonun doğal işletme biçimi:
     S1 → PİK · S2, S3 → BANT · S4 → ilk 10 yıl BANT, sonrası PİK */
const dDogalAmac = k => k === "S1" ? "gelir" : "enerji";

function dSekmeCiz(){
  $("#dSekme").innerHTML = SENARYOLAR.map(x => {
    const a = x.kod === dSen;
    return `<span class="sekme${a ? " acik" : ""}" data-k="${x.kod}"
      style="padding:5px 11px;font-size:12px;border-color:${x.renk};
             ${a ? "background:" + x.renk : ""}">${x.kod} · ${x.ad}</span>`;
  }).join("");
  $("#dSekme").querySelectorAll(".sekme").forEach(b => b.onclick = () => {
    dSen = b.dataset.k;
    dAmacElle = false;                 /* senaryo değişince biçim de sıfırlanır */
    detayCiz();
  });
  /* S4'te iki dönem de geçerli olduğu için seçenek etiketleri değişir */
  const s4 = dSen === "S4";
  $("#dAmac").options[0].text = s4 ? "PİK — 11–50. yıl (serbest piyasa)"
                                   : "PİK — gelir maksimizasyonu";
  $("#dAmac").options[1].text = s4 ? "BANT — 1–10. yıl (sabit tarife)"
                                   : "BANT — enerji maksimizasyonu";
}

async function detayCiz(){
  const kutu = $("#detayKutu");
  if (!secili || !dVar(secili.d)){
    kutu.style.display = "none";
    dSen = null;
    return;
  }
  kutu.style.display = "block";
  /* nokta değiştiğinde detay, tıklanan noktanın senaryosuyla açılır */
  if (dSen === null || detayCiz.sonNokta !== secili.d ||
      detayCiz.sonSen !== secili.s){
    dSen = secili.s;
    dAmacElle = false;
    detayCiz.sonNokta = secili.d;
    detayCiz.sonSen = secili.s;
    const pk = $("#dPaketSonuc"); if (pk) pk.innerHTML = "";
  }
  if (!dAmacElle) dAmac = dDogalAmac(dSen);
  $("#dAmac").value = dAmac;
  dSekmeCiz();

  const sen = senBilgi(dSen);
  const d = secili.d;
  const K = (DETAY.konfig && DETAY.konfig[dAnahtar(d)])
            || {dt: d.dt, q: d.q, vc: d.vc, km: d.km,
                neden: ["seçilen alternatif"]};

  /* seri hazır değilse sunucudan iste */
  const durum = $("#dDurum");
  let O = dYerel(d, dAmac);
  if (!O){
    durum.style.display = "inline-block";
    durum.textContent = "işletme çalışması arka planda çözülüyor…";
    try{
      O = await dGetir(d, dAmac);
    }catch(e){
      durum.textContent = "hesaplanamadı: " + e.message;
      return;
    }
    if (!O){
      durum.style.display = "none";
      $("#dKart").innerHTML = sunucuUyari(
        "Bu alternatifin işletme çalışması hazır değil — hesaplanması gerekiyor.");
      $("#dG1").innerHTML = $("#dG2").innerHTML = $("#dG3").innerHTML = "";
      return;
    }
    durum.style.display = "none";
    /* diğer işletme biçimini de arka planda hazırla (senaryo geçişi anında olsun) */
    const oteki = dAmac === "gelir" ? "enerji" : "gelir";
    if (!dYerel(d, oteki)) dGetir(d, oteki).catch(() => {});
  }
  const N = O.kot.length, ny = DETAY.yil_sayisi, y0 = DETAY.yil0;

  $("#detayBaslik").textContent =
    `D_tünel ${sayi(K.dt,1)} m · Q ${sayi(K.q,1)} m³/s · `
    + `D_cebri ${sayi(d.dc,2)} m · min kot ${sayi(K.km,0)} m`;
  $("#dNeden").textContent = K.neden ? ("Bu seçenek şunlar için hesaplandı: "
    + K.neden.join(", ") + ".") : "";

  /* yıl seçici */
  if ($("#dYil").options.length !== ny + 1){
    let o = `<option value="hepsi">tümü (${ny} su yılı)</option>`;
    for (let i = 0; i < ny; i++)
      o += `<option value="${i}">${y0 + i}–${y0 + i + 1} su yılı</option>`;
    $("#dYil").innerHTML = o;
    $("#dYil").value = dYil;
  }
  const i0 = dYil === "hepsi" ? 0 : +dYil * 12;
  const i1 = dYil === "hepsi" ? N : i0 + 12;
  const dilim = a => a.slice(i0, i1);

  dZaman(O, dilim, i0, i1, K);
  dCalismaAlani(O, K);
  dVerim(O, K);
  dKart(K, O, sen);
}

/* ---- 1) Rezervuar salınımı + debiler ---------------------------------- */
function dZaman(O, dilim, i0, i1, K){
  const W = 900, H = 320, G = {sol: 58, sag: 62, ust: 26, alt: 40};
  const gw = W - G.sol - G.sag, gh = H - G.ust - G.alt;
  const kot = dilim(O.kot), q = dilim(O.q), gel = dilim(O.gelen),
        sav = dilim(O.savak);
  const n = kot.length;
  const X = i => G.sol + (n === 1 ? gw / 2 : i / (n - 1) * gw);

  const kMin = Math.min(K.km, Math.min(...kot)), kMaks = DETAY.kot_maks;
  const kPay = (kMaks - kMin) * .08;
  const YK = v => G.ust + gh - (v - (kMin - kPay))
                  / ((kMaks + kPay) - (kMin - kPay)) * gh;
  const qMaks = Math.max(1, ...gel, ...q) * 1.08;
  const YQ = v => G.ust + gh - v / qMaks * gh;

  let p = "";
  const ek = dEksen(kMin - kPay, kMaks + kPay);
  ek.d.forEach(v => {
    p += `<line class="izgara" x1="${G.sol}" y1="${YK(v)}" x2="${W-G.sag}" y2="${YK(v)}"/>`;
    p += `<text class="etiket" x="${G.sol-8}" y="${YK(v)+4}" text-anchor="end">${sayi(v,0)}</text>`;
  });
  const eq = dEksen(0, qMaks);
  eq.d.forEach(v => {
    p += `<text class="etiket" x="${W-G.sag+8}" y="${YQ(v)+4}">${sayi(v,0)}</text>`;
  });
  /* maks / min işletme kotu */
  p += `<line x1="${G.sol}" y1="${YK(DETAY.kot_maks)}" x2="${W-G.sag}"
          y2="${YK(DETAY.kot_maks)}" stroke="#d1242f" stroke-dasharray="5 4"/>`;
  p += `<line x1="${G.sol}" y1="${YK(K.km)}" x2="${W-G.sag}" y2="${YK(K.km)}"
          stroke="#8250df" stroke-dasharray="5 4"/>`;

  const yol = (a, Y) => a.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1)
                             + "," + Y(v).toFixed(1)).join(" ");
  /* gelen akım — dolgu */
  p += `<path d="${yol(gel, YQ)} L${X(n-1).toFixed(1)},${G.ust+gh}
          L${G.sol},${G.ust+gh} Z" fill="#8b949e" opacity=".18"/>`;
  p += `<path d="${yol(sav, YQ)}" fill="none" stroke="#d1242f" stroke-width="1.2"
          opacity=".8" stroke-dasharray="3 2"/>`;
  p += `<path d="${yol(q, YQ)}" fill="none" stroke="#2da44e" stroke-width="1.5"/>`;
  p += `<path d="${yol(kot, YK)}" fill="none" stroke="#0969da" stroke-width="2"/>`;

  /* x ekseni: su yılı etiketleri */
  const adim = n > 60 ? 60 : n > 24 ? 12 : 1;
  for (let i = 0; i < n; i += adim){
    const yil = DETAY.yil0 + Math.floor((i0 + i) / 12);
    p += `<line class="izgara" x1="${X(i)}" y1="${G.ust}" x2="${X(i)}" y2="${G.ust+gh}"/>`;
    p += `<text class="etiket" x="${X(i)}" y="${G.ust+gh+16}"
            text-anchor="middle">${n <= 12 ? DETAY.ay_adlari[(i0+i)%12] : yil}</text>`;
  }
  p += `<line class="eksen" x1="${G.sol}" y1="${G.ust+gh}" x2="${W-G.sag}" y2="${G.ust+gh}"/>`;
  p += `<text class="dbaslik" x="${G.sol}" y="14">Rezervuar salınımı ve debiler</text>`;
  p += `<text class="etiket" x="${G.sol}" y="${H-6}">
          <tspan fill="#0969da">▬ rezervuar kotu [m]</tspan>
          <tspan fill="#2da44e" dx="14">▬ türbinlenen debi [m³/s]</tspan>
          <tspan fill="#d1242f" dx="14">▬ savaklanan</tspan>
          <tspan fill="#8b949e" dx="14">▬ gelen akım</tspan></text>`;
  $("#dG1").innerHTML = p;
}

/* ---- 2) İşletme noktaları: debi – net düşü ---------------------------- */
function dCalismaAlani(O, K){
  const W = 440, H = 340, G = {sol: 62, sag: 16, ust: 26, alt: 48};
  const gw = W - G.sol - G.sag, gh = H - G.ust - G.alt;
  const qun = K.q / 2;
  const nk = [];
  for (let i = 0; i < O.q.length; i++){
    if (O.saat[i] <= 0 || O.yuk[i] <= 0) continue;
    nk.push({qop: O.yuk[i] * O.unite[i] * qun, h: O.hnet[i],
             saat: O.saat[i], ay: i % 12});
  }
  if (!nk.length){ $("#dG2").innerHTML = ""; return; }
  const qs = nk.map(o => o.qop), hs = nk.map(o => o.h);
  const x0 = Math.min(...qs) * .92, x1 = Math.max(K.q, ...qs) * 1.05;
  const y0 = Math.min(...hs) * .98, y1 = Math.max(...hs) * 1.02;
  const X = v => G.sol + (v - x0) / (x1 - x0) * gw;
  const Y = v => G.ust + gh - (v - y0) / (y1 - y0) * gh;

  let p = "";
  const ex = dEksen(x0, x1), ey = dEksen(y0, y1);
  ey.d.forEach(v => {
    p += `<line class="izgara" x1="${G.sol}" y1="${Y(v)}" x2="${W-G.sag}" y2="${Y(v)}"/>`;
    p += `<text class="etiket" x="${G.sol-7}" y="${Y(v)+4}" text-anchor="end">${sayi(v,0)}</text>`;
  });
  ex.d.forEach(v => {
    p += `<line class="izgara" x1="${X(v)}" y1="${G.ust}" x2="${X(v)}" y2="${G.ust+gh}"/>`;
    p += `<text class="etiket" x="${X(v)}" y="${G.ust+gh+16}" text-anchor="middle">${sayi(v,0)}</text>`;
  });
  const sMaks = Math.max(...nk.map(o => o.saat));
  nk.forEach(o => {
    const r = 2 + 5 * Math.sqrt(o.saat / sMaks);
    p += `<circle cx="${X(o.qop).toFixed(1)}" cy="${Y(o.h).toFixed(1)}" r="${r.toFixed(1)}"
            fill="#0969da" opacity=".38"/>`;
  });
  /* tasarım noktası */
  p += `<line x1="${X(K.q)}" y1="${G.ust}" x2="${X(K.q)}" y2="${G.ust+gh}"
          stroke="#d1242f" stroke-dasharray="4 3"/>`;
  p += `<text class="etiket" x="${X(K.q)-5}" y="${G.ust+12}" text-anchor="end"
          fill="#d1242f">Q_tasarım</text>`;
  p += `<line class="eksen" x1="${G.sol}" y1="${G.ust+gh}" x2="${W-G.sag}" y2="${G.ust+gh}"/>`;
  p += `<line class="eksen" x1="${G.sol}" y1="${G.ust}" x2="${G.sol}" y2="${G.ust+gh}"/>`;
  p += `<text class="dbaslik" x="${G.sol}" y="14">İşletme noktaları</text>`;
  p += `<text class="etiket" x="${G.sol+gw/2}" y="${H-24}" text-anchor="middle">
          İşletme debisi [m³/s]</text>`;
  p += `<text class="etiket" transform="translate(14,${G.ust+gh/2}) rotate(-90)"
          text-anchor="middle">Net düşü [m]</text>`;
  p += `<text class="etiket" x="${G.sol}" y="${H-6}">daire boyu = o aydaki çalışma
          saati</text>`;
  $("#dG2").innerHTML = p;
}

/* ---- 3) Türbin verim eğrisi + işletme dağılımı ------------------------ */
function dVerim(O, K){
  const W = 440, H = 340, G = {sol: 56, sag: 40, ust: 26, alt: 48};
  const gw = W - G.sol - G.sag, gh = H - G.ust - G.alt;
  const VE = DETAY.verim_egrisi;
  const X = v => G.sol + (v - 0.2) / (1.05 - 0.2) * gw;
  const eMin = Math.min(...VE.eta) * 100 - 3, eMaks = 100;
  const Y = v => G.ust + gh - (v - eMin) / (eMaks - eMin) * gh;

  /* hangi yükte kaç saat çalışılmış */
  const saat = {};
  for (let i = 0; i < O.yuk.length; i++)
    if (O.yuk[i] > 0) saat[O.yuk[i]] = (saat[O.yuk[i]] || 0) + O.saat[i];
  const topSaat = Object.values(saat).reduce((a, b) => a + b, 0) || 1;

  let p = "";
  const ey = dEksen(eMin, eMaks);
  ey.d.forEach(v => {
    p += `<line class="izgara" x1="${G.sol}" y1="${Y(v)}" x2="${W-G.sag}" y2="${Y(v)}"/>`;
    p += `<text class="etiket" x="${G.sol-7}" y="${Y(v)+4}" text-anchor="end">${sayi(v,0)}</text>`;
  });
  [0.2,0.4,0.6,0.8,1.0].forEach(v => {
    p += `<line class="izgara" x1="${X(v)}" y1="${G.ust}" x2="${X(v)}" y2="${G.ust+gh}"/>`;
    p += `<text class="etiket" x="${X(v)}" y="${G.ust+gh+16}" text-anchor="middle">%${(v*100).toFixed(0)}</text>`;
  });
  /* çalışma süresi payı — çubuk */
  Object.entries(saat).forEach(([y, sa]) => {
    const pay = sa / topSaat, hgt = pay * gh * .85;
    p += `<rect x="${X(+y)-9}" y="${G.ust+gh-hgt}" width="18" height="${hgt}"
            fill="#2da44e" opacity=".22"/>`;
    p += `<text class="etiket" x="${X(+y)}" y="${G.ust+gh-hgt-4}"
            text-anchor="middle" fill="#2da44e">%${(pay*100).toFixed(0)}</text>`;
  });
  /* imalatçı verim eğrisi */
  const yol = VE.yuk.map((y, i) => (i ? "L" : "M") + X(y).toFixed(1) + ","
                         + Y(VE.eta[i]*100).toFixed(1)).join(" ");
  p += `<path d="${yol}" fill="none" stroke="#bf3989" stroke-width="2.2"/>`;
  VE.yuk.forEach((y, i) => {
    p += `<circle cx="${X(y).toFixed(1)}" cy="${Y(VE.eta[i]*100).toFixed(1)}"
            r="3" fill="#bf3989"/>`;
  });
  /* fiilen kullanılan yük noktaları */
  Object.keys(saat).forEach(y => {
    const e = interp(+y, VE.yuk, VE.eta) * 100;
    p += `<circle cx="${X(+y).toFixed(1)}" cy="${Y(e).toFixed(1)}" r="6"
            fill="none" stroke="#0969da" stroke-width="2.2"/>`;
  });
  p += `<line class="eksen" x1="${G.sol}" y1="${G.ust+gh}" x2="${W-G.sag}" y2="${G.ust+gh}"/>`;
  p += `<line class="eksen" x1="${G.sol}" y1="${G.ust}" x2="${G.sol}" y2="${G.ust+gh}"/>`;
  p += `<text class="dbaslik" x="${G.sol}" y="14">Türbin verim eğrisi</text>`;
  p += `<text class="etiket" x="${G.sol+gw/2}" y="${H-24}" text-anchor="middle">
          Ünite yük oranı</text>`;
  p += `<text class="etiket" transform="translate(13,${G.ust+gh/2}) rotate(-90)"
          text-anchor="middle">Türbin verimi [%]</text>`;
  p += `<text class="etiket" x="${G.sol}" y="${H-6}">
          <tspan fill="#bf3989">▬ imalatçı eğrisi</tspan>
          <tspan fill="#0969da" dx="10">○ kullanılan yükler</tspan>
          <tspan fill="#2da44e" dx="10">▮ çalışma süresi payı</tspan></text>`;
  $("#dG3").innerHTML = p;
}

function interp(x, xs, ys){
  if (x <= xs[0]) return ys[0];
  if (x >= xs[xs.length-1]) return ys[ys.length-1];
  for (let i = 1; i < xs.length; i++)
    if (x <= xs[i])
      return ys[i-1] + (ys[i]-ys[i-1]) * (x-xs[i-1]) / (xs[i]-xs[i-1]);
  return ys[ys.length-1];
}

/* ---- 4) Bilgi kartı --------------------------------------------------- */
function dKart(K, O, sen){
  const z = O.ozet, d = secili.d, sat = (a,b) => `<tr><td>${a}</td><td>${b}</td></tr>`;
  const bicim = dAmac === "gelir" ? "PİK (gelir maks.)" : "BANT (enerji maks.)";
  const dogal = dAmac === dDogalAmac(dSen);
  $("#dKart").innerHTML = `
    <div class="kart" style="border-left:4px solid ${sen.renk}">
      <div class="ad">${sen.kod} · ${sen.ad}</div>
      <div class="not">${bicim} işletmesi${dogal ? "" :
        " — bu senaryonun doğal biçimi değil, karşılaştırma için"}</div>
      <div class="buyuk" style="color:${sen.renk}">
        ${sayi(gNet(d,dSen),3)} M€/yıl</div>
      <div class="not">nihai net fayda (${sen.kod})${
        sabitYil() ? " · sabit maliyet dahil" : ""}</div>
      <table>
        ${sat("Tünel çapı / hızı", sayi(K.dt,1) + " m · " + sayi(d.vt,2) + " m/s")}
        ${sat("Tasarım debisi", sayi(K.q,1) + " m³/s")}
        ${sat("Cebri boru çapı / hızı", sayi(d.dc,2) + " m · " + sayi(K.vc,1) + " m/s")}
        ${sat("Et kalınlığı / çelik", sayi(d.et,1) + " mm · " + sayi(d.celik,0) + " t")}
        ${sat("Minimum su kotu", sayi(K.km,0) + " m")}
        ${sat("Aktif hacim", sayi(d.vakt,2) + " hm³")}
        ${sat("Kurulu güç", sayi(z.P_kurulu,2) + " MW")}
        <tr><td colspan="2" style="padding-top:7px"></td></tr>
        ${sat("Enerji", sayi(z.enerji,2) + " GWh/yıl")}
        ${sat("Firm enerji (%95)", sayi(z.firm,2) + " GWh/yıl")}
        ${sat("Kapasite faktörü", sayi(z.kapasite_f,1) + " %")}
        ${sat("Çalışma süresi", sayi(z.calisma,0) + " h/yıl")}
        <tr><td colspan="2" style="padding-top:7px"></td></tr>
        ${sat("Rezervuar en düşük", sayi(z.kot_min,1) + " m")}
        ${sat("Rezervuar ortalama", sayi(z.kot_ort,1) + " m")}
        ${sat("Rezervuar en yüksek", sayi(z.kot_maks,1) + " m")}
        ${sat("RATED rezervuar kotu", sayi(dAmac === "gelir" ? d.rkot : d.rkotB,2) + " m")}
        ${sat("RATED net düşü", sayi(dAmac === "gelir" ? d.rnet : d.rnetB,2)
              + " m")}
        ${sat("&nbsp;&nbsp;· 1 ünite işletmesinde",
              sayi(dAmac === "gelir" ? d.rnet1 : d.rnet1B,2) + " m")}
        ${sat("&nbsp;&nbsp;· 2 ünite işletmesinde",
              sayi(dAmac === "gelir" ? d.rnet2 : d.rnet2B,2) + " m")}
        ${sat("Yük kaybı @Q_tas", sayi(d.kayip,2) + " m")}
        <tr><td colspan="2" style="padding-top:7px"></td></tr>
        ${sat("Yatırım", sayi(gYat(d),3) + " M€")}
        ${sat("Brüt gelir", sayi(d[dSen+"_brut"],3) + " M€/yıl")}
        ${sat("Net gelir", sayi(d[dSen+"_gelir"],3) + " M€/yıl")}
        ${sat("Yıllık sabit gider", sayi(d.gid,3) + " M€/yıl")}
        ${sabitYil() ? sat("Konfig.-bağımsız sabit maliyet",
                           sayi(sabitYil(),3) + " M€/yıl") : ""}
        ${sat("Fayda/masraf", sayi(gFm(d,dSen),3))}
        ${sat("Senaryo enerjisi", sayi(d[dSen+"_enerji"],2) + " GWh/yıl")}
      </table></div>`;
}

/* ---- İmalatçı paketi: sunucuda üret, bağlantıları göster ------------- */
$("#dPaket").onclick = async () => {
  if (!secili) return;
  const d = secili.d, b = $("#dPaket"), kutu = $("#dPaketSonuc");
  if (!(await sunucuYokla())){
    kutu.innerHTML = sunucuUyari(
      "İmalatçı paketi (9 grafik + Excel) sunucuda üretilir.");
    return;
  }
  b.disabled = true;
  const eski = b.textContent;
  b.textContent = "⏳ üretiliyor… (10–20 sn)";
  kutu.innerHTML = `<div class="paketkutu">9 grafik ve 6 sayfalık Excel
    hazırlanıyor — dinamik programlama yeniden çözülüyor…</div>`;
  try{
    const u = `api/imalatci?dt=${d.dt}&q=${d.q}&vc=${d.vc}&km=${d.km}`
            + `&amac=${dAmac}`;
    const c = await fetch(u, {cache: "no-store"});
    const j = await c.json();
    if (j.hata) throw new Error(j.hata);
    const o = j.ozet, sat = (a, v) => `<tr><td>${a}</td><td>${v}</td></tr>`;
    kutu.innerHTML = `<div class="paketkutu">
      <b>İmalatçı paketi hazır</b> — ${o.amac_ad} işletme · ${j.sure_s} sn<br>
      <div style="margin:7px 0">
        <a href="${j.png}" target="_blank">📊 9 grafik (PNG)</a>
        <a href="${j.xlsx}">📗 Veri tabloları (Excel)</a>
      </div>
      <table>
        ${sat("ANMA rezervuar kotu", sayi(o.rated_kot,2) + " m")}
        ${sat("ANMA net düşü", sayi(o.rated_net,2) + " m")}
        ${sat("&nbsp;· 1 ünite işletmesinde", sayi(o.rated_net_1u,2) + " m"
              + " (suyun %" + sayi(o.pay1u,0) + "'i)")}
        ${sat("&nbsp;· 2 ünite işletmesinde", sayi(o.rated_net_2u,2) + " m")}
        ${sat("Kurulu güç", sayi(o.P_kurulu,2) + " MW")}
        ${sat("Yıllık enerji", sayi(o.enerji,2) + " GWh")}
        ${sat("Yıllık çalışma", sayi(o.calisma,0) + " h")}
        ${sat("<b>Başlatma-durdurma</b>", "<b>" + sayi(o.baslatma,0)
              + " /yıl</b> · ortalama blok " + sayi(o.blok_h,1) + " h")}
        ${sat("Çalışılan gün", sayi(o.gun,0) + " gün/yıl")}
      </table></div>`;
  }catch(e){
    kutu.innerHTML = `<div class="duyari">Paket üretilemedi: ${e.message}</div>`;
  }
  b.disabled = false; b.textContent = eski;
};

/* ---- Gövde en kesiti: sunucuda çiz, önizleme ve bağlantı ------------- */
$("#dKesit").onclick = async () => {
  if (!secili) return;
  const d = secili.d, b = $("#dKesit"), kutu = $("#dPaketSonuc");
  if (!(await sunucuYokla())){
    kutu.innerHTML = sunucuUyari("Gövde en kesiti sunucuda çizilir.");
    return;
  }
  b.disabled = true;
  const eski = b.textContent;
  b.textContent = "⏳ çiziliyor…";
  kutu.innerHTML = `<div class="paketkutu">Ölçekli en kesit hazırlanıyor —
    su alma kotu vorteks batıklığından hesaplanıyor…</div>`;
  try{
    const sen = senBilgi(dSen);
    const u = `api/enkesit?dt=${d.dt}&q=${d.q}&vc=${d.vc}&km=${d.km}`
            + `&amac=${dAmac}&etiket=${encodeURIComponent(sen.kod + " " + sen.ad)}`;
    const c = await fetch(u, {cache: "no-store"});
    const j = await c.json();
    if (j.hata) throw new Error(j.hata);
    const v = j.vorteks, g = j.govde;
    const sat = (a, x) => `<tr><td>${a}</td><td>${x}</td></tr>`;
    kutu.innerHTML = `<div class="paketkutu" style="border-color:#8250df;
        background:rgba(130,80,223,.08)">
      <b>Gövde en kesiti hazır</b> — ${j.sure_s} sn<br>
      <div style="margin:7px 0">
        <a href="${j.png}" target="_blank">🏗 Ölçekli en kesit (PNG)</a>
      </div>
      <table>
        ${sat("Kret kotu", sayi(g.kret,2) + " m  (NSS + " + sayi(g.hava_payi,1)
              + " m hava payı)")}
        ${sat("Gövde yüksekliği", sayi(g.yukseklik,2) + " m")}
        ${sat("Taban genişliği", sayi(g.taban_genislik,2) + " m  (taban/yük. "
              + sayi(g.taban_yukseklik,3) + ")")}
        ${sat("Kesit alanı", sayi(g.alan,0) + " m²")}
        ${sat("Şevler", "menba 1:" + sayi(g.menba_sev,2) + " · mansap 1:"
              + sayi(g.mansap_sev,2))}
        <tr><td colspan="2" style="padding-top:6px"></td></tr>
        ${sat("Su alma ağzı  B × D", sayi(v.B,2) + " × " + sayi(v.D,2) + " m")}
        ${sat("Ağızdaki hız / Froude", sayi(v.V,2) + " m/s · " + sayi(v.Fr,3))}
        ${sat("Gordon / Knauss", sayi(v.S_gordon,2) + " / " + sayi(v.S_knauss,2)
              + " m")}
        ${sat("<b>Vorteks batıklığı S</b>", "<b>" + sayi(v.S,2) + " m ("
              + v.belirleyen + ")</b>")}
        ${sat("<b>Su alma taban kotu</b>", "<b>" + sayi(v.taban,2) + " m</b>")}
      </table></div>`;
  }catch(e){
    kutu.innerHTML = `<div class="duyari">En kesit çizilemedi: ${e.message}</div>`;
  }
  b.disabled = false; b.textContent = eski;
};

$("#dAmac").onchange = e => { dAmac = e.target.value; dAmacElle = true;
                              $("#dPaketSonuc").innerHTML = ""; detayCiz(); };
$("#dYil").onchange = e => { dYil = e.target.value; detayCiz(); };

kurSekmeler(); kurSecimler(); ciz();
</script>
</body>
</html>
"""


def main():
    kd = os.path.dirname(os.path.abspath(__file__))
    yol = en_yeni_tarama(kd)
    df = pd.read_excel(yol, sheet_name="Tüm Senaryolar")

    print("=" * 88)
    print("HEZİL HES — İNTERAKTİF SONUÇ PANOSU")
    print("=" * 88)
    print(f"Kaynak     : {os.path.basename(yol)}  ({len(df)} alternatif)")

    kayit = veri_hazirla(df)
    js = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))

    # Bütün yer tutucular JSON olarak gömülür (dizeler de tırnaklı kalmalıdır;
    # tırnakları soymak "const X = metin;" gibi sözdizimi hatası üretir).
    gomulen = {
        "__VERI__": kayit,
        "__SENARYOLAR__": SENARYOLAR,
        "__METRIKLER__": METRIKLER,
        "__RENK_TUNEL__": {f"{k:.1f}": v for k, v in RENK_TUNEL.items()},
        "__RENK_VC__": RENK_VC,
        "__INDIRGEME__": INDIRGEME_ORANI,
        "__URETIM__": f"üretim {time.strftime('%d.%m.%Y %H:%M')}",
        "__DETAY__": detay_oku(kd),
    }
    html = HTML
    for yer, nesne in gomulen.items():
        html = html.replace(yer, js(nesne))

    # --- kendi kendini denetle: gömülü her sabit geçerli JSON olmalı ---------
    hata = []
    for ad in ("VERI", "SENARYOLAR", "METRIKLER", "RENK_TUNEL", "RENK_VC",
               "URETIM", "DETAY"):
        m = re.search(rf"^const {ad} = (.*);$", html, re.M)
        if m is None:
            hata.append(f"{ad}: satır bulunamadı")
            continue
        try:
            json.loads(m.group(1))
        except Exception as e:
            hata.append(f"{ad}: geçersiz JSON ({e})")
    kalan = [y for y in gomulen if y in html]
    if kalan:
        hata.append(f"doldurulmamış yer tutucu: {kalan}")
    if hata:
        raise SystemExit("PANO ÜRETİLEMEDİ:\n  " + "\n  ".join(hata))

    cikti = os.path.join(kd, "hezil_dashboard.html")
    try:
        with open(cikti, "w", encoding="utf-8") as f:
            f.write(html)
    except PermissionError:
        cikti = cikti.replace(".html", f"_{time.strftime('%Y%m%d_%H%M%S')}.html")
        with open(cikti, "w", encoding="utf-8") as f:
            f.write(html)

    print(f"Senaryo    : {', '.join(s['kod'] + ' ' + s['ad'] for s in SENARYOLAR)}"
          f"  (çoklu seçilebilir)")
    print(f"Büyüklük   : {len(METRIKLER)} adet seçilebilir eksen")
    print(f"Nokta      : {len(kayit)} konfigürasyon × 4 senaryo = "
          f"{len(kayit)*4} olası nokta")
    print(f"Gömülü işletme detayı : "
          f"{len(gomulen['__DETAY__'].get('konfig', {}))} konfigürasyon "
          f"(DETAY_GOMME='{DETAY_GOMME}')")
    print("İşletme çalışmasının tamamı için:  python pano_sunucu.py")
    print(f"Dosya boyu : {os.path.getsize(cikti)/1024:.0f} KB (tek dosya, "
          f"bağımlılık yok)")
    print(f"\nÇIKTI      : {cikti}")
    print("Çift tıklayarak tarayıcıda açabilirsiniz.")
    print("=" * 88)


if __name__ == "__main__":
    main()
