"""
Guardrails for automated data updates (run by scripts/auto_update.sh).

Compares the freshly built docs/data/site_data*.json against the last
published version (git HEAD) and exits with:
    0  OK to publish (warnings, if any, are printed)
    1  Do NOT publish — the pipeline looks broken
    2  NSF new-awards cumulative dropped for an open FY. The NSF Awards API can
       retroactively drop awards, but a truncated fetch looks the same. The
       caller should delete the open-FY NSF caches, re-fetch, rebuild, and
       re-run with --accept-nsf-drop: a drop that reproduces is real.

Usage:
    python3 scripts/validate_update.py [--accept-nsf-drop]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import CURRENT_FY, is_fy_frozen  # noqa: E402

PARENTS = ["NIH", "NSF", "DOE_SC", "NASA_SCI", "USDA_RD"]
AWARD_SECTIONS = ["awards", "awards_all"]
FROZEN_TOLERANCE = 0.01      # completed FYs should not move at all
DROP_WARN = 0.03             # open-FY cumulative decline worth flagging
JUMP_WARN = 0.25             # open-FY cumulative jump worth flagging (backfill)
NSF_PCT_RANGE = (48, 65)     # CLAUDE.md: completed-FY NSF new awards = 55-60% of approp
MIN_SIZE_RATIO = 0.6

errors, warnings, nsf_drops = [], [], []


def load_new(name):
    return json.loads((ROOT / "docs" / "data" / name).read_text())


def load_published(name):
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD:docs/data/{name}"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout
        return json.loads(out), len(out.encode())
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None, 0


def merged(core, detail):
    """Combine core (parent agencies) and detail (sub-agencies) sections."""
    out = {}
    for section in set(core) | set(detail):
        a, b = core.get(section), detail.get(section)
        if isinstance(a, dict) and isinstance(b, dict):
            out[section] = {**a, **b}
        else:
            out[section] = a if a is not None else b
    return out


def last_value(values):
    vals = [v for v in values if v is not None]
    return vals[-1] if vals else None


def value_at_day(trace, day, key):
    """Cumulative value at the last point on or before fy_day `day`."""
    best = None
    for d, v in zip(trace["fy_days"], trace[key]):
        if d <= day and v is not None:
            best = v
    return best


def rel_change(old, new):
    if old in (None, 0) or new is None:
        return None
    return (new - old) / abs(old)


def check_structure(new):
    cfg = new.get("config", {})
    for key in ("current_fy", "awards_current_fy", "latest_period_label"):
        if not cfg.get(key):
            errors.append(f"config.{key} missing")
    for section in ["spenddown", "summaries"] + AWARD_SECTIONS:
        missing = [a for a in PARENTS if a not in new.get(section, {})]
        if missing:
            errors.append(f"{section}: missing agencies {missing}")
    for agency, summ in new.get("summaries", {}).items():
        if agency in PARENTS and "error" in summ:
            errors.append(f"summaries.{agency}: {summ['error']}")


def check_frozen_and_open(new, old):
    for section in AWARD_SECTIONS:
        for agency, adata in new.get(section, {}).items():
            old_agency = old.get(section, {}).get(agency)
            if not old_agency:
                continue
            for fy_str, trace in adata["years"].items():
                old_trace = old_agency["years"].get(fy_str)
                if not old_trace:
                    continue
                fy = int(fy_str)
                if is_fy_frozen(fy):
                    ch = rel_change(last_value(old_trace["cumulative_dollars_m"]),
                                    last_value(trace["cumulative_dollars_m"]))
                    if ch is not None and abs(ch) > FROZEN_TOLERANCE:
                        errors.append(f"{section}.{agency} FY{fy} (completed) changed {ch:+.1%}")
                elif agency in PARENTS:
                    # Open FY: compare at the last day the published version
                    # covered — or, for monthly USASpending series, its last
                    # complete month (the provisional partial month is re-placed
                    # each build, so comparing it would flag false drops)
                    prov = old_trace.get("provisional_index")
                    old_day = old_trace["fy_days"][prov - 1 if prov else -1]
                    ch = rel_change(value_at_day(old_trace, old_day, "cumulative_dollars_m"),
                                    value_at_day(trace, old_day, "cumulative_dollars_m"))
                    if ch is None:
                        continue
                    label = f"{section}.{agency} FY{fy} at fy_day {old_day}"
                    if ch < -DROP_WARN:
                        if section == "awards" and agency == "NSF":
                            nsf_drops.append(f"{label}: {ch:+.1%}")
                        else:
                            warnings.append(f"{label} dropped {ch:+.1%} vs published")
                    elif ch > JUMP_WARN:
                        warnings.append(f"{label} rose {ch:+.1%} vs published (likely backfill)")

    for agency, adata in new.get("spenddown", {}).items():
        old_agency = old.get("spenddown", {}).get(agency)
        if not old_agency:
            continue
        for fy_str, trace in adata["years"].items():
            old_trace = old_agency["years"].get(fy_str)
            if old_trace and is_fy_frozen(int(fy_str)):
                ch = rel_change(last_value(old_trace["dollars_b"]), last_value(trace["dollars_b"]))
                if ch is not None and abs(ch) > FROZEN_TOLERANCE:
                    errors.append(f"spenddown.{agency} FY{fy_str} (completed) changed {ch:+.1%}")


def check_nsf_pct(new):
    nsf = new.get("awards", {}).get("NSF", {})
    for fy_str, trace in nsf.get("years", {}).items():
        if not is_fy_frozen(int(fy_str)):
            continue
        pct = last_value(trace.get("pct_of_approp", []))
        if pct is not None and not (NSF_PCT_RANGE[0] <= pct <= NSF_PCT_RANGE[1]):
            errors.append(
                f"awards.NSF FY{fy_str} ends at {pct:.1f}% of appropriation "
                f"(expected {NSF_PCT_RANGE[0]}-{NSF_PCT_RANGE[1]}%) — wrong NSF dollar field?"
            )


def check_obligations_period(new, old):
    labels = new["config"].get("fy_month_labels", {})
    order = {v.split("(")[0].strip(): int(k) for k, v in labels.items()}

    def key(cfg):
        label = (cfg.get("latest_period_label") or "").split("(")[0].strip()
        return (cfg.get("current_fy") or 0, order.get(label, 0))

    if key(new["config"]) < key(old.get("config", {})):
        errors.append(f"obligations period went backwards: {key(old['config'])} -> {key(new['config'])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--accept-nsf-drop", action="store_true")
    args = parser.parse_args()

    try:
        new_core, new_detail = load_new("site_data.json"), load_new("site_data_detail.json")
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read new site data: {e}")
        return 1
    new = merged(new_core, new_detail)
    check_structure(new)
    check_nsf_pct(new)

    old_core, old_core_size = load_published("site_data.json")
    old_detail, old_detail_size = load_published("site_data_detail.json")
    if old_core is None or old_detail is None:
        warnings.append("no published site data in git HEAD — skipped comparisons")
    else:
        old = merged(old_core, old_detail)
        for name, old_size in (("site_data.json", old_core_size),
                               ("site_data_detail.json", old_detail_size)):
            new_size = (ROOT / "docs" / "data" / name).stat().st_size
            if old_size and new_size < MIN_SIZE_RATIO * old_size:
                errors.append(f"{name} shrank from {old_size // 1024} KB to {new_size // 1024} KB")
        check_frozen_and_open(new, old)
        check_obligations_period(new, old)

    cfg = new.get("config", {})
    print(f"Validation — awards FY{cfg.get('awards_current_fy')}, "
          f"obligations FY{cfg.get('current_fy')} through {cfg.get('latest_period_label')}")
    for w in warnings:
        print(f"  WARN: {w}")
    for d in nsf_drops:
        print(f"  {'WARN' if args.accept_nsf_drop else 'NSF DROP'}: {d}")
    for e in errors:
        print(f"  ERROR: {e}")

    if errors:
        return 1
    if nsf_drops and not args.accept_nsf_drop:
        return 2
    print("  OK to publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
