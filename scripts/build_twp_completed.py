"""Build the completed TWP work paper for a control from its client data.

Takes the empty work-paper template and fills it from the control definition,
the sampling determination and the per-sample testing output — producing the
static workbook kept in the client data. The download builds the same work
paper per review cycle instead (see app/services/twp_builder.py), adding that
cycle's sample selection, document references and sign-off.

Re-run after editing any of the source JSONs:

    poetry run python -m scripts.build_twp_completed IA8.CA02 19A1
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.services.twp_builder import TwpBuildError, build_twp_workbook, completed_target


def build(control_number: str, entity_code: str) -> Path:
    try:
        wb = build_twp_workbook(control_number, entity_code)
    except TwpBuildError as exc:
        raise SystemExit(str(exc)) from exc
    target = completed_target(control_number, entity_code)
    target.parent.mkdir(parents=True, exist_ok=True)
    wb.save(target)
    return target


def main() -> None:
    control_number = sys.argv[1] if len(sys.argv) > 1 else "IA8.CA02"
    entity_code = sys.argv[2] if len(sys.argv) > 2 else "19A1"
    out = build(control_number, entity_code)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
