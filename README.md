# Hezil Barajı ve HES — Alternatif Optimizasyon Çalışması

Hezil Barajı ve Hidroelektrik Santrali için **ön fizibilite / alternatif optimizasyonu** çalışması.
Aylık gelen akımlar ve saatlik piyasa fiyatları kullanılarak, rezervuar işletme politikası
**deterministik dinamik programlama (DP)** ile optimize edilir ve tünel çapı × tasarım debisi ×
cebri boru hızı × minimum su kotu uzayında 1.512 alternatif taranır.

Proje tamamen Türkçedir (kod, yorumlar, Excel sayfaları, konsol çıktısı ve pano arayüzü).

---

## İçindekiler

- [Özellikler](#özellikler)
- [Nasıl çalışır](#nasıl-çalışır)
- [Kurulum](#kurulum)
- [Kullanım (işlem sırası)](#kullanım-işlem-sırası)
- [Betikler ve komut satırı](#betikler-ve-komut-satırı)
- [Girdi dosyaları](#girdi-dosyaları)
- [Senaryolar ve ekonomi](#senaryolar-ve-ekonomi)
- [Çıktılar](#çıktılar)
- [Proje yapısı](#proje-yapısı)
- [Önemli kısıtlar ve tuzaklar](#önemli-kısıtlar-ve-tuzaklar)

---

## Özellikler

- **Dinamik programlama tabanlı işletme optimizasyonu** — aylık rezervuar işletme politikası,
  piyasa gelirini (PTF) maksimize edecek şekilde geriye doğru çözülür.
  - *PİK (puant)* işletme: santral ayda az saatte tam yükte çalışır; üretim o ayın en pahalı
    saatlerinden satılır (fiyat-süre eğrisi içbükey fayda fonksiyonu olarak kullanılır).
  - *BANT* işletme: yalnız üretilen enerji maksimize edilir, gelir ayın ortalama fiyatından hesaplanır.
- **4 boyutlu alternatif taraması** — 7 tünel çapı × 6 tünel hızı × 6 cebri boru hızı × 6 min. kot
  = **1.512 konfigürasyon**, her biri PİK ve BANT amaçlarıyla ayrı ayrı çözülür (multiprocessing ile paralel).
- **4 senaryo** — PİK·piyasa, BANT·piyasa, SABİT 88 €/MWh, YEKDEM (kademeli alım garantisi).
- **Bağımlılıksız, tek dosyalık interaktif pano** — `hezil_dashboard.html` (gömülü veri, saf SVG + JS,
  koyu/açık tema). İnternet veya kütüphane gerektirmez.
- **Yerel pano sunucusu** — herhangi bir alternatifin işletme çalışmasını anlık çözer
  (`pano_sunucu.py`, port 8765) ve sonuçları önbelleğe alır.
- **Türbin imalatçısı veri paketi** (9 grafik + Excel) ve **ölçekli RCC gövde en kesiti** çizimi.
- **Duyarlılık analizleri** — sabit tarife, EM birim maliyeti ve günlük zaman adımı etkisi (DP tekrarı olmadan).

---

## Nasıl çalışır

```
giris_akimlari.xlsx  ──┐
kot_alan_hacim.xlsx  ──┼──►  optimzasyon.py  (DP çekirdeği)
res_operation_table..csv ─┘        │
                                   ▼
                          alternatifler.py  ──►  hezil_alternatifler*.xlsx + PNG
                                   │
                                   ▼
                          dashboard.py  ──►  hezil_dashboard.html (tek dosya)
                                   │
                                   ▼
                          pano_sunucu.py  ──►  http://127.0.0.1:8765
                                   (işletme çalışmalarını anlık çözer,
                                    hezil_onbellek/ içine önbellekler)
```

- **`optimzasyon.py`** kalptir: modül düzeyinde global girdi sabitleri (KOT_MAKS, Q_TASARIM, TUNEL_D,
  AMAC, …) vardır; çağıranlar bu sabitleri değiştirip `yeniden_kur()` çağırarak modeli tazeler.
- Hidrolik: Darcy-Weisbach (Swamee-Jain) sürtünmesi + ΣK·v²/2g yerel kayıpları; türbin verimi
  imalatçı eğrisinden homolog ölçeklenir; cebri boru et kalınlığı/basıncı hesaplanır.
- Ekonomi: yıllık gider = (tünel + EM + santral) yatırımı × 0,12 indirgeme oranı;
  net fayda = yıllık gelir − yıllık gider.

---

## Kurulum

```bash
pip install -r requirements.txt
```

Gereksinimler: `numpy`, `pandas`, `matplotlib`, `openpyxl` (ve `scipy`).
**Not:** scipy yalnızca PCHIP interpolasyonu için kullanılır; saf numpy yedeği mevcut olduğundan
çalışma zamanında zorunlu değildir.

Test, linter veya derleme adımı yoktur. Doğrulama = betiği çalıştırıp konsol çıktısını/çıkış
dosyalarını kontrol etmek.

---

## Kullanım (işlem sırası)

```bash
# 1) Tek başına DP çözümü (isteğe bağlı — örnek çıktı üretir)
python optimzasyon.py

# 2) Alternatif taraması (1.512 alternatif × PİK+BANT = ~3.000 DP koşumu, birkaç dakika)
python alternatifler.py

# 3) Tek dosyalık HTML pano üretimi
python dashboard.py

# 4) Yerel sunucu (işletme çalışmalarını anlık çözer, tarayıcıyı açar)
python pano_sunucu.py
#    Windows'ta çift tık: pano_baslat.bat
#    Durdurmak için: Ctrl+C
```

Sunucu çalışmasa bile `hezil_dashboard.html`'e çift tıklamak panoyu açar; yalnızca işletme
çalışması bölümü gömülü yedek veriyi kullanır.

---

## Betikler ve komut satırı

| Betik | Ne yapar | Çıktı |
|---|---|---|
| `optimzasyon.py` | Tek konfigürasyon için DP işletme optimizasyonu + rapor | `hezil_dp_sonuclar.xlsx`, `.png` |
| `alternatifler.py` | 1.512 alternatifin taranması (PİK + BANT) | `hezil_alternatifler*.xlsx`, `hezil_alternatifler.png`, `hezil_ekonomi.png` |
| `dashboard.py` | Tarama sonucunu tek dosyalık HTML panoya gömer | `hezil_dashboard.html` |
| `pano_sunucu.py` | Yerel HTTP sunucusu; `/api/isletme`, `/api/imalatci`, `/api/enkesit` | önbellek: `hezil_onbellek/*.json` |
| `isletme_detay.py` | Seçili konfigürasyonların işletme serilerini önceden hesaplar | `hezil_isletme_detay.json` |
| `sabit_fayda.py` | Sabit tarife (88 €/MWh) senaryosu — DP tekrarı yok | `hezil_sabit_fayda.xlsx`, `.png` |
| `em_duyarlilik.py` | Optimumun EM birim maliyetine duyarlılığı — DP tekrarı yok | `hezil_em_duyarlilik.xlsx`, `.png` |
| `gunluk_analiz.py` | Günlük zaman adımı kontrolü (min. kot sonucu değişiyor mu?) | `hezil_gunluk_analiz.xlsx`, `.png` |
| `govde_enkesit.py` | Ölçekli RCC gövde en kesiti + vorteks batıklığı | `hezil_govde_enkesit_*.png` |
| `imalatci_paketi.py` | Türbin imalatçısına 9 grafik + Excel paketi | `hezil_imalatci_paketi.png`, `.xlsx` |

### Komut satırı bayrakları

`govde_enkesit.py` ve `imalatci_paketi.py`:

```bash
python govde_enkesit.py                    # → S1 optimumu
python govde_enkesit.py --senaryo S4       # → YEKDEM optimumu
python govde_enkesit.py --konfig 4.4 60 5.0 720   # elle: (D, Q, v_c, kot)

python imalatci_paketi.py                  # → S1 optimumu
python imalatci_paketi.py --senaryo S4     # → YEKDEM optimumu
python imalatci_paketi.py --konfig 4.4 60 5.0 720
python imalatci_paketi.py --amac enerji    # → bant işletme (varsayılan: gelir/pik)
```

### Tarama ızgarası (`alternatifler.py`)

| Boyut | Değerler |
|---|---|
| Tünel çapı | 4.0 / 4.4 / 4.8 / 5.0 / 5.2 / 5.6 / 6.0 m (uzunluk 4 600 m sabit) |
| Tünel hızı | 2.8 – 3.8 m/s (6 adım; Q = v·πD²/4) |
| Cebri boru hızı | 3.5 – 6.0 m/s (6 adım; çap buna göre hesaplanır, uzunluk 300 m) |
| Minimum su kotu | 690 – 740 m (5 m aralık; maks. kot 755 m sabit) |

Toplam: 7 × 6 × 6 × 6 = **1.512 konfigürasyon**.

---

## Girdi dosyaları

| Dosya | İçerik |
|---|---|
| `giris_akimlari.xlsx` | Aylık gelen akımlar [hm³], su yılı **Ekim → Eylül** |
| `kot_alan_hacim.xlsx` | Kot–alan–hacim tablosu (kot [m] · alan [km²] · hacim [hm³]) |
| `res_operation_table_8760rows.csv` | Saatlik piyasa fiyatı (sütun: `price`, EUR/MWh). Yoksa sentetik seri üretilir → mutlak gelirler gösterge niteliğinde |

---

## Senaryolar ve ekonomi

| Kod | Senaryo | İşletme | Değerleme |
|---|---|---|---|
| S1 | PİK · piyasa | PİK (gelir maks.) | saatlik PTF, en pahalı saatler |
| S2 | BANT · piyasa | BANT (enerji maks.) | ay ortalama fiyatı |
| S3 | SABİT 88 €/MWh | BANT | sabit birim fayda |
| S4 | YEKDEM | BANT → PİK | 5 yıl 85 €/MWh + 5 yıl 75 €/MWh (bant) → 40 yıl piyasa (pik) |

Ekonomi sabitleri (`alternatifler.py`):

- İndirgeme oranı: `INDIRGEME_ORANI = 0.12` (yatırım → yıllık gider)
- EM birim maliyeti: `EM_BIRIM_EUR_KW = 140.0` €/kW
- Santral + şalt: `SANTRAL_SALT_EUR_KW = 75.0` €/kW
- Gelir kesintisi: `GELIR_KESINTI_ORANI = 0.09` (brüt gelir → net gelir)
- Net fayda = yıllık gelir − yıllık gider = (brüt gelir × 0.91) − (yatırım × 0.12)

---

## Çıktılar

- **`hezil_dashboard.html`** — tarama sonuçlarını gösteren interaktif, tek dosyalık pano:
  çoklu senaryo seçimi, seçilebilir eksenler (20+ büyüklük), filtreler (çap/hız/kot),
  her senaryonun optimumu halkalanır ve kart olarak özetlenir, sabit maliyet ve B/C < 1
  eleme araçları, işletme çalışması bölümü (sunucuyla anlık çözüm), alternatifler tablosu.
- **`hezil_alternatifler*.xlsx`** — Girdiler + Tüm Alternatifler + Ekonomi + En İyi 20 +
  Referans + pivot tabloları. Hedef dosya Excel'de açıkken zaman damgalı yedek yazılır;
  alt betikler daima **en güncel** dosyayı okur.
- **PNG raporları** — enerji/gelir taramaları, ekonomi, duyarlılık, günlük analiz, en kesit,
  imalatçı paketi vb.

---

## Proje yapısı

```
hezil/
├── optimzasyon.py          # DP çekirdeği (global sabitler + yeniden_kur())
├── alternatifler.py        # 1.512 alternatif taraması + ekonomi
├── dashboard.py            # tek dosyalık HTML pano üreteci
├── pano_sunucu.py          # yerel sunucu (port 8765) — anlık işletme çözümü
├── pano_baslat.bat         # Windows çift tık başlatıcı
├── isletme_detay.py        # işletme serilerini önceden hesaplar (JSON)
├── sabit_fayda.py          # sabit tarife senaryosu
├── em_duyarlilik.py        # EM maliyeti duyarlılığı
├── gunluk_analiz.py        # günlük zaman adımı kontrolü
├── govde_enkesit.py        # RCC gövde en kesiti
├── imalatci_paketi.py      # türbin imalatçısı paketi
├── giris_akimlari.xlsx     # aylık akımlar (girdi)
├── kot_alan_hacim.xlsx     # kot-alan-hacim (girdi)
├── res_operation_table_8760rows.csv  # saatlik fiyat (girdi)
├── requirements.txt
├── knowledge.md            # proje bilgi dosyası (Freebuff/AI bağlamı)
├── hezil_onbellek/         # sunucu önbelleği (D_Q_vc_kot_amac.json)
└── hezil_*.xlsx / *.png    # üretilen çıktılar
```

---

## Önemli kısıtlar ve tuzaklar

- **Tek iş parçacığı değildir:** DP modül düzeyindeki global girdileri (Q_TASARIM, KOT_MIN,
  BASLANGIC_KOTU, AMAC, çap…) değiştirir. `pano_sunucu.py` tüm DP/çizim işini tek
  `threading.Lock` altında sıraya alır. Bu yolların içini paralelleştirmeyin.
- **Çözmeden önce global sabitleri tam sıfırlayın:** `BASLANGIC_KOTU` konfigürasyonun
  `KOT_MIN`'ine ayarlanır (yıl başı boş rezervuar). Kısmi sıfırlama bayat sonuç üretir.
- **Tünel maliyeti tablosu yalnız D 4.0–6.0 m kapsar;** dışında maliyet kenar eğimleriyle
  doğrusal tahmin edilir (kübik taşmayı önlemek için).
- **`hezil_onbellek/` önbelleği bayatlayabilir:** model girdileri değişince değişen
  konfigürasyonların JSON dosyalarını silin (anahtar: `4.4_57.8_4.0_700_gelir.json` biçiminde).
- **Ekonomi sabitlerini sessizce değiştirmeyin** (`INDIRGEME_ORANI`, `EM_BIRIM_EUR_KW`,
  `GELIR_KESINTI_ORANI`): `dashboard.py` indirgeme oranını kaynak metinden regex ile okur;
  tutarsızlık pano ile Excel sonuçlarını ayrıştırır.
- **Bayat dosya okuma:** tarama/Excel hedefi Excel'de açıkken, üreten betik zaman damgalı yedek
  yazar; alt betikler glob-by-mtime ile **en yeni** `hezil_alternatifler*.xlsx`'i seçer —
  sabit isim kullanmayın.
- **Sentetik fiyat uyarısı:** fiyat dosyası bulunamazsa sentetik seri üretilir; mutlak gelir
  rakamları o zaman yalnızca gösterge niteliğindedir.
- **Günlük analiz uyarısı:** günlük akımlar aylık ortalamalardan sentetik türetilir
  (gözlenmiş günlük seri yoktur); mutlak sonuçlar değil, min. kot sonucunun dayanıklılığı okunmalıdır.
- **Gövde en kesiti ön tasarımdır:** stabilite, taşkın kabartması ve dalga tırmanması hesapları
  ayrıca yapılmalıdır.
- **Konsol çıktısı UTF-8'dir;** her betik `sys.stdout.reconfigure(encoding="utf-8")` ile başlar.
