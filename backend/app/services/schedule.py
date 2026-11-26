"""Turn prescription frequency text (1-0-1, BD, TDS, HS, SOS ...) into dose times."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SLOT_ORDER3 = ["morning", "afternoon", "night"]
SLOT_ORDER4 = ["morning", "afternoon", "evening", "night"]

ABBREV = {
    "OD": [1, 0, 0], "QD": [1, 0, 0], "QAM": [1, 0, 0],
    "BD": [1, 0, 1], "BID": [1, 0, 1], "BDS": [1, 0, 1],
    "TDS": [1, 1, 1], "TID": [1, 1, 1],
    "HS": [0, 0, 1], "QHS": [0, 0, 1], "NOCTE": [0, 0, 1],
}
QID = {"QID", "QDS"}
AS_NEEDED = {"SOS", "PRN", "STAT"}


def parse_frequency(raw: str | None) -> dict:
    """Return {"slots": {slot: qty}, "as_needed": bool}. Empty slots + as_needed False means 'could not parse'."""
    text = (raw or "").strip().upper().replace("–", "-").replace("—", "-")
    if not text:
        return {"slots": {}, "as_needed": False}
    tokens = set(re.findall(r"[A-Z]+", text))
    if tokens & AS_NEEDED:
        return {"slots": {}, "as_needed": True}

    m = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?", text)
    if m:
        vals = [float(g) for g in m.groups() if g is not None]
        order = SLOT_ORDER4 if len(vals) == 4 else SLOT_ORDER3
        return {"slots": {s: v for s, v in zip(order, vals) if v > 0}, "as_needed": False}

    if tokens & QID:
        return {"slots": {s: 1 for s in SLOT_ORDER4}, "as_needed": False}
    for tok in tokens:
        if tok in ABBREV:
            return {"slots": {s: v for s, v in zip(SLOT_ORDER3, ABBREV[tok]) if v > 0}, "as_needed": False}
    return {"slots": {}, "as_needed": False}


def slots_from_dict(d: dict | None) -> dict:
    out = {}
    for k, v in (d or {}).items():
        try:
            if k in SLOT_ORDER4 and float(v) > 0:
                out[k] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def parse_duration_days(raw) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw) if raw > 0 else None
    m = re.search(r"(\d+)\s*(day|days|d|week|weeks|wk|wks|month|months)?", str(raw).lower())
    if not m:
        return None
    n = int(m.group(1))
    unit = (m.group(2) or "d")
    if unit.startswith("w"):
        n *= 7
    elif unit.startswith("m"):
        n *= 30
    return n


def local_to_utc(day, hhmm: str, tz: str) -> datetime:
    h, m = [int(x) for x in hhmm.split(":")]
    local = datetime(day.year, day.month, day.day, h, m, tzinfo=ZoneInfo(tz))
    return local.astimezone(timezone.utc)


def build_dose_times(slots: dict, days: int, start_day, times: dict, tz: str, now: datetime):
    """Yield (slot, qty, utc_datetime) for upcoming doses. Skips doses already >5 min in the past."""
    cutoff = now - timedelta(minutes=5)
    for i in range(days):
        day = start_day + timedelta(days=i)
        for slot, qty in slots.items():
            when = local_to_utc(day, times[slot], tz)
            if when >= cutoff:
                yield slot, qty, when


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
