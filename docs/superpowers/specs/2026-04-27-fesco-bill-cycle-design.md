# FESCO Bill Cycle — Design Spec

**Date:** 2026-04-27
**Status:** Approved (in brainstorming)
**Owner:** Bilal

## 1. Problem

The Savings page currently aggregates energy and PKR over **calendar months** (`YYYY-MM` from `daily_stats.date`). Reality is different: FESCO reads the meter on the **26th** of each month (next working day if the 26th is Sat/Sun) and bills against that 26th-to-26th cycle. Consequences:

- The "this month's savings" number is wrong by up to ~5 days every cycle.
- The slab-cliff projection misaligns with the slab the FESCO bill will actually land in.
- The user has no view of last-12-months unit history, no forecasted bill for the open cycle, no tracking of NEPRA "Protected" status, and no way to record the actual bill that arrives.

## 2. Goals

1. Aggregate energy and savings over the **FESCO billing cycle**, not the calendar month.
2. Forecast the open cycle's units and bill total using a simple run-rate.
3. Maintain a 12-month history of bills (units + PKR) the same way a FESCO bill does.
4. Auto-detect Protected / Unprotected status from history and predict when it will flip.
5. Add a new top-level **FESCO Bill** page that mirrors the actual bill's layout.

## 3. Non-Goals

- No multi-tenant / multi-meter support — single user, single meter.
- No payment integration. Payment amount is just a recorded number.
- No PDF parsing of the FESCO bill — manual entry only.
- No timezone work. App runs in Asia/Karachi, no DST.

## 4. Architecture Overview

Four new Python modules, one new HTML page, one new JS file, additive changes to existing modules. No edits to `power_stats.py`, `inverter_status.py`, `continuous_reader.py`, or `auth.py`.

```
new:
  fesco_bill.py            pure functions: boundaries, aggregation, forecast, status
  fesco_cycles.py          CRUD over billing_cycles table (thread-safe like CostConfig)
  templates/fesco_bill.html
  static/js/fesco_bill.js

changed:
  cost_savings.py          add compute_savings_for_cycle; switch build_full_payload
  lesco_tariff.py          add fix_charges_total; compute_bill includes fix charges
  cost_config.py           add new default keys (reading_day_of_month, etc.)
  app.py                   register /fesco-bill page + /fesco/* JSON routes
  templates/dashboard.html add "Record bill" banner (after reading date)
  templates/solar_flow.html add nav item "FESCO Bill"
  templates/savings.html   relabel "this month" → "this cycle" + cycle dates
```

## 5. Data Model

### 5.1 New table: `billing_cycles`

Created idempotently by `fesco_cycles.py._init_db()` in the same SQLite database as `daily_stats` and `cost_config`.

```sql
CREATE TABLE IF NOT EXISTS billing_cycles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_label TEXT NOT NULL UNIQUE,        -- "Mar26"
  start_date TEXT NOT NULL,                -- ISO 'YYYY-MM-DD' (day after prev reading)
  end_date TEXT NOT NULL,                  -- ISO 'YYYY-MM-DD' (reading date)
  status TEXT NOT NULL,                    -- 'open' | 'closed'
  units_estimated REAL,                    -- summed grid_kwh from daily_stats
  units_actual INTEGER,                    -- from real bill (NULL until entered)
  bill_amount_estimated REAL,              -- compute_bill(units_estimated, cfg).total
  bill_amount_actual REAL,                 -- from real bill
  payment_amount REAL,                     -- from real bill (NULL = unpaid)
  fpa_per_unit_actual REAL,                -- captured from real bill, overrides cfg FPA on recompute
  notes TEXT,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cycles_end_date ON billing_cycles(end_date DESC);
```

`cycle_label` format: 3-letter month + 2-digit year, e.g. `Mar26`, `Apr26`. Matches the format on the FESCO bill grid.

### 5.2 New keys in `cost_config`

Added to `DEFAULT_NON_TARIFF` in [cost_config.py](../../../cost_config.py):

```python
"reading_day_of_month": 26,
"weekend_rolls_to_monday": True,
"fix_charges_per_kw": 300,        # 300 × sanctioned_load_kw
"consumer_id": "",
"tariff_code": "A-1a(01)",
"connection_date": None,          # ISO 'YYYY-MM-DD'
"meter_no": "",
"discom_name": "FESCO",
```

The existing `monthly_billing_day = 1` key is **left in place** but ignored by new code. Removing it would break any cached config blob already written. New code reads only the new keys.

### 5.3 No changes to existing tables

`daily_stats` is the source of truth for energy. Cycle aggregation is a SQL `WHERE date BETWEEN start AND end` query against it.

## 6. Pure-function API (in `fesco_bill.py`)

All functions are deterministic given inputs — no I/O except the explicit `db_path` arg. Easy to unit-test.

```python
def compute_cycle_boundaries(today: date, cfg: dict) -> tuple[date, date]:
    """Returns (start_date, end_date) for the cycle containing `today`.
    end_date = next reading date >= today (26th, weekend-adjusted, day-clamped).
    start_date = day after the previous cycle's end_date.
    Override path: if billing_cycles has an open row whose end_date was
    manually set, use those bounds instead."""

def aggregate_cycle(start: date, end: date, db_path: str) -> dict:
    """SUM grid_energy, solar_energy, load_energy from daily_stats WHERE
    date BETWEEN start AND end. Returns kWh values."""

def forecast_open_cycle(cfg: dict, db_path: str, stats_manager) -> dict:
    """Run-rate forecast for the current open cycle. Returns:
    { start, end, days_elapsed, days_remaining, units_so_far,
      projected_units, daily_avg_kwh, forecast_bill, same_month_last_year_units }."""

def detect_protected_status(closed_cycles: list[dict]) -> dict:
    """Apply NEPRA rule: protected if last 6 closed cycles all <= 200 units.
    Uses units_actual; falls back to units_estimated if missing.
    Returns 'unknown' if fewer than 6 closed cycles exist."""

def predict_status_flip(closed_cycles: list[dict], open_forecast: dict, cfg: dict) -> dict:
    """Walk a forward timeline = closed cycles + open forecast + 6 hypothetical
    cycles at trailing-3-month average. For each cycle, compute the rolling
    6-cycle window, check if all <= 200. Return the first cycle where status
    flips, or null if no flip in horizon."""
```

### 6.1 `compute_cycle_boundaries` — exact algorithm

```
target_day = cfg["reading_day_of_month"]   # default 26

# Step 1: find the end_date (next reading date >= today, weekend-adjusted)
month_iter = today
loop:
  candidate = clamp(date(month_iter.year, month_iter.month, target_day),
                    last_day_of(month_iter))
  if cfg["weekend_rolls_to_monday"]:
    if weekday(candidate) == SAT: candidate += 2 days
    elif weekday(candidate) == SUN: candidate += 1 day
  if candidate >= today:
    end = candidate
    break
  month_iter = first_of_next_month(month_iter)

# Step 2: find start_date.
# Prefer the most recent CLOSED cycle's end_date + 1 (handles user overrides).
# Fall back to applying the rule one month back.
last_closed = SELECT end_date FROM billing_cycles
              WHERE status='closed' ORDER BY end_date DESC LIMIT 1
if last_closed and last_closed < end:
  start = last_closed + 1 day
else:
  prev_month = first_of_prev_month(end)
  prev_candidate = clamp(date(prev_month.year, prev_month.month, target_day),
                         last_day_of(prev_month))
  apply weekend rule to prev_candidate
  start = prev_candidate + 1 day
```

Edge case: `target_day=31`, month has 30 days → clamp to last day, then apply weekend rule. Documented in the unit test.

### 6.2 `forecast_open_cycle` — exact math

```
start, end = compute_cycle_boundaries(today, cfg)
total_days   = (end - start).days + 1
elapsed_days = (today - start).days + 1
units_so_far = aggregate_cycle(start, today, db)["grid_kwh"]
daily_avg    = units_so_far / elapsed_days   if elapsed_days > 0 else 0
projected    = units_so_far * (total_days / elapsed_days)
              if elapsed_days > 0 else 0
forecast_bill = compute_bill(projected, cfg)   # already includes fix charges (§7)
same_month_last_year = SELECT units_actual FROM billing_cycles
                       WHERE cycle_label = '{Mar25 if today is in Mar26 cycle}'
```

### 6.3 `predict_status_flip` — exact algorithm

```
timeline = closed_cycles + [open_forecast as pseudo-closed]
trailing_avg = mean(units of last 3 timeline entries)
for i in 1..6:
  timeline.append(pseudo-cycle with units = trailing_avg, label="+i months")

# current_status anchors the search; we only return flips that come AFTER it.
current_status = detect_protected_status(closed_cycles).status
prev_status = current_status

# Start scanning from the open-forecast entry onward (i.e. future cycles only).
scan_start_index = len(closed_cycles)   # index of the open-forecast entry
for i in scan_start_index .. len(timeline) - 1:
  if i < 5: continue   # need 6 entries in the rolling window
  window_6 = timeline[i-5 .. i]
  status = "protected" if all(c.units <= 200 for c in window_6) else "unprotected"
  if status != prev_status:
    is_forecast = (i == scan_start_index)
    return { flips_to: status, at_cycle: timeline[i].label,
             condition: "if {timeline[i].label} <= 200 units" if is_forecast else None }
  prev_status = status
return { flips_to: null, horizon_end: timeline[-1].label }
```

## 7. Tariff changes

In [lesco_tariff.py](../../../lesco_tariff.py):

- Add `fix_charges_total(cfg)` returning `cfg["fix_charges_per_kw"] * cfg["sanctioned_load_kw"]` (default 300 × 3.3 = 990, but matches user's 300 × 3 = 900 with their `sanctioned_load_kw` overridden).
- In `compute_bill`, add a `fix_charges` line (post-energy, pre-FPA) and include it in `pre_tax`. GST and ED apply to it (matches FESCO bill where 900 is in FESCO Charges and the 1122 GST is computed across the full pre-tax).
- Returned dict gets a new `fix_charges` field.

## 8. Savings integration

In [cost_savings.py](../../../cost_savings.py):

- Add `compute_savings_for_cycle(db_path, start, end, cfg)` — same shape as `compute_savings_for_month` but takes date bounds.
- `build_full_payload(stats_manager, cost_config)` switches:
  - `month_block` → `cycle_block` using current open cycle's bounds
  - `compute_slab_projection` reads cycle bounds instead of calendar month (rename internally; same math)
  - `compute_lifetime` walks `billing_cycles` (closed) instead of synthesized calendar months. Uses `units_actual` if present, else `units_estimated`.
- `compute_savings_for_month` is preserved and used by [history.html](../../../templates/history.html) only.

## 9. CRUD module (`fesco_cycles.py`)

Thread-safe singleton modeled on `CostConfig`:

```python
class CycleStore:
    def __init__(self, db_path: str)
    def list_cycles(self, limit: int = 24) -> list[dict]
    def get_cycle(self, label: str) -> dict | None
    def upsert_cycle(self, cycle: dict) -> dict
    def delete_cycle(self, label: str) -> None
    def bootstrap_history(self, rows: list[dict]) -> int
        """Bulk-insert 12 history rows; back-compute start_date/end_date from
        the reading-day rule. Skips rows whose label already exists."""
    def ensure_open_cycle(self, cfg: dict, db_path: str) -> dict
        """If no row with status='open' exists, create one for the current
        cycle bounds. If today is past the open cycle's end_date, mark the
        old open cycle as 'closed' (auto-fill units_estimated and
        bill_amount_estimated) and create the new open cycle."""
```

`ensure_open_cycle` is called on every `GET /fesco/bill` and `GET /fesco/cycles` so the cycle list stays current without a background scheduler.

## 10. HTTP API

All under `@login_required`. Writes use the existing CSRF pattern from `/savings/config`. JSON in/out.

| Method | Path | Purpose |
|---|---|---|
| GET | `/fesco-bill` | Page (template render) |
| GET | `/fesco/cycles` | List cycles (sorted desc), summary fields |
| GET | `/fesco/bill?cycle=<label>` | Full bill payload; defaults to open cycle |
| GET | `/fesco/status` | Protected status + flip prediction |
| POST | `/fesco/cycle` | Upsert one cycle (edit modal + bootstrap row) |
| POST | `/fesco/bootstrap` | Bulk insert 12 history rows |
| DELETE | `/fesco/cycle/<label>` | Remove (Settings only, with confirm) |

`GET /fesco/bill` payload shape:

```json
{
  "cycle": {
    "label": "Mar26", "start_date": "...", "end_date": "...", "status": "open",
    "units_estimated": 67.4, "units_actual": null,
    "bill_amount_estimated": 7863.2, "bill_amount_actual": null,
    "payment_amount": null, "fpa_per_unit_actual": null
  },
  "header": {
    "consumer_id": "...", "tariff_code": "...", "load_kw": 3.0,
    "connection_date": "...", "meter_no": "...",
    "reading_date": "2026-04-26", "due_date": "2026-05-08"
  },
  "forecast": { /* if status=open */ },
  "bill_breakdown": { /* full compute_bill result + fix_charges + lp_surcharge */ },
  "history": [ {label, units, bill_amount, paid}, ... 12 rows ],
  "status": { /* detect_protected_status + predict_status_flip */ }
}
```

`due_date` = `reading_date + 13 days` (per the bill: 26 Mar reading → 8 Apr due is 13 days). Hardcoded in `fesco_bill.py` as a constant `DUE_DATE_OFFSET_DAYS = 13`.

`lp_surcharge` line: 4% of payable amount if paid after due_date, 8% after due_date + 5 days. Numbers from the user's bill: 308 / 616 on 7597 = 4.05% / 8.1%. Use **4%** and **8%** (matches NEPRA spec; small rounding on FESCO's side).

## 11. Page UI

Layout described in Section C of brainstorming chat. ASCII summary:

```
[Header: consumer/tariff/load/reading-date/due-date]
[Banner: ESTIMATED · cycle in progress · X of N days elapsed]
[2-column charge grid: FESCO Charges | GOVT Charges]
[Slab breakdown card with cliff warning]
[Payable + L.P. surcharge rows]
[12-month history grid with edit pencils]
[+ Enter actual bill for {cycle}]  <-- only on open cycle
```

### 11.1 State variants
- **Open**: ESTIMATED badge, forecast numbers, cliff warning if relevant, "Enter actual bill" CTA.
- **Closed with actuals**: ACTUAL badge, side-by-side "Estimated vs Actual" mini-card.
- **Closed without actuals**: ESTIMATED — awaiting bill, prominent edit pencil.
- **Bootstrap (no rows)**: Only the 12-row paste form is shown.

### 11.2 Cycle picker
Dropdown sorted desc, pinned open-cycle at top. Selecting updates URL to `/fesco-bill?cycle=Feb26` for bookmarkability.

### 11.3 Edit modal
Fields: `reading_date` (defaults to computed end_date), `units_actual` (int), `bill_amount_actual` (PKR), `payment_amount` (PKR, optional), `fpa_per_unit_actual` (defaults to current `cfg.fpa_per_unit`), `notes`. On save → upsert, status='closed', protected detection re-runs, savings page payload invalidated (no caching layer to bust — just a fact).

If `reading_date` differs from the current row's `end_date`, the **next** open cycle's `start_date` shifts to the new `reading_date + 1`. `fesco_cycles.upsert_cycle` triggers a recompute of the next cycle's bounds when this happens (or marks the next open cycle stale so the next `ensure_open_cycle` call rebuilds it).

### 11.4 Bootstrap form
Visible only when `billing_cycles` is empty. 12 rows × 3 fields (Month dropdown / Units int / Bill paid PKR). Submit → POST `/fesco/bootstrap`. Months default to the last 12 calendar months relative to today.

### 11.5 Live screen banner
In [dashboard.html](../../../templates/dashboard.html) and [solar_flow.html](../../../templates/solar_flow.html): if today >= the most recent open-or-recently-closed cycle's `end_date + 1` AND that cycle has no `bill_amount_actual`, show a dismissible (per-day, localStorage) banner: **"FESCO Mar26 bill is out — record it"** linking to `/fesco-bill`.

## 12. Edge cases

| Case | Behavior |
|---|---|
| Mid-cycle config edit (slab/FPA) | Open cycle forecast recomputes immediately. Closed cycles keep stored `bill_amount_actual` (truth). |
| Reading day 31 in 30-day month | Clamp to last day of month, then apply weekend rule. |
| App installed mid-cycle | First `start_date` = earliest `daily_stats.date`. Cycle marked `partial=true` in `notes`; UI shows "partial cycle." |
| Paste form skips a month | Allowed. Protected detection requires 6 *consecutive* closed cycles; gaps yield "unknown." |
| Negative bill (refund/adjustment, e.g. May25 -1376) | Stored as-is. UI renders red as "Adjustment / Refund." |
| User manually sets `consumer_type` after auto-detection | Manual wins until next cycle closes; on close, auto-detection runs and overwrites. Note appended to cycle's `notes`. |
| Timezone | All dates ISO `YYYY-MM-DD` in Asia/Karachi. No UTC. |
| No closed cycles yet (fresh app, before bootstrap) | Page shows only the bootstrap form. Savings page falls back to calendar-month logic until a cycle is closed. |
| `fpa_per_unit_actual` was set on a closed cycle | When recomputing that cycle's `bill_amount_estimated`, use the per-cycle FPA, not the current config FPA. |

## 13. Testing

Unit tests in `test_fesco_bill.py`:

1. `compute_cycle_boundaries`:
   - 26th lands on Mon-Fri (no rollover)
   - 26th on Saturday → Monday 28th
   - 26th on Sunday → Monday 27th
   - Month with 30 days, day=31 → 30th, then weekend rule
2. `aggregate_cycle`: seed 5 daily_stats rows, assert kWh sums.
3. `forecast_open_cycle`: frozen time at midpoint of cycle, seeded data, assert `projected_units = 2 * units_so_far`.
4. `detect_protected_status`:
   - Real 12-month series from user's bill → "unprotected, 306 in Sep25 violates"
   - Synthetic series of 6 × 150 → "protected"
   - 5 closed cycles → "unknown"
5. `predict_status_flip`:
   - User's series + Apr forecast at 180 → flips_to=protected at May26
   - User's series + Apr forecast at 250 → still unprotected, no flip in horizon
6. `fix_charges_total`: 3.3 kW × 300 = 990; 3.0 kW × 300 = 900.

Flask integration tests:
- `POST /fesco/bootstrap` with 12 rows → `GET /fesco/cycles` returns 12.
- `GET /fesco/bill` with no cycles → 200, payload signals bootstrap state.
- `POST /fesco/cycle` with actuals → `GET /fesco/status` reflects updated detection.

No DOM-level tests for `fesco_bill.html`. Smoke render via `flask test_client.get('/fesco-bill')` asserting 200 + key strings present.

## 14. Migration notes

- `cost_config` row is loaded via `_build_default()` which already merges new keys over stored JSON. Existing users transparently get the new defaults on next load.
- `billing_cycles` table is created if-not-exists on first import of `fesco_cycles`.
- No data migration. Existing `daily_stats` is read as-is; cycle aggregation is just a different SQL query.

## 15. Out of scope (explicitly)

- PDF parsing of FESCO bill — manual entry only.
- Email/SMS reminders for due date — only in-app banner.
- Per-meter or per-property support — single-meter only.
- Push notifications — browser only, no native.
- Auto-fetching the bill from FESCO's web portal — out of scope (their portal has no API; would need scraping).

## 16. Future enhancements (not in this spec)

- Mobile app port (already in [mobile-design-prompt.md](../../../mobile-design-prompt.md)).
- Bill PDF upload + OCR auto-fill of units/amount.
- Tariff history (when FESCO/NEPRA changes slab rates, store the dated change so old cycles re-compute against the rates that were in effect at the time).
