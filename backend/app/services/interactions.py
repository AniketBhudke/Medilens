"""Rule-based drug-interaction and duplicate-ingredient checks (reference data in /data)."""
import json
import re
from itertools import combinations
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
_INTERACTIONS = json.loads((DATA / "interactions.json").read_text(encoding="utf-8"))
_BRANDS = json.loads((DATA / "brand_salts.json").read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9+ \-]", "", (s or "").lower()).strip()


def ingredients_for(med: dict) -> set[str]:
    """Active ingredients for a medicine: use the AI-read ingredient, else the brand lookup."""
    raw = med.get("active_ingredient") or ""
    if not raw.strip():
        name = _norm(med.get("name", ""))
        first = re.split(r"[ \-]\d", name)[0].strip()
        raw = _BRANDS.get(first) or _BRANDS.get(first.split(" ")[0], "") or name
    parts = re.split(r"\+|,|/| and ", _norm(raw))
    return {p.strip() for p in parts if p.strip()}


def check_interactions(meds: list[dict]) -> list[dict]:
    out = []
    ing = [(m.get("name", "?"), ingredients_for(m)) for m in meds]
    for (n1, i1), (n2, i2) in combinations(ing, 2):
        for rule in _INTERACTIONS:
            a, b = rule["a"], rule["b"]
            hit = (any(a in x for x in i1) and any(b in x for x in i2)) or (any(b in x for x in i1) and any(a in x for x in i2))
            if hit:
                out.append({"type": "interaction", "severity": rule["severity"], "medicines": [n1, n2], "message": rule["message"]})
    return out


def find_duplicates(meds: list[dict]) -> list[dict]:
    out, seen = [], {}
    for m in meds:
        for ing in ingredients_for(m):
            seen.setdefault(ing, []).append(m.get("name", "?"))
    for ing, names in seen.items():
        uniq = list(dict.fromkeys(names))
        if len(uniq) > 1:
            out.append({
                "type": "duplicate", "severity": "high", "medicines": uniq,
                "message": f"{' and '.join(uniq)} both contain {ing}. Taking both may double your dose. Ask your doctor or pharmacist.",
            })
    return out


def all_warnings(meds: list[dict]) -> list[dict]:
    return find_duplicates(meds) + check_interactions(meds)
