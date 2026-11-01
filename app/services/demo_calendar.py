"""The demo's testing calendar, applied to the dates a phased cycle shows.

The supporting documents date from January to July 2025, but the client
tests on its own calendar: DE in May, OE in September–October, RF in
December and YE the following January. `misc/phase_demo.json`'s `calendar`
maps a slice of the documents' period onto each of those windows, and every
date a sample shows is moved through it — its date fields, its month, and
the dates quoted in its validation text — so a sample reads as drawn from
its phase's window (see `phase_rules.EVIDENCE_WINDOWS`).

The mapping is monotonic, so samples keep their order and a sample drawn
under the documents' own dates is drawn the same under the shown ones. File
names are never changed, including ones quoted in the text, and a field's
original value is kept under `source_fields` for the evidence filename rule
(IA5.CA03.1's monthly reviews are filed as Apr-25.pdf). Without a calendar
the payload is returned as it is.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.core.config import settings

Segment = tuple[date, date, date, date]

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_MONTH_NO = (
    {m.lower(): i for i, m in enumerate(MONTHS, 1)}
    | {m.lower(): i for i, m in enumerate(MONTH_NAMES, 1)}
    | {"sept": 9}
)

# Keys never touched: the files a sample was tested on keep their real names.
UNSHIFTED_KEYS = {"evidences_used", "pages", "sample_no", "result", "source_fields"}
# Narrative keys whose quoted dates are moved.
TEXT_KEYS = {"validation", "summary", "conclusion", "failure_reason"}
# Keys holding a date as yyyymmdd (SAP's assignment field).
COMPACT_DATE_KEYS = {"Assignment"}

_FILE = re.compile(r"[^\s'\"(),;:]+\.(?:pdf|msg|png|jpe?g|xlsx?|xlsm|docx?|eml|csv)\b", re.I)
_MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
_TEXT_DATES = re.compile(
    rf"\b(?P<iso>(?P<iy>20\d\d)-(?P<im>\d\d)-(?P<id>\d\d))\b"
    rf"|\b(?P<dmy>(?P<dd>\d{{1,2}})[- ](?P<dm>{_MON})[- ,]+(?P<dy>20\d\d))\b"
    rf"|\b(?P<mdy>(?P<mm>{_MON}) (?P<md>\d{{1,2}}),? (?P<my>20\d\d))\b"
    rf"|\b(?P<num>(?P<nd>\d{{1,2}})(?P<sep>[./])(?P<nm>\d{{1,2}})(?P=sep)(?P<ny>20\d\d|\d\d))\b"
    rf"|\b(?P<my2>(?P<mo>{_MON})[ -](?P<yo>20\d\d))\b",
    re.I,
)


def _month(word: str) -> int:
    """A month's number from its full or three-letter name ("Marine" is not March)."""
    return _MONTH_NO[word.lower()]


_MONTH_VALUE = re.compile(rf"^(?P<m>{_MON})-(?P<y>\d\d)$", re.I)


def calendar() -> list[Segment]:
    """The (from_start, from_end, to_start, to_end) segments, in order."""
    path = Path(settings.PHASE_DEMO_PATH)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    segments: list[Segment] = []
    for entry in (payload.get("calendar") if isinstance(payload, dict) else None) or []:
        try:
            a, b = (date.fromisoformat(x) for x in entry["from"])
            c, d = (date.fromisoformat(x) for x in entry["to"])
        except (KeyError, TypeError, ValueError):
            continue
        segments.append((a, b, c, d))
    return sorted(segments)


def shift_date(day: date, segments: list[Segment]) -> date:
    """Where a documents' date falls on the testing calendar."""
    if not segments:
        return day
    for a, b, c, d in segments:
        if a <= day <= b:
            span = (b - a).days
            return c + timedelta(days=round((day - a).days * (d - c).days / span) if span else 0)
    # Outside every segment: move with the nearest one, keeping the distance.
    before = [s for s in segments if s[1] < day]
    if before:
        a, b, c, d = before[-1]
        return d + (day - b)
    a, b, c, d = segments[0]
    return c - (a - day)


def _month_end(year: int, month: int) -> date:
    return (date(year + month // 12, month % 12 + 1, 1)) - timedelta(days=1)


def _shift_month(year: int, month: int, segments: list[Segment]) -> date:
    # A month stands for its last day — a monthly review is done at month end.
    return shift_date(_month_end(year, month), segments)


def shift_text(text: str, segments: list[Segment]) -> str:
    """The text with every quoted date moved, in the format it was written in."""
    if not segments or not text:
        return text
    kept: list[str] = []

    def hide(m: re.Match[str]) -> str:
        kept.append(m.group(0))
        return f"\x00{len(kept) - 1}\x00"

    hidden = _FILE.sub(hide, text)

    def move(m: re.Match[str]) -> str:
        g = m.groupdict()
        try:
            if g["iso"]:
                return shift_date(date.fromisoformat(g["iso"]), segments).isoformat()
            if g["dmy"]:
                new = shift_date(date(int(g["dy"]), _month(g["dm"]), int(g["dd"])), segments)
                sep = "-" if "-" in g["dmy"] else " "
                name = MONTHS if sep == "-" else _names(g["dm"])
                return f"{new.day:02d}{sep}{_cased(name[new.month - 1], g['dm'])}{sep}{new.year}"
            if g["mdy"]:
                new = shift_date(date(int(g["my"]), _month(g["mm"]), int(g["md"])), segments)
                name = _names(g["mm"])
                comma = "," if "," in g["mdy"] else ""
                return f"{_cased(name[new.month - 1], g['mm'])} {new.day}{comma} {new.year}"
            if g["num"]:
                year = int(g["ny"]) if len(g["ny"]) == 4 else 2000 + int(g["ny"])
                new = shift_date(date(year, int(g["nm"]), int(g["nd"])), segments)
                y = str(new.year) if len(g["ny"]) == 4 else f"{new.year % 100:02d}"
                return f"{new.day:02d}{g['sep']}{new.month:02d}{g['sep']}{y}"
            if g["my2"]:
                new = _shift_month(int(g["yo"]), _month(g["mo"]), segments)
                sep = "-" if "-" in g["my2"] else " "
                name = MONTHS if sep == "-" else _names(g["mo"])
                return f"{_cased(name[new.month - 1], g['mo'])}{sep}{new.year}"
        except (ValueError, KeyError):
            pass
        return m.group(0)

    moved = _TEXT_DATES.sub(move, hidden)
    return re.sub("\x00(\\d+)\x00", lambda m: kept[int(m.group(1))], moved)


def _names(like: str) -> tuple[str, ...]:
    """Full month names unless the text abbreviates ("May" reads as full)."""
    return MONTH_NAMES if len(like) > 3 or like.lower() == "may" else MONTHS


def _cased(word: str, like: str) -> str:
    return word.upper() if like.isupper() else word


def _shift_value(key: str, value: Any, segments: list[Segment]) -> Any:
    """A whole-value date moved, or the value unchanged."""
    if not isinstance(value, str):
        if key in COMPACT_DATE_KEYS and isinstance(value, int):
            return int(_shift_value(key, str(value), segments))
        return value
    text = value.strip()
    if len(text) >= 10 and re.match(r"^20\d\d-\d\d-\d\d", text):
        try:
            return shift_date(date.fromisoformat(text[:10]), segments).isoformat() + text[10:]
        except ValueError:
            return value
    month = _MONTH_VALUE.match(text)
    if month:
        try:
            number = _month(month["m"])
        except KeyError:
            return value
        new = _shift_month(2000 + int(month["y"]), number, segments)
        return f"{MONTHS[new.month - 1]}-{new.year % 100:02d}"
    if key in COMPACT_DATE_KEYS and re.fullmatch(r"20\d{6}", text):
        try:
            day = date(int(text[:4]), int(text[4:6]), int(text[6:]))
        except ValueError:
            return value
        return shift_date(day, segments).strftime("%Y%m%d")
    return value


def shift_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """A testing output on the demo's testing calendar (a copy)."""
    segments = calendar()
    if not payload or not segments:
        return payload
    out = copy.deepcopy(payload)
    for sample in (out.get("test_details") or {}).values():
        if not isinstance(sample, dict):
            continue
        source: dict[str, Any] = {}
        for key, value in list(sample.items()):
            if key in UNSHIFTED_KEYS:
                continue
            if key in TEXT_KEYS and isinstance(value, str):
                sample[key] = shift_text(value, segments)
                continue
            moved = _shift_value(key, value, segments)
            if moved != value:
                source[key] = value
                sample[key] = moved
        if source:
            sample["source_fields"] = source
    header = out.get("control_test_output")
    if isinstance(header, dict):
        for key in TEXT_KEYS & header.keys():
            if isinstance(header[key], str):
                header[key] = shift_text(header[key], segments)
    return out
