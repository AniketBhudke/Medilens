"""Compare lab values with standard adult reference ranges."""
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
_RANGES = json.loads((DATA / "lab_ranges.json").read_text(encoding="utf-8"))

_ALIAS = {}
for key, spec in _RANGES.items():
    _ALIAS[key] = key
    for a in spec["aliases"]:
        _ALIAS[a.lower()] = key


def _canon(test: str) -> str | None:
    t = re.sub(r"\s+", " ", (test or "").lower().strip())
    if t in _ALIAS:
        return _ALIAS[t]
    t2 = re.sub(r"\(.*?\)", "", t).strip()
    if t2 in _ALIAS:
        return _ALIAS[t2]
    return None


def evaluate(results: list[dict], sex: str | None = None) -> list[dict]:
    """Add flag (low/high/normal/unknown), reference range and plain note to each result."""
    out = []
    for r in results:
        item = dict(r)
        key = _canon(r.get("test", ""))
        try:
            val = float(r.get("value"))
        except (TypeError, ValueError):
            item.update(flag="unknown", reference=None)
            out.append(item)
            continue
        if key is None:
            item.update(flag="unknown", reference=r.get("reference_range_text"))
            out.append(item)
            continue
        spec = _RANGES[key]
        lo, hi = spec.get(sex or "", spec["general"]) if sex in ("male", "female") else spec["general"]
        flag, note = "normal", ""
        if val < lo:
            flag, note = "low", spec.get("low", "")
        elif val > hi:
            flag, note = "high", spec.get("high", "")
        # how far outside range, to tell mild from marked
        span = max(hi - lo, 1e-9) if hi < 1e9 else lo
        gap = (lo - val) if val < lo else (val - hi if val > hi else 0)
        severity = "none" if flag == "normal" else ("marked" if gap / max(span, 1e-9) > 0.25 else "mild")
        item.update(test_standard=key, flag=flag, severity=severity, reference=f"{lo:g} – {hi:g} {spec['unit']}", default_note=note)
        out.append(item)
    return out
