"""Sample selection for cycles sampled by the client's sampling matrix.

A matrix-sampled cycle tests only as many samples as the matrix calls for,
drawn from the control's testing output. Three steps:

1. Size — the Operating Effectiveness table (frequency x risk/round), then the
   sub-sampling table for frequencies it has no row for. A range such as
   "2 to 5" takes its upper bound. There is deliberately no fallback to the
   control's own stated size: a control the matrix cannot size is reported as
   not tested, with the reason.
2. Split — the size is shared across the control's sample types in proportion
   to how many of each the population holds (largest-remainder rounding).
3. Pick — within each type, samples are spread evenly across the population
   in its own order, so the selection is deterministic and covers the period
   rather than bunching at the start.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.sampling_matrix import (
    _find_row,
    _frequency_band_map,
    _operating_effectiveness_table,
    _sub_sampling_table,
    calculate_sample_size,
    resolve_column,
    sub_sampling_size,
)

_NUMBERS = re.compile(r"\d+")


def size_from_matrix_value(raw: str | None) -> int | None:
    """The sample count a matrix cell calls for. Ranges take the upper bound."""
    if raw is None:
        return None
    numbers = [int(n) for n in _NUMBERS.findall(str(raw))]
    return max(numbers) if numbers else None


def matrix_size(matrix: dict[str, Any], params: dict[str, Any]) -> tuple[str | None, str | None]:
    """(matrix cell as written, source) — source is "matrix" or "sub_sampling".

    Both are None when neither table has a value for the control.
    """
    value = calculate_sample_size(
        matrix,
        risk_level=params.get("risk_level"),
        frequency=params.get("frequency"),
        phase=params.get("phase"),
    )
    if value is not None:
        return value, "matrix"
    value = sub_sampling_size(
        matrix, risk_level=params.get("risk_level"), frequency=params.get("frequency")
    )
    if value is not None:
        return value, "sub_sampling"
    return None, None


OE_TABLE = "Operating Effectiveness Testing"
SUB_TABLE = "Sub-sampling according to population range"


def explain_lookup(matrix: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Which cells of the matrix the sizing read, for the derivation log.

    Mirrors `matrix_size`: the Operating Effectiveness table first (frequency
    row, phase or risk column), then — when that has no value — the
    sub-sampling table through the frequency's declared population band.
    """
    frequency = params.get("frequency")
    risk = params.get("risk_level")
    out: dict[str, Any] = {
        "oe_row": None,
        "oe_column": None,
        "oe_value": None,
        "band": None,
        "sub_row": None,
        "sub_column": None,
        "sub_value": None,
    }
    table = _operating_effectiveness_table(matrix)
    row = _find_row(table, frequency or "") if table else None
    column = resolve_column(risk, params.get("phase"))
    if row is not None:
        out["oe_row"] = next(k for k, v in table.items() if v is row)
        out["oe_column"] = column
        value = row.get(column) if column else None
        out["oe_value"] = None if value in (None, "") else str(value)

    target = (frequency or "").strip().lower()
    for key, band in _frequency_band_map(matrix).items():
        if not key.startswith("_") and key.strip().lower() == target:
            out["band"] = str(band)
            break
    if out["band"]:
        sub = _sub_sampling_table(matrix)
        for key, value in sub.items():
            if key.strip().lower() == out["band"].strip().lower() and isinstance(value, dict):
                out["sub_row"] = key
                out["sub_column"] = (
                    "High" if (risk or "").strip().lower() == "high" else "Low/ Medium"
                )
                cell = value.get(out["sub_column"])
                out["sub_value"] = None if cell in (None, "") else str(cell)
    return out


def no_matrix_value_reason(params: dict[str, Any]) -> str:
    frequency = params.get("frequency") or "unknown"
    risk = params.get("risk_level") or "unknown"
    return (
        f"The sampling matrix has no sample size for a {frequency} control "
        f"at {risk} risk, so no sample could be selected."
    )


NO_POPULATION_REASON = "No population was provided for this control, so there was nothing to test."


def untested_type_lines(selection: dict[str, Any], required: int) -> list[dict[str, Any]]:
    """Sample types the selection left without a sample, each with its reason.

    A proportional split can round a small type down to nothing; that type is
    reported as not tested rather than topped up, so the matrix count holds.
    """
    total = sum(t["available"] for t in selection["types"])
    return [
        {
            "label": t["label"],
            "available": t["available"],
            "reason": (
                f"Not tested: the sampling matrix calls for {required} sample(s) for this "
                f"control, shared across its sample types in proportion to the population. "
                f"{t['label']} make up {t['available']} of {total} items, so no sample of "
                "this type was selected."
            ),
        }
        for t in selection["types"]
        if t["available"] and not t["selected"]
    ]


def _field_names(sample: dict[str, Any]) -> set[str]:
    names = {k for k, v in sample.items() if k != "parameters" and v not in (None, "")}
    for param in sample.get("parameters") or []:
        if isinstance(param, dict) and param.get("label") and param.get("value") not in (None, ""):
            names.add(str(param["label"]))
    return names


def _param(sample: dict[str, Any], label: str) -> Any:
    for param in sample.get("parameters") or []:
        if isinstance(param, dict) and param.get("label") == label:
            return param.get("value")
    return sample.get(label)


def sample_types(samples: list[dict[str, Any]], header: dict[str, Any] | None) -> list[str]:
    """The type label of each sample, in order.

    Uses the same declaration as the methodology breakdown: a sample belongs to
    the first declared type whose field it carries. Without a declaration the
    journal-entry split applies (Type "NR" vs everything else).
    """
    declared = (header or {}).get("methodology")
    if isinstance(declared, dict) and declared.get("breakdown"):
        lines = [
            line for line in declared["breakdown"] if line.get("label") and line.get("when_field")
        ]
        types = []
        for sample in samples:
            fields = _field_names(sample)
            match = next((line["label"] for line in lines if line["when_field"] in fields), None)
            types.append(str(match or "Other"))
        return types

    return [
        (
            "NR Entries"
            if str(_param(sample, "Type") or "").strip().upper() == "NR"
            else "Manual Journal Entries"
        )
        for sample in samples
    ]


def proportional_quotas(counts: dict[str, int], size: int) -> dict[str, int]:
    """Share `size` across types in proportion to their counts.

    Largest-remainder rounding keeps the total exact; ties go to the larger
    type, then the earlier one.
    """
    total = sum(counts.values())
    if total == 0 or size <= 0:
        return dict.fromkeys(counts, 0)
    size = min(size, total)
    exact = {label: size * n / total for label, n in counts.items()}
    quotas = {label: int(value) for label, value in exact.items()}
    order = list(counts)
    leftover = size - sum(quotas.values())
    ranked = sorted(
        order,
        key=lambda label: (-(exact[label] - quotas[label]), -counts[label], order.index(label)),
    )
    for label in ranked[:leftover]:
        quotas[label] += 1
    return quotas


def spread(items: list[Any], k: int) -> list[Any]:
    """k items spread evenly across the list (midpoints of k equal strata)."""
    n = len(items)
    if k >= n:
        return list(items)
    if k <= 0:
        return []
    return [items[int((i + 0.5) * n / k)] for i in range(k)]


def sample_no_of(sample: dict[str, Any], index: int) -> int:
    raw = sample.get("sample_no")
    return raw if isinstance(raw, int) else index + 1


def select_samples(
    samples: list[dict[str, Any]], header: dict[str, Any] | None, size: int
) -> dict[str, Any]:
    """Choose which samples to test and report how the choice was made.

    Returns {"selected": [sample_no, ...], "types": [{label, available,
    selected}], "shortfall": int} — shortfall is how many more samples the
    matrix asked for than the population holds.
    """
    labels = sample_types(samples, header)
    groups: dict[str, list[int]] = {}
    for i, (sample, label) in enumerate(zip(samples, labels, strict=True)):
        groups.setdefault(label, []).append(sample_no_of(sample, i))

    quotas = proportional_quotas({label: len(nos) for label, nos in groups.items()}, size)
    chosen: set[int] = set()
    types = []
    for label, nos in groups.items():
        picked = spread(nos, quotas[label])
        chosen.update(picked)
        types.append({"label": label, "available": len(nos), "selected": len(picked)})

    ordered = [sample_no_of(s, i) for i, s in enumerate(samples)]
    return {
        "selected": [no for no in ordered if no in chosen],
        "types": types,
        "shortfall": max(0, size - len(samples)),
    }
