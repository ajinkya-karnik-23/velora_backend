"""Test report generation using docxtpl.

Can be imported as a module (generate_test_report) or run standalone
for a quick smoke-test with example data.
"""

from __future__ import annotations

import io
from pathlib import Path

from docxtpl import DocxTemplate

TEMPLATE_PATH = Path(__file__).parent / "report_template.docx"


def generate_test_report(
    control_number: str,
    test_id: int | str,
    test_description: str,
    result_string: str,
    evidence_list: list[dict] | None = None,
    tested_by: str = "—",
) -> bytes:
    """Render the report template and return the filled docx as raw bytes."""
    doc = DocxTemplate(TEMPLATE_PATH)

    context = {
        "control_number": str(control_number),
        "test_id": str(test_id),
        "test_description": str(test_description) if test_description else "—",
        "result_string": str(result_string) if result_string else "—",
        "evidence_list": evidence_list or [],
        "tested_by": tested_by,
    }

    doc.render(context)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Standalone smoke-test — run directly to verify the template renders
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample = generate_test_report(
        control_number="CTRL-2026-99421",
        test_id="TST-AAB-880",
        test_description=(
            "Automated validation sequence to verify structural integrity and "
            "response times of the database cluster under maximum simulated peak "
            "stress levels."
        ),
        result_string=(
            "PASSED — All core components responded within the expected 150 ms "
            "timeframe with zero critical anomalies detected."
        ),
    )

    out_path = Path(__file__).parent / "final_rendered_report.docx"
    out_path.write_bytes(sample)
    print(f"✅ Report written to {out_path}  ({len(sample):,} bytes)")
