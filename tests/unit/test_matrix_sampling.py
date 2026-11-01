"""Sample selection for matrix-sampled review cycles."""

from __future__ import annotations

from app.services.matrix_sampling import (
    matrix_size,
    proportional_quotas,
    sample_types,
    select_samples,
    size_from_matrix_value,
    spread,
)

MATRIX = {
    "Sampling Methodology": {
        "Operating Effectiveness Testing": {
            "Monthly": {
                "Risk Rating conclusion Low": None,
                "Risk Rating Conclusion Medium": "2 to 5",
            },
        },
        "Sub-sampling according to population range applicable for all rounds": {
            "Less than 20 items": {"Low/ Medium": 2, "High": 5},
        },
        "Frequency to sub-sampling population band": {"Upon Occurrence": "Less than 20 items"},
    }
}


def test_range_takes_upper_bound():
    assert size_from_matrix_value("2 to 5") == 5
    assert size_from_matrix_value("27") == 27
    assert size_from_matrix_value(None) is None


def test_matrix_size_sources():
    assert matrix_size(MATRIX, {"frequency": "Monthly", "risk_level": "Medium"}) == (
        "2 to 5",
        "matrix",
    )
    assert matrix_size(MATRIX, {"frequency": "Upon Occurrence", "risk_level": "Low"}) == (
        "2",
        "sub_sampling",
    )


def test_matrix_gap_has_no_size():
    # Monthly + Low is blank and Monthly has no population band.
    assert matrix_size(MATRIX, {"frequency": "Monthly", "risk_level": "Low"}) == (None, None)


def test_proportional_quotas_keep_exact_total():
    assert proportional_quotas({"a": 10, "b": 2}, 5) == {"a": 4, "b": 1}
    assert proportional_quotas({"a": 25, "b": 2}, 2) == {"a": 2, "b": 0}
    assert sum(proportional_quotas({"a": 3, "b": 3, "c": 3}, 7).values()) == 7


def test_quotas_never_exceed_population():
    assert proportional_quotas({"a": 2, "b": 1}, 10) == {"a": 2, "b": 1}


def test_spread_covers_the_population():
    assert spread(list(range(1, 21)), 2) == [6, 16]
    assert spread([1, 2, 3], 5) == [1, 2, 3]


def _sample(no, **fields):
    return {
        "sample_no": no,
        "parameters": [{"label": k, "value": v} for k, v in fields.items()],
    }


def test_types_follow_declared_breakdown():
    header = {
        "methodology": {
            "breakdown": [
                {"label": "Amendments", "when_field": "Customer name"},
                {"label": "Reviews", "when_field": "Month"},
            ]
        }
    }
    samples = [_sample(1, **{"Customer name": "A"}), _sample(2, Month="Jan")]
    assert sample_types(samples, header) == ["Amendments", "Reviews"]


def test_types_default_to_journal_entry_split():
    samples = [_sample(1, Type="KR"), _sample(2, Type="NR")]
    assert sample_types(samples, None) == ["Manual Journal Entries", "NR Entries"]


def test_select_samples_splits_by_type_and_reports_shortfall():
    samples = [_sample(i, Type="NR" if i > 8 else "KR") for i in range(1, 11)]
    result = select_samples(samples, None, 5)
    assert len(result["selected"]) == 5
    assert {t["label"]: t["selected"] for t in result["types"]} == {
        "Manual Journal Entries": 4,
        "NR Entries": 1,
    }
    assert result["shortfall"] == 0

    assert select_samples(samples, None, 12)["shortfall"] == 2
