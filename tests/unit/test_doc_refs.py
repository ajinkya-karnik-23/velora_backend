"""Supporting-document reference numbers."""

from __future__ import annotations

from app.services.doc_refs import next_ref, ref_prefix


def test_prefix_names_control_and_sample_or_step():
    assert ref_prefix("IA5.CA01", 3, None) == "IA5.CA01-S03"
    assert ref_prefix("IA5.CA01", None, 12) == "IA5.CA01-T12"
    assert ref_prefix("IA5.CA01", None, None) == "IA5.CA01"
    assert ref_prefix(None, 1, None) == "DOC-S01"


def test_numbering_continues_and_is_never_reused():
    assert next_ref("IA5.CA01-S03", []) == "IA5.CA01-S03-D01"
    # D02 was deleted; the next document still continues past the highest issued.
    assert next_ref("IA5.CA01-S03", ["IA5.CA01-S03-D01", "IA5.CA01-S03-D03"]) == "IA5.CA01-S03-D04"
    # Other samples' references do not count.
    assert next_ref("IA5.CA01-S03", ["IA5.CA01-S31-D05", "IA5.CA01-S03-D01"]) == "IA5.CA01-S03-D02"
