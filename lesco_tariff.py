"""LESCO domestic tariff calculator.

Pure functions: take a units number + a config dict, return a full bill breakdown
in PKR. No I/O, no globals — every rate is read from the passed-in config so the
frontend can override anything (slab edges, per-unit rates, FPA, GST, surcharges).

Two slab modes are supported because LESCO bills protected and unprotected
consumers differently:

  - "telescopic": each slab charges its own rate for the units that fall in it.
    Used for Protected category. 250 units = 100*r1 + 100*r2 + 50*r3.
  - "flat": the slab the *total* consumption lands in sets a single rate for
    every unit. This is the Pakistani "single-block" cliff. 250 units at the
    201-300 slab = 250 * r3. This is what makes crossing 200 units hurt.

Default config below mirrors the NEPRA / LESCO January 2026 schedule for
domestic A-1 consumers. FPA is monthly-variable so it's exposed as a top-level
field rather than baked into slab rates.
"""

from __future__ import annotations

from typing import Any
from copy import deepcopy


DEFAULT_CONFIG: dict[str, Any] = {
    "consumer_type": "unprotected",  # "protected" | "unprotected"
    "sanctioned_load_kw": 3.3,        # Galaxy Primax 3.3 kW
    "fpa_per_unit": 4.5,              # Fuel Price Adjustment, monthly notification
    "qtr_adjustment_per_unit": 0.0,   # Quarterly Tariff Adjustment (optional)

    # All taxes/surcharges. Edit any from the UI.
    "gst_percent": 17.0,
    "electricity_duty_percent": 1.5,
    "fc_surcharge_per_unit": 3.23,    # Financing Cost surcharge
    "nj_surcharge_per_unit": 0.0,     # Neelum-Jhelum surcharge (frequently 0 lately)
    "tv_fee_pkr": 35.0,
    "extra_tax_percent": 0.0,         # FBR extra tax for non-filers, etc.

    # Minimum bill thresholds (PKR). LESCO charges max(computed, minimum).
    "min_bill_below_5kw": 600.0,
    "min_bill_5kw_or_above": 2000.0,

    # Protected slabs (telescopic): consumed in order until total is exhausted.
    "protected_slabs": [
        {"up_to": 50,  "rate": 3.95,  "label": "Lifeline 1-50"},
        {"up_to": 100, "rate": 10.54, "label": "Protected 51-100"},
        {"up_to": 200, "rate": 13.01, "label": "Protected 101-200"},
    ],

    # Unprotected slabs (flat): pick the slab the total falls in, apply once.
    # `up_to` = None means "everything above the previous slab".
    "unprotected_slabs": [
        {"up_to": 100,  "rate": 22.44, "label": "1-100"},
        {"up_to": 200,  "rate": 28.91, "label": "101-200"},
        {"up_to": 300,  "rate": 33.10, "label": "201-300"},
        {"up_to": 400,  "rate": 36.46, "label": "301-400"},
        {"up_to": 500,  "rate": 38.95, "label": "401-500"},
        {"up_to": 600,  "rate": 40.22, "label": "501-600"},
        {"up_to": 700,  "rate": 41.85, "label": "601-700"},
        {"up_to": None, "rate": 47.20, "label": "Above 700"},
    ],
}


def default_config() -> dict[str, Any]:
    """Return a deep copy of the default config so callers can safely mutate."""
    return deepcopy(DEFAULT_CONFIG)


def merge_config(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Layer user overrides on top of defaults. Top-level keys only — slab arrays
    are replaced wholesale if present (so the UI sends the full slab list when
    editing rates, not a partial patch)."""
    cfg = default_config()
    if not overrides:
        return cfg
    for k, v in overrides.items():
        if k in cfg:
            cfg[k] = v
    return cfg


def _telescopic_energy_charge(units: float, slabs: list[dict]) -> tuple[float, list[dict]]:
    """Walk slabs in order, billing each portion at its own rate. Returns
    (total, breakdown_lines)."""
    remaining = units
    prev_edge = 0
    total = 0.0
    lines: list[dict] = []
    for slab in slabs:
        edge = slab.get("up_to")
        if edge is None:
            block = remaining
        else:
            block = min(remaining, max(0, edge - prev_edge))
        if block <= 0:
            prev_edge = edge if edge is not None else prev_edge
            continue
        cost = block * slab["rate"]
        total += cost
        lines.append({
            "label": slab.get("label", f"slab to {edge}"),
            "units": round(block, 3),
            "rate": slab["rate"],
            "amount": round(cost, 2),
        })
        remaining -= block
        prev_edge = edge if edge is not None else prev_edge
        if remaining <= 0:
            break
    return total, lines


def _flat_energy_charge(units: float, slabs: list[dict]) -> tuple[float, list[dict]]:
    """Find the slab the total `units` falls in, charge every unit at that
    slab's rate. The Pakistani 'single-block' cliff."""
    if units <= 0:
        return 0.0, []
    chosen = slabs[-1]
    for slab in slabs:
        edge = slab.get("up_to")
        if edge is None or units <= edge:
            chosen = slab
            break
    cost = units * chosen["rate"]
    line = {
        "label": chosen.get("label", "slab"),
        "units": round(units, 3),
        "rate": chosen["rate"],
        "amount": round(cost, 2),
    }
    return cost, [line]


def compute_bill(units: float, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute a full LESCO bill for `units` kWh consumed in a billing month.

    Returns a dict with `total`, `energy_charge`, every line item, plus the
    slab the consumption landed in (used by the slab-threshold projector).
    """
    cfg = merge_config(config)
    units = max(0.0, float(units or 0))

    consumer_type = (cfg.get("consumer_type") or "unprotected").lower()
    if consumer_type == "protected":
        slabs = cfg["protected_slabs"]
        energy_charge, slab_lines = _telescopic_energy_charge(units, slabs)
        slab_mode = "telescopic"
    else:
        slabs = cfg["unprotected_slabs"]
        energy_charge, slab_lines = _flat_energy_charge(units, slabs)
        slab_mode = "flat"

    fpa = units * float(cfg.get("fpa_per_unit", 0) or 0)
    qta = units * float(cfg.get("qtr_adjustment_per_unit", 0) or 0)
    fc_surcharge = units * float(cfg.get("fc_surcharge_per_unit", 0) or 0)
    nj_surcharge = units * float(cfg.get("nj_surcharge_per_unit", 0) or 0)

    # GST and electricity duty are calculated on (energy + FPA + QTA + surcharges).
    pre_tax = energy_charge + fpa + qta + fc_surcharge + nj_surcharge
    gst = pre_tax * float(cfg.get("gst_percent", 0) or 0) / 100.0
    ed = pre_tax * float(cfg.get("electricity_duty_percent", 0) or 0) / 100.0
    extra_tax = pre_tax * float(cfg.get("extra_tax_percent", 0) or 0) / 100.0

    tv_fee = float(cfg.get("tv_fee_pkr", 0) or 0)

    subtotal = pre_tax + gst + ed + extra_tax + tv_fee

    # Apply minimum bill floor.
    sanctioned = float(cfg.get("sanctioned_load_kw", 0) or 0)
    min_bill = (
        cfg["min_bill_5kw_or_above"]
        if sanctioned >= 5
        else cfg["min_bill_below_5kw"]
    )
    total = max(subtotal, float(min_bill))
    min_bill_applied = total > subtotal

    # Identify which unprotected slab we're in and the next-slab cliff distance.
    slab_info = None
    if consumer_type == "unprotected":
        prev_edge = 0
        for slab in slabs:
            edge = slab.get("up_to")
            if edge is None or units <= edge:
                next_edge = edge
                slab_info = {
                    "current_label": slab.get("label"),
                    "current_rate": slab["rate"],
                    "lower_edge": prev_edge,
                    "upper_edge": next_edge,
                    "units_to_next_slab": (
                        max(0.0, next_edge - units) if next_edge is not None else None
                    ),
                }
                break
            prev_edge = edge

    return {
        "units": round(units, 3),
        "consumer_type": consumer_type,
        "slab_mode": slab_mode,
        "slab_info": slab_info,
        "energy_charge": round(energy_charge, 2),
        "energy_lines": slab_lines,
        "fpa": round(fpa, 2),
        "qta": round(qta, 2),
        "fc_surcharge": round(fc_surcharge, 2),
        "nj_surcharge": round(nj_surcharge, 2),
        "gst": round(gst, 2),
        "electricity_duty": round(ed, 2),
        "extra_tax": round(extra_tax, 2),
        "tv_fee": round(tv_fee, 2),
        "subtotal": round(subtotal, 2),
        "min_bill_floor": float(min_bill),
        "min_bill_applied": min_bill_applied,
        "total": round(total, 2),
        "effective_rate_per_unit": round(total / units, 3) if units > 0 else 0.0,
    }


def marginal_rate(units_already_used: float, config: dict[str, Any] | None = None) -> float:
    """The PKR/unit cost of the *next* unit consumed at the current consumption
    level. Used to value avoided grid usage. Includes FPA, FC, NJ, GST, ED.
    """
    cfg = merge_config(config)
    base_units = max(0.0, float(units_already_used or 0))
    a = compute_bill(base_units, cfg)
    b = compute_bill(base_units + 1.0, cfg)
    # Strip TV fee + min-bill floor from the delta — those are fixed/threshold,
    # not per-unit signals. Using subtotal-without-tv keeps the marginal clean.
    delta = (b["subtotal"] - b["tv_fee"]) - (a["subtotal"] - a["tv_fee"])
    return round(delta, 4)
