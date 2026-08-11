# Project knowledge

This file gives Freebuff context about your project: goals, commands, conventions, and gotchas.

## What this is

**Hezil Barajı ve HES** (Hezil Dam & hydroelectric power plant) — pre-feasibility / alternative-optimization study, entirely in Turkish. Core engine is a **deterministic dynamic programming (DP)** reservoir-operation optimizer (`optimzasyon.py`); everything else is a scanning, economics, reporting or visualization layer on top of it.

## Pipeline (run order)

1. `python optimzasyon.py` — standalone DP solve. Reads inputs at module level, writes `hezil_dp_sonuclar.xlsx` / `.png`.
2. `python alternatifler.py` — **alternative scan** (tunnel D × design Q × min water level × penstock v), solves DP for each (PİK and BANT objectives), parallel via multiprocessing. Writes `hezil_alternatifler.xlsx` + PNGs. ~1500+ runs, minutes.
3. `python dashboard.py` — reads newest `hezil_alternatifler*.xlsx`, emits a **single-file, dependency-free HTML dashboard** (`hezil_dashboard.html`; data embedded, pure SVG+JS, dark/light).
4. `python pano_sunucu.py` — local HTTP server (port 8765, auto-opens browser) that solves operation studies on demand (`/api/isletme`, `/api/imalatci`, `/api/enkesit`) and caches results to `hezil_onbellek/`. On Windows just double-click `pano_baslat.bat`.

Ancillary analyses (each runnable standalone, all read the newest scan file):
- `isletme_detay.py` — precomputes monthly operation series JSON for selected configs (`hezil_isletme_detay.json`, embedded in dashboard as server-less fallback).
- `sabit_fayda.py` — fixed-tariff scenario (88 €/MWh) re-valuing BANT runs (no DP re-solve).
- `em_duyarlilik.py` — sensitivity of the optimum to EM unit cost (no DP re-solve).
- `gunluk_analiz.py` — daily time-step check of the min-level result (synthetic daily flows; indicative only).
- `govde_enkesit.py` — scaled RCC dam cross-section + vortex submergence calc. Flags: `--senaryo S4`, `--konfig D Q v_c kot`.
- `imalatci_paketi.py` — turbine-manufacturer package (9 graphs + xlsx). Flags: `--senaryo`, `--konfig`, `--amac enerji`.

## Setup / run

- Package manifest: `requirements.txt` (`numpy pandas matplotlib openpyxl scipy`). Install: `pip install -r requirements.txt`. scipy is optional at runtime — used only for PCHIP, pure-numpy fallback exists.
- No tests, no linter, no build step. Validate by running a script and checking its console output/exit code.
- Typical first run: `python alternatifler.py` → `python dashboard.py` → `python pano_sunucu.py`.

## Architecture & data flow

- `optimzasyon.py` = heart. **Module-level global constants** (KOT_MAKS, Q_TASARIM, TUNEL_D, AMAC, …) read from input files at import time; `yeniden_kur()` recomputes all derived quantities after constants are mutated. Callers (scan, detail, server) mutate `opt.*` globals then call `yeniden_kur()`.
- Hydraulics: Darcy-Weisbach (Swamee-Jain) friction + local losses, penstock steel thickness/pressure calc; turbine efficiency from manufacturer curve, homologous scaling.
- Input files: `giris_akimlari.xlsx` (monthly inflow hm³, water year **Ekim→Eylül**), `kot_alan_hacim.xlsx` (elevation-area-volume), `res_operation_table_8760rows.csv` (hourly price, `price` col, EUR/MWh; if missing a synthetic series is generated → absolute revenue figures indicative only).
- 4 scenarios: S1 PİK·piyasa · S2 BANT·piyasa · S3 SABİT 88 €/MWh · S4 YEKDEM (5y 85 + 5y 75 €/MWh bant → 40y market pik). Economics: revenue −9% cut → net revenue − annual cost (investment × 0.12) = net benefit.

## Conventions

- Everything Turkish: identifiers, comments, UI, Excel sheet names, console output. Keep it that way; `# -*- coding: utf-8 -*-` + `sys.stdout.reconfigure(encoding="utf-8")` at the top of every script.
- Matplotlib always `Agg` backend; savefig/Excel writes catch `PermissionError` and fall back to timestamped filenames (`hezil_alternatifler_20260805_181824.xlsx` style). Downstream scripts always pick the **newest** `hezil_alternatifler*.xlsx` via glob-by-mtime — never a hardcoded name.
- When a scan/Excel target is open in Excel, rerunning the producing script writes a timestamped copy; stale reads are a real bug class.

## Gotchas

- **Not thread-safe**: DP mutates module-level globals. `pano_sunucu.py` serializes all DP/plot work under one `threading.Lock`. Never parallelize inside those paths.
- Global DP constants (Q_TASARIM, KOT_MIN, BASLANGIC_KOTU, AMAC, tunnel/penstock dims) are mutated by callers — reset them fully before solving; `BASLANGIC_KOTU` is set to the config's `KOT_MIN` (start-of-year empty reservoir).
- Tünel maliyeti table only spans D 4.0–6.0 m; outside, cost is extrapolated linearly with edge slopes (guard against cubic overshoot).
- `hezil_onbellek/` JSON cache keys look like `4.4_57.8_4.0_700_gelir.json` (D_Q_vc_kot_amac). Stale cache is a gotcha when model inputs change — delete files for changed configs.
- Don't change `INDIRGEME_ORANI`, `EM_BIRIM_EUR_KW`, `GELIR_KESINTI_ORANI` silently — economics/dashboards read or re-derive them from `alternatifler.py` (dashboard parses the constant out of the source text rather than importing).
