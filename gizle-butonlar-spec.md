# Hezil HES — İmalatçı Paketi & Gövde En Kesiti Butonlarını Gizleme Spec

**Status:** Draft — awaiting implementation approval
**Date:** 2026-08-11
**Related files:** `dashboard.py`, `hezil_dashboard.html` (regenerated), `knowledge.md`, `README.md`

---

## 1. Overview

Hide the two advanced-action buttons in the dashboard's "İşletme çalışması" (operation study)
section — **"📐 İmalatçı paketi üret"** (`#dPaket`) and **"🏗 Gövde en kesiti"** (`#dKesit`) —
**together with their container** (the `margin-left:auto` div holding the "Türbin imalatçısı"
label + both buttons) and the **result area** (`#dPaketSonuc`).

Hiding is the **default**; the feature is re-enabled by flipping a single constant in
`dashboard.py` (`PAKET_VE_KESIT_GOSTER = True`) and regenerating the HTML. The server-side API
endpoints (`/api/imalatci`, `/api/enkesit`) and the standalone CLI scripts
(`imalatci_paketi.py`, `govde_enkesit.py`) are **not** touched — only the dashboard UI hides the
buttons.

---

## 2. Decisions (from user interview)

| # | Topic | Decision |
|---|-------|----------|
| 1 | Hide mode | **Configurable, default hidden** — a `dashboard.py` constant turns the buttons back on; no runtime toggle |
| 2 | Scope of "container" | **Label + both buttons + result area** (`#dPaketSonuc`) all hidden together |
| 3 | Server API endpoints | **Left untouched** — `/api/imalatci` and `/api/enkesit` keep working (session-gated as today); only the UI hides |
| 4 | Where to change | **`dashboard.py` (source) + regenerate** `hezil_dashboard.html` via `python dashboard.py` — the committed HTML is the generated artifact |
| 5 | Config mechanism | **A constant at the top of `dashboard.py`** (near `DETAY_GOMME`), NOT `.env` (dashboard.py doesn't read `.env` today; that would be scope creep) |
| 6 | Hidden mode markup | **Elements are not rendered into the HTML at all** when off (no markup, no `display:none` wrappers) |
| 7 | JS handlers | **Stay in the file**, but every element reference is **null-guarded** so the script cannot crash when the elements are absent |
| 8 | Docs | **`knowledge.md` + `README.md`** get short notes about the flag (pipeline note + feature/setup description) |
| 9 | Constant name | **`PAKET_VE_KESIT_GOSTER`** (default `False` = hidden) |
| 10 | Validation | **Written into the spec** (§9) — regenerate + grep-based checks + browser manual test |

---

## 3. Current state (context)

- `dashboard.py` L459-464 — the container to hide:

```html
        <div style="margin-left:auto">
          <label>Türbin imalatçısı</label>
          <button id="dPaket" class="dugme">📐 İmalatçı paketi üret</button>
          <button id="dKesit" class="dugme"
                  style="background:#8250df;border-color:#8250df;margin-left:6px">
            🏗 Gövde en kesiti</button>
        </div>
```

- `dashboard.py` L474 — the result area (separate container, inside the `.detaySer` left column):

```html
          <div id="dPaketSonuc"></div>
```

- JS references to the hidden elements (all inside `dashboard.py`'s big HTML template; mirrored
  in the generated `hezil_dashboard.html`). **Top-level script order matters** — statements execute
  top-to-bottom at load, so a load-time throw aborts everything below it:
  - L1252: `const pk = $("#dPaketSonuc"); if (pk) pk.innerHTML = "";` — **already null-guarded** ✓
  - L1547: `$("#dPaket").onclick = async () => { ... }` — **NOT guarded**; this is a **top-level
    statement that runs at load** → if `#dPaket` is absent, `TypeError` **aborts the whole script**,
    so L1594, L1646, L1648, the init (L1650) AND the login wiring (L1653+) never run
  - L1594: `$("#dKesit").onclick = async () => { ... }` — **NOT guarded**; same load-time abort
  - L1646-1647: `$("#dAmac").onchange = e => { dAmac = ...; $("#dPaketSonuc").innerHTML = ""; ... }` —
    the registration itself is load-time **safe** (`#dAmac` always exists); the unguarded
    `$("#dPaketSonuc")` reference lives **inside the handler body** and throws only when the user
    changes the operation mode → `detayCiz()` on the same line never runs → the detail view stops
    refreshing. NOT the load-time breaker, but still needs the guard (L1647)
- Order at load: L1547 → L1594 → L1646 → L1648 → L1650 `kurSekmeler(); kurSecimler(); ciz();` →
  L1653 `$("#girisDugmesi").onclick = girisGonder;` (login wiring). The init is synchronous at
  script end; a throw at L1547/L1594 kills the whole bootstrap **including** the login overlay
  wiring — critical, since the server gates everything behind login.
- The HTML template uses `__X__` placeholders (`__VERI__`, `__SENARYOLAR__`, …) replaced at
  generation time in `main()` (L1682-1694: `gomulen` dict → `html.replace(yer, js(nesne))`). The
  self-check (L1696-1712) validates the `const X = …;` JSON slots and reports unfilled `gomulen`
  keys. **The conditional block must NOT go through `gomulen`/`js()`** — `json.dumps` would
  JSON-escape the HTML (quotes → `\"`, newlines → `\n`) and break the markup; it needs a raw
  `html.replace(...)` (see §5.2).
- `DETAY_GOMME = "az"` sits at L121 — the constant block where `PAKET_VE_KESIT_GOSTER` belongs.

---

## 4. Requirements

### 4.1 Functional
- F1. With `PAKET_VE_KESIT_GOSTER = False` (default): the "Türbin imalatçısı" label, both
  buttons, and the `#dPaketSonuc` result area are **absent from the generated HTML markup**.
- F2. With `PAKET_VE_KESIT_GOSTER = True`: the dashboard renders exactly as it does today —
  label, both buttons, and result area present and fully functional.
- F3. The remaining controls in the `.kontroller` row (`#dAmac`, `#dYil`, `#dNeden`, `#dDurum`)
  keep working in both modes.
- F4. The page must never throw a JS error due to the missing elements — in either mode.
- F5. Server endpoints `/api/imalatci` / `/api/enkesit` and the standalone scripts remain
  unchanged and usable (e.g. via curl / CLI) — this feature is UI-only.

### 4.2 Non-functional
- NF1. Only `dashboard.py` (and the regenerated HTML + two doc files) change — no changes to
  `pano_sunucu.py`, `optimzasyon.py`, `imalatci_paketi.py`, `govde_enkesit.py`, `.env`, or
  `requirements.txt`.
- NF2. All UI strings remain Turkish (project convention).
- NF3. The flag follows the existing constant style (`DETAY_GOMME`-like: all-caps, Turkish,
  comment in Turkish) and is documented where it's defined.
- NF4. Regenerating the HTML must not disturb the login overlay (`#girisKatmani` marker must
  remain present — the server warns if missing).

---

## 5. Detailed design

### 5.1 The constant

In `dashboard.py`, right above or below `DETAY_GOMME` (L121):

```python
# İşletme çalışması bölümündeki gelişmiş araç butonları:
#   True  → "İmalatçı paketi üret" + "Gövde en kesiti" butonları ve sonuç alanı gösterilir
#   False → bu butonlar ve #dPaketSonuc HTML'e hiç gömülmez (varsayılan)
PAKET_VE_KESIT_GOSTER = False
```

### 5.2 Conditional markup

The HTML template keeps two placeholders: `__PAKET_KESIT_ALANI__` at the container location
(L459, label + both buttons) and `__PAKET_SONUC_ALANI__` at the result-div location (L474).
Concretely, at generation time:

```python
paket_kesit_blok = ("""
        <div style="margin-left:auto">
          <label>Türbin imalatçısı</label>
          <button id="dPaket" class="dugme">📐 İmalatçı paketi üret</button>
          <button id="dKesit" class="dugme"
                  style="background:#8250df;border-color:#8250df;margin-left:6px">
            🏗 Gövde en kesiti</button>
        </div>""" if PAKET_VE_KESIT_GOSTER else "")
paket_sonuc_blok = ('<div id="dPaketSonuc"></div>' if PAKET_VE_KESIT_GOSTER else "")
```

Fill must be a **raw string replacement**, NOT the `gomulen`/`js()` pipeline (that would
JSON-escape the HTML). Insert the raw replaces **between the existing `gomulen` loop (L1692-1694)
and the self-check block (L1696)** — i.e. immediately after the loop, before the "kendi kendini
denetle" block:

```python
html = html.replace("__PAKET_KESIT_ALANI__", paket_kesit_blok)
html = html.replace("__PAKET_SONUC_ALANI__", paket_sonuc_blok)
if "__PAKET_KESIT_ALANI__" in html or "__PAKET_SONUC_ALANI__" in html:
    raise SystemExit("PANO ÜRETİLEMEDİ: doldurulmamış yer tutucu (PAKET/KESIT)")
```

The leftover-placeholder check mirrors the existing `kalan` guard (L1708) so a typo can't ship a
literal `__…__` string into the page. **Do not convert the HTML template to an f-string** — it is
full of `{}` CSS/JS braces.

### 5.3 Null-guards in JS (JS stays, becomes crash-proof)

The JS handler code remains in the template **unconditionally**, but each reference to the hidden
elements is guarded:

- L1547 → `const pktBtn = $("#dPaket"); if (pktBtn) pktBtn.onclick = async () => { ... };`
- L1594 → `const kesitBtn = $("#dKesit"); if (kesitBtn) kesitBtn.onclick = async () => { ... };`
- L1646-1647 → inside the `#dAmac` onchange: `const pk = $("#dPaketSonuc"); if (pk) pk.innerHTML = "";`
  (L1252 already has `if (pk)` — keep as-is.)

The two handler bodies internally use `$("#dPaket")` / `$("#dKesit")` / `$("#dPaketSonuc")`
again (e.g. `const b = $("#dPaket"), kutu = $("#dPaketSonuc")` at L1549); since they can only run
when the buttons exist, those inner references are safe — but for consistency the guard pattern
is used at every top-level statement that runs at init time.

**Guard variable naming:** use names that do **not** shadow the handler-internal `const b` at
L1549/L1596 — e.g. `pktBtn` for the `#dPaket` guard and `kesitBtn` for the `#dKesit` guard
(avoiding bare `b`/`k`). Legal JS either way, but this removes the shadowing confusion and makes
the §9 validation greps unambiguous.

**L1647 — preserve the `detayCiz()` tail.** The full replacement inside the `#dAmac` onchange
handler is:

```js
$("#dAmac").onchange = e => { dAmac = e.target.value; dAmacElle = true;
  const pk = $("#dPaketSonuc"); if (pk) pk.innerHTML = "";
  detayCiz(); };
```

Only the `$("#dPaketSonuc").innerHTML = "";` fragment is guarded; the `detayCiz();` call on the
same line must be **kept** so the detail view still refreshes when the mode changes.

### 5.4 Docs

- **`knowledge.md`** — add a short note (pipeline/gotcha section): `dashboard.py` has
  `PAKET_VE_KESIT_GOSTER` (default `False`); when off, the imalatçı/enkesit buttons and result
  area are not embedded in the HTML; re-enable by setting `True` and re-running
  `python dashboard.py`. Server endpoints are unaffected.
- **`README.md`** — add one line to the script/feature table or the dashboard section noting the
  default-hidden advanced buttons and how to re-enable them.

---

## 6. Edge cases

| Case | Behavior |
|---|---|
| `PAKET_VE_KESIT_GOSTER = False` (default) | Markup absent; JS guarded → no errors; remaining controls work |
| `PAKET_VE_KESIT_GOSTER = True` | Pixel-identical to today's dashboard; both buttons fully functional |
| Buttons absent, user changes `#dAmac` (operation mode) | Guarded `#dPaketSonuc` clear is skipped; `detayCiz()` still runs (L1647 calls it after the guard), so the detail view refreshes — without the guard the handler throws before `detayCiz()`. `#dYil`/login listeners were already registered at load, unaffected |
| Placeholder typo (`__PAKET_KESIT_ALANI__` left in the template) | Leftover-check in §5.2 raises `SystemExit` — never ships as literal text |
| Buttons absent, user changes `#dYil` | `detayCiz()` runs; `if (pk)` guard (L1252) already skips the result-area clear |
| Script bootstrap with missing elements | No `TypeError` → login overlay wiring (`girisDugmesi.onclick` etc. at script end) still runs — critical, since the server gates everything |
| Standalone `file://` mode | Same HTML, same behavior; buttons simply don't exist |
| Server mode with stale pre-change HTML | Not possible via this change (HTML is regenerated); server's `#girisKatmani` stale-HTML guard unaffected |
| API called directly (curl) while buttons hidden | Still works — by design (decision #3) |
| `PAKET_VE_KESIT_GOSTER` set to a truthy non-`True` value | Treated as truthy (same as `True`) — Python convention |

---

## 7. Out of scope

- Removing or disabling `/api/imalatci` / `/api/enkesit` in `pano_sunucu.py` (kept).
- Touching `imalatci_paketi.py`, `govde_enkesit.py`, `isletme_detay.py` or the optimizer.
- A runtime/`.env`/query-parameter toggle (constant-only per decision #1/#5).
- Reorganizing the `.kontroller` row layout (the container simply disappears; `margin-left:auto`
  had no siblings on its row that depend on it — verified: `#dNeden` and `#dDurum` are separate
  flex items, layout stays clean).
- Removing the now-unused `.paketkutu` CSS block: with `#dPaketSonuc` never populated in hidden
  mode, `.paketkutu` becomes dead CSS. **Leave it untouched** — it is harmless, and deleting it
  would only add risk if the feature is later re-enabled.

---

## 8. Implementation plan (file by file)

1. **`dashboard.py`**
   - Add `PAKET_VE_KESIT_GOSTER = False` (with Turkish comment) next to `DETAY_GOMME` (L121).
   - Replace the L459-464 container markup with a placeholder that fills with the block or `""`.
   - Replace the L474 `<div id="dPaketSonuc"></div>` markup with the same conditional treatment.
   - Add null-guards at L1547, L1594, L1646-1647 (keep the existing L1252 guard). L1547 and
     L1594 are the critical load-time guards — without them the whole script (init + login
     wiring) aborts; L1647 is the runtime guard for the mode-change handler.
2. **Regenerate:** run `python dashboard.py` (project venv: `venv/bin/python dashboard.py`) →
   `hezil_dashboard.html` is rewritten (the `__X__` self-check in `main()` already validates
   placeholders).
3. **`knowledge.md`** — short note about the flag.
4. **`README.md`** — one-line feature note.

---

## 9. Validation plan (no test framework exists; console + grep + browser)

1. Default mode: `python dashboard.py` → then
   `grep -c 'id="dPaket"\|id="dKesit"\|id="dPaketSonuc"' hezil_dashboard.html` → **0**
   (the JS still contains `$("#dPaket")` etc., but that does **not** match the `id="…"` pattern,
   so the count stays 0).
   Guarded JS still present: `grep -cE 'if \([a-zA-Z]+\) [a-zA-Z]+\.onclick'`
   `hezil_dashboard.html` → ≥ 1 (e.g. `if (pktBtn) pktBtn.onclick`) and
   `grep -c 'girisKatmani' hezil_dashboard.html` → ≥ 1 (login overlay intact).
2. Enabled mode: set `PAKET_VE_KESIT_GOSTER = True`, regenerate → the three `id=` markers
   present again (**count = 3** — each of `id="dPaket"`/`id="dKesit"`/`id="dPaketSonuc"` sits on
   its own line, so `grep -c` counts exactly 3 lines) and the same guarded JS remains. Revert to
   `False` and regenerate.
3. Start `venv/bin/python pano_sunucu.py` with the default (hidden) HTML → server boots with no
   warnings; `POST /api/giris` works; `/api/isletme` works with a session; `/api/imalatci` still
   answers with a session (endpoint alive, by design). **Stop the server afterwards** (Ctrl+C) —
   it binds `0.0.0.0:8765` and runs forever otherwise. Note: `.env` with at least one user is
   required to start it (already present in the repo).
4. Browser check (manual — **Chrome is not installed in this environment**, per login-spec
   §10): open the regenerated dashboard (server or `file://`), verify the operation-study section
   renders with the mode selector + period selector working, no console errors, and the
   İmalatçı/Gövde buttons are gone in default mode; repeat with `True` → buttons visible and
   functional.
5. Log in and change operation mode / period with buttons hidden → no JS errors (guards work).

---

## 10. Verification log (2026-08-11 — spec checked against source)

| Claim | Verified? | Note (line refs = current source) |
|---|---|---|
| Container markup location | ✓ | `dashboard.py` L459-464 (`<div style="margin-left:auto">` + label + `#dPaket` + `#dKesit`) |
| Result area location | ✓ | `dashboard.py` L474 `<div id="dPaketSonuc"></div>` |
| `#dPaketSonuc` clear in `detayCiz` already guarded | ✓ | L1252 `if (pk)` |
| `#dPaket` onclick NOT guarded | ✓ | L1547 `$("#dPaket").onclick = ...` |
| `#dKesit` onclick NOT guarded | ✓ | L1594 `$("#dKesit").onclick = ...` |
| `#dPaket` onclick is a top-level load-time statement | ✓ | L1547 runs at script evaluation → aborts everything below (L1594, L1646, L1648, L1650 init, L1653 login wiring) if `#dPaket` is absent — the critical guard |
| `#dKesit` onclick is a top-level load-time statement | ✓ | L1594 — same abort risk as L1547 |
| `#dAmac` onchange touches `#dPaketSonuc` unguarded | ✓ | L1646-1647 — registration safe at load; the throw happens in the handler body on mode change, so `detayCiz()` (same line) is skipped and the detail view stops refreshing |
| Init is synchronous at script end | ✓ | L1650 `kurSekmeler(); kurSecimler(); ciz();` — any throw in the listener block kills bootstrap |
| Constant block location | ✓ | `DETAY_GOMME` at L121 — `PAKET_VE_KESIT_GOSTER` belongs beside it |
| Template placeholder mechanism exists | ✓ | `__VERI__` etc. replaced at generation; `main()` self-check validates placeholders (L1730 prints `DETAY_GOMME`) |
| Server endpoints to keep | ✓ | `pano_sunucu.py` L341 (`/api/enkesit`), L366 (`/api/imalatci`), both session-gated |
| Chrome available for browser testing | ✗ | Not installed — validation step 4 is a manual user test |
| `gomulen`/`js()` pipeline JSON-escapes strings | ✓ | `js = lambda o: json.dumps(...)` L1678; `html.replace(yer, js(nesne))` L1694 — §5.2 must use raw `.replace()` for HTML blocks |
| Self-check reports unfilled `gomulen` keys | ✓ | L1708 `kalan = [y for y in gomulen if y in html]` — §5.2 adds an analogous check for its own placeholders |
| Existing self-check does NOT cover the new placeholders | ✓ | L1698-1700 regexes target only `const X = …;` lines (`VERI`, `SENARYOLAR`, …) — `__PAKET_KESIT_ALANI__`/`__PAKET_SONUC_ALANI__` are markup, not `const`s, so only §5.2's leftover check protects them (confirmed by the L1708 `kalan` iteration over `gomulen` keys only) |
| Handler-internal `const b` at L1549/L1596 | ✓ | `const d = secili.d, b = $("#dPaket"), kutu = $("#dPaketSonuc");` (L1549) and same pattern at L1596 — motivates the `pktBtn`/`kesitBtn` guard naming in §5.3 |
| Script order: listeners → init → login wiring | ✓ | L1547 → L1594 → L1646 → L1648 → L1650 (`kurSekmeler(); kurSecimler(); ciz();`) → L1653 (`$("#girisDugmesi").onclick = girisGonder;`) — load-time throw at L1547/L1594 kills the bootstrap |
| `detayCiz` L1252 guard is `if (pk)` | ✓ | `const pk = $("#dPaketSonuc"); if (pk) pk.innerHTML = "";` — untouched, safe |

**Second pass (same date) — re-verification of the spec against the source:**

| Issue found | Fix applied |
|---|---|
| §3 cascade-break analysis was wrong: it blamed L1646-1647 for "breaking every subsequent listener registration". In reality L1647's unguarded reference is inside the arrow-function body and only throws on the mode-change **event**; the load-time breakers are L1547 and L1594 (top-level `.onclick` assignments that run at script evaluation and abort the whole script, init and login wiring included) | §3 rewritten with the true top-level order (L1547 → L1594 → L1646 → L1648 → L1650 → L1653); L1547/L1594 labeled the critical load-time guards; L1647 re-labeled as the runtime mode-change guard; §8 and the §10 table updated to match |
| §5.2 said "the existing .replace()/placeholder-fill step substitutes either the block or an empty string" — ambiguous; if implemented via `gomulen`, `json.dumps` would escape the HTML and corrupt the markup (verified L1678/L1694) | §5.2 now mandates raw `html.replace(...)` for both placeholders + a leftover-placeholder `SystemExit` check mirroring `kalan` (L1708); two explicit placeholders named (`__PAKET_KESIT_ALANI__`, `__PAKET_SONUC_ALANI__`); f-string example dropped (no interpolation needed) |
| §6 `#dAmac` edge-case row said the guard "keeps `#dYil` listener registering" — `#dYil` registers at load regardless; the real consequence is `detayCiz()` being skipped on mode change | Row reworded; new placeholder-typo edge case added |
| §9 step 3 left a forever-running server | Added "stop the server afterwards (Ctrl+C)" + `.env` prerequisite note |

**Third pass (same date) — independent code-reviewer audit (spawned per request):**

| Finding | Fix applied |
|---|---|
| No definite errors found: all line refs (L121, L459-464, L474, L1252, L1547/1549, L1594/1596, L1646-1648, L1650, L1653, L1678, L1694, L1708, L1730; pano_sunucu.py L341/L366), the load-time-breaker analysis, the `gomulen`/`js()` JSON-escaping claim, and the "count = 3" grep reasoning all verified correct; no other references to the hidden elements exist | No change needed |
| §5.3 L1647 guard example was incomplete — it omitted the `detayCiz();` tail that must be preserved on the same line (an implementer could drop the refresh) | §5.3 now shows the full replacement: `const pk = $("#dPaketSonuc"); if (pk) pk.innerHTML = "";` followed by `detayCiz();` kept on the next line, with an explicit "preserve the tail" note |
| §5.3 guard bullets used `const b`/`const k`, which shadow the handler-internal `const b` at L1549/L1596 — legal but confusing, and it made the §9 grep naming-brittle | Guard names changed to `pktBtn`/`kesitBtn` (bullets updated); §9 grep generalized to `grep -cE 'if \([a-zA-Z]+\) [a-zA-Z]+\.onclick'` so it matches either naming; shadowing rationale added to §5.3 and §10 |
| §8/§3 wording "the `__X__` self-check already validates placeholders" could mislead: the existing self-check (L1698-1712) only covers `gomulen` keys, not the two new markup placeholders | §10 adds an explicit verified row; §5.2 already carries its own leftover check — the wording now points to it as the *only* guard for the new placeholders |
| §9 step 1 grep ambiguity (`if (b) b.onclick` vs `if (k) k.onclick`) | Generalized to `grep -cE 'if \([a-zA-Z]+\) [a-zA-Z]+\.onclick'`; step 1 also notes the JS `$("#dPaket")` references don't match the `id="…"` pattern |
| §9 step 2 wording implied guards differ between modes | Clarified: the guarded JS is unconditional in the template, present in both modes; only the markup differs |
| `.paketkutu` CSS becomes dead in hidden mode — a future "cleanup" could break enabled mode | §7 now explicitly says to leave it untouched |
| §5.2 insertion point was implied rather than stated | Now explicit: insert the raw replaces between the `gomulen` loop (L1692-1694) and the self-check block (L1696) |
