from __future__ import annotations

from datetime import date

from app.services.demo_calendar import shift_date, shift_payload, shift_text

SEGMENTS = [
    (date(2025, 1, 1), date(2025, 1, 31), date(2026, 5, 1), date(2026, 5, 31)),
    (date(2025, 2, 1), date(2025, 5, 31), date(2026, 9, 1), date(2026, 10, 31)),
    (date(2025, 6, 1), date(2025, 7, 15), date(2026, 12, 1), date(2026, 12, 31)),
    (date(2025, 7, 16), date(2025, 7, 31), date(2027, 1, 1), date(2027, 1, 31)),
]


def test_each_slice_lands_in_its_phase_window():
    assert shift_date(date(2025, 1, 7), SEGMENTS) == date(2026, 5, 7)
    assert date(2026, 9, 1) <= shift_date(date(2025, 3, 17), SEGMENTS) <= date(2026, 10, 31)
    assert shift_date(date(2025, 6, 1), SEGMENTS) == date(2026, 12, 1)
    assert shift_date(date(2025, 7, 31), SEGMENTS) == date(2027, 1, 31)


def test_dates_outside_every_slice_move_with_the_nearest():
    assert shift_date(date(2024, 12, 6), SEGMENTS) == date(2026, 4, 5)
    assert shift_date(date(2025, 8, 20), SEGMENTS) == date(2027, 2, 20)


def test_text_dates_move_in_their_own_format_and_file_names_stay():
    text = (
        "Posted 07-Jan-2025, approved 2025-01-07 (07.01.25), review for April 2025 and "
        "MAY 2025; see AMKR 03.07.25.pdf and Apr-25.pdf. Marine 2025 cover."
    )
    assert shift_text(text, SEGMENTS) == (
        "Posted 07-May-2026, approved 2026-05-07 (07.05.26), review for October 2026 and "
        "OCTOBER 2026; see AMKR 03.07.25.pdf and Apr-25.pdf. Marine 2025 cover."
    )


def test_payload_keeps_original_values_for_the_filename_rule(monkeypatch):
    monkeypatch.setattr("app.services.demo_calendar.calendar", lambda: SEGMENTS)
    payload = {
        "test_details": {
            "11": {
                "sample_no": 11,
                "Month": "Apr-25",
                "Date of review": "2025-04-30",
                "evidences_used": ["Apr-25.pdf"],
                "validation": "Reviewed for April 2025.",
            }
        }
    }
    sample = shift_payload(payload)["test_details"]["11"]
    assert sample["Month"] == "Oct-26" and sample["Date of review"] == "2026-10-15"
    assert sample["source_fields"] == {"Month": "Apr-25", "Date of review": "2025-04-30"}
    assert sample["evidences_used"] == ["Apr-25.pdf"]
    assert sample["validation"] == "Reviewed for October 2026."
    assert payload["test_details"]["11"]["Month"] == "Apr-25"
