# Hezil Dam & HPP — Alternative Optimization Study

A **pre-feasibility / alternative optimization study** for the Hezil Dam and Hydropower Plant (HPP).
Using monthly inflows and hourly market prices, the reservoir operation policy is optimized with
**deterministic dynamic programming (DP)**, and 1,512 alternatives are screened across the
tunnel diameter × design discharge × penstock velocity × minimum operating level space.

*Note: the project itself (code, comments, Excel sheets, console output, dashboard UI) is entirely
in Turkish — all identifiers, comments, and UI labels follow the Turkish terminology.*

---

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Installation](#installation)
- [Usage (pipeline order)](#usage-pipeline-order)
- [Scripts and command line](#scripts-and-command-line)
- [Input files](#input-files)
- [Scenarios and economics](#scenarios-and-economics)
- [Outputs](#outputs)
- [Project structure](#project-structure)
- [Important constraints and gotchas](#important-constraints-and-gotchas)

---

## Features

- **DP-based reservoir operation optimization** — the monthly reservoir operation policy is solved
  via backward induction to maximize market revenue (day-ahead price / PTF).
  - *Peak (PİK) operation*: the plant runs at full load for a few hours each month; generation is
    sold at the month's most expensive hours (the price-duration curve enters the DP as a concave
    benefit function).
  - *Baseload (BANT) operation*: only generated energy is maximized; revenue is valued at the
    month's average price.
- **4-dimensional alternative screening** — 7 tunnel diameters × 6 tunnel velocities × 6 penstock
  velocities × 6 minimum levels = **1,512 configurations**, each solved separately for the PİK and
  BANT objectives (parallelized with multiprocessing).
- **4 scenarios** — PİK·market, BANT·market, FIXED 88 €/MWh, YEKDEM (tiered feed-in guarantee).
- **Self-contained, single-file interactive dashboard** — `hezil_dashboard.html` (embedded data,
  pure SVG + JS, dark/light theme). No internet or libraries required.
- **Local dashboard server** — solves the operation study of any alternative on demand
  (`pano_sunucu.py`, port 8765) and caches results.
- **Turbine manufacturer data package** (9 charts + Excel) and a **scaled RCC dam cross-section**.
- **Sensitivity analyses** — fixed tariff, EM unit cost, and daily time-step effects (no DP re-solve).

---

## How it works

```
giris_akimlari.xlsx  ──┐
kot_alan_hacim.xlsx  ──┼──►  optimzasyon.py  (DP core)
res_operation_table..csv ─┘        │
                                   ▼
                          alternatifler.py  ──►  hezil_alternatifler*.xlsx + PNG
                                   │
                                   ▼
                          dashboard.py  ──►  hezil_dashboard.html (single file)
                                   │
                                   ▼
                          pano_sunucu.py  ──►  http://127.0.0.1:8765
                                   (solves operation studies on demand,
                                    caches into hezil_onbellek/)
```

- **`optimzasyon.py`** is the heart: module-level global input constants (KOT_MAKS, Q_TASARIM,
  TUNEL_D, AMAC, …); callers mutate these constants and call `yeniden_kur()` to refresh the model.
- Hydraulics: Darcy-Weisbach (Swamee-Jain) friction + ΣK·v²/2g local losses; turbine efficiency is
  scaled homologously from the manufacturer curve; penstock wall thickness/pressure is calculated.
- Economics: annual cost = (tunnel + EM + plant) investment × 0.12 annualization rate;
  net benefit = annual revenue − annual cost.

---

## Installation

```bash
pip install -r requirements.txt
```

Requirements: `numpy`, `pandas`, `matplotlib`, `openpyxl` (and `scipy`).
**Note:** scipy is used only for PCHIP interpolation; a pure-numpy fallback exists, so it is not
strictly required at runtime.

There is no test, linter, or build step. Validation means running a script and checking its
console output/output files.

---

## Usage (pipeline order)

```bash
# 1) Standalone DP solve (optional — produces example output)
python optimzasyon.py

# 2) Alternative screening (1,512 alternatives × PİK+BANT = ~3,000 DP runs, a few minutes)
python alternatifler.py

# 3) Generate the single-file HTML dashboard
python dashboard.py

# 4) Local server (solves operation studies on demand, opens the browser)
python pano_sunucu.py
#    On Windows, double-click: pano_baslat.bat
#    Stop with: Ctrl+C
```

Even without the server running, double-clicking `hezil_dashboard.html` opens the dashboard; only
the operation-study section falls back to the embedded data.

---

## Scripts and command line

| Script | What it does | Output |
|---|---|---|
| `optimzasyon.py` | DP operation optimization + report for a single configuration | `hezil_dp_sonuclar.xlsx`, `.png` |
| `alternatifler.py` | Screens 1,512 alternatives (PİK + BANT) | `hezil_alternatifler*.xlsx`, `hezil_alternatifler.png`, `hezil_ekonomi.png` |
| `dashboard.py` | Embeds the screening results into a single-file HTML dashboard | `hezil_dashboard.html` |
| `pano_sunucu.py` | Local HTTP server; `/api/isletme`, `/api/imalatci`, `/api/enkesit` | cache: `hezil_onbellek/*.json` |
| `isletme_detay.py` | Precomputes operation series for selected configurations | `hezil_isletme_detay.json` |
| `sabit_fayda.py` | Fixed-tariff (88 €/MWh) scenario — no DP re-solve | `hezil_sabit_fayda.xlsx`, `.png` |
| `em_duyarlilik.py` | Sensitivity of the optimum to EM unit cost — no DP re-solve | `hezil_em_duyarlilik.xlsx`, `.png` |
| `gunluk_analiz.py` | Daily time-step check (does the min-level result change?) | `hezil_gunluk_analiz.xlsx`, `.png` |
| `govde_enkesit.py` | Scaled RCC dam cross-section + vortex submergence | `hezil_govde_enkesit_*.png` |
| `imalatci_paketi.py` | 9-chart + Excel package for the turbine manufacturer | `hezil_imalatci_paketi.png`, `.xlsx` |

### Command-line flags

`govde_enkesit.py` and `imalatci_paketi.py`:

```bash
python govde_enkesit.py                    # → S1 optimum
python govde_enkesit.py --senaryo S4       # → YEKDEM optimum
python govde_enkesit.py --konfig 4.4 60 5.0 720   # manual: (D, Q, v_c, level)

python imalatci_paketi.py                  # → S1 optimum
python imalatci_paketi.py --senaryo S4     # → YEKDEM optimum
python imalatci_paketi.py --konfig 4.4 60 5.0 720
python imalatci_paketi.py --amac enerji    # → baseload operation (default: peak/revenue)
```

### Screening grid (`alternatifler.py`)

| Dimension | Values |
|---|---|
| Tunnel diameter | 4.0 / 4.4 / 4.8 / 5.0 / 5.2 / 5.6 / 6.0 m (length fixed at 4,600 m) |
| Tunnel velocity | 2.8 – 3.8 m/s (6 steps; Q = v·πD²/4) |
| Penstock velocity | 3.5 – 6.0 m/s (6 steps; diameter computed accordingly, length 300 m) |
| Minimum operating level | 690 – 740 m (5 m steps; max level fixed at 755 m) |

Total: 7 × 6 × 6 × 6 = **1,512 configurations**.

---

## Input files

| File | Contents |
|---|---|
| `giris_akimlari.xlsx` | Monthly inflows [hm³], water year **October → September** |
| `kot_alan_hacim.xlsx` | Elevation–area–volume table (elevation [m] · area [km²] · volume [hm³]) |
| `res_operation_table_8760rows.csv` | Hourly market price (column: `price`, EUR/MWh). If missing, a synthetic series is generated → absolute revenues are indicative only |

---

## Scenarios and economics

| Code | Scenario | Operation | Valuation |
|---|---|---|---|
| S1 | PİK · market | PİK (revenue max.) | hourly day-ahead price, most expensive hours |
| S2 | BANT · market | BANT (energy max.) | monthly average price |
| S3 | Fixed 88 €/MWh | BANT | fixed unit benefit |
| S4 | YEKDEM | BANT → PİK | 5 yr 85 €/MWh + 5 yr 75 €/MWh (baseload) → 40 yr market (peak) |

Economics constants (`alternatifler.py`):

- Annualization rate: `INDIRGEME_ORANI = 0.12` (investment → annual cost)
- EM unit cost: `EM_BIRIM_EUR_KW = 140.0` €/kW
- Plant + switchyard: `SANTRAL_SALT_EUR_KW = 75.0` €/kW
- Revenue deduction: `GELIR_KESINTI_ORANI = 0.09` (gross revenue → net revenue)
- Net benefit = annual revenue − annual cost = (gross revenue × 0.91) − (investment × 0.12)

---

## Outputs

- **`hezil_dashboard.html`** — interactive, single-file dashboard of the screening results:
  multi-scenario selection, selectable axes (25+ metrics), filters (diameter/velocity/level),
  each scenario's optimum is ringed and summarized as a card, fixed-cost and B/C < 1 elimination
  tools, an operation-study section (solved live by the server), and an alternatives table.
- **`hezil_alternatifler*.xlsx`** — Inputs + All Alternatives + Economics + Top 20 + Reference +
  pivot tables. When the target file is open in Excel, a timestamped backup is written instead;
  downstream scripts always read the **newest** file.
- **PNG reports** — energy/revenue screening, economics, sensitivities, daily analysis,
  cross-section, manufacturer package, etc.

---

## Project structure

```
hezil/
├── optimzasyon.py          # DP core (global constants + yeniden_kur())
├── alternatifler.py        # 1,512-alternative screening + economics
├── dashboard.py            # single-file HTML dashboard generator
├── pano_sunucu.py          # local server (port 8765) — on-demand operation solves
├── pano_baslat.bat         # Windows double-click launcher
├── isletme_detay.py        # precomputes operation series (JSON)
├── sabit_fayda.py          # fixed-tariff scenario
├── em_duyarlilik.py        # EM cost sensitivity
├── gunluk_analiz.py        # daily time-step check
├── govde_enkesit.py        # RCC dam cross-section
├── imalatci_paketi.py      # turbine manufacturer package
├── giris_akimlari.xlsx     # monthly inflows (input)
├── kot_alan_hacim.xlsx     # elevation-area-volume (input)
├── res_operation_table_8760rows.csv  # hourly price (input)
├── requirements.txt
├── knowledge.md            # project knowledge file (AI context)
├── hezil_onbellek/         # server cache (D_Q_vc_kot_amac.json)
└── hezil_*.xlsx / *.png    # generated outputs
```

---

## Important constraints and gotchas

- **Not thread-safe:** DP mutates module-level globals (Q_TASARIM, KOT_MIN, BASLANGIC_KOTU, AMAC,
  diameters…). `pano_sunucu.py` serializes all DP/plot work under a single `threading.Lock`.
  Never parallelize inside those paths.
- **Reset globals fully before solving:** `BASLANGIC_KOTU` is set to the configuration's
  `KOT_MIN` (start-of-year empty reservoir). Partial resets produce stale results.
- **Tunnel cost table only covers D 4.0–6.0 m;** outside that range cost is extrapolated linearly
  with edge slopes (to avoid cubic overshoot).
- **The `hezil_onbellek/` cache can go stale:** after model inputs change, delete the JSON files
  for the changed configurations (key format: `4.4_57.8_4.0_700_gelir.json`).
- **Don't change economics constants silently** (`INDIRGEME_ORANI`, `EM_BIRIM_EUR_KW`,
  `GELIR_KESINTI_ORANI`): `dashboard.py` reads the annualization rate from the source text via
  regex; a mismatch desynchronizes the dashboard and the Excel results.
- **Stale-file reads:** when the screening/Excel target is open in Excel, the producing script
  writes a timestamped backup; downstream scripts select the **newest** `hezil_alternatifler*.xlsx`
  via glob-by-mtime — never use a hardcoded name.
- **Synthetic price warning:** if the price file is missing, a synthetic series is generated;
  absolute revenue figures are then indicative only.
- **Daily-analysis warning:** daily inflows are synthesized from monthly averages (no observed
  daily series exists); read the robustness of the min-level result, not the absolute numbers.
- **Dam cross-section is preliminary:** stability, flood surcharge, and wave run-up calculations
  must be performed separately.
- **Console output is UTF-8;** every script starts with `sys.stdout.reconfigure(encoding="utf-8")`.
