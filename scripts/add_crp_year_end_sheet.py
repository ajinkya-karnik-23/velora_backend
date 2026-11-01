"""Add a "Year End" sheet to the client's CRP workbook.

Usage:
    python -m scripts.add_crp_year_end_sheet [PATH]   # default: CRP_TEMPLATE_PATH

The template ships with Test of Design, Operating Effectiveness and
Rollforward sheets only. Year End is added as an exact copy of Rollforward —
same columns, reviewer checks, dropdowns, conditional formatting, numbered
blank rows and example row — titled "YEAR END", placed after Rollforward. The
workbook is edited at the XML level so nothing else changes (openpyxl would
drop the template's dropdown extensions). Running it again does nothing once
the sheet is there.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402

SOURCE_SHEET = "Rollforward"
NEW_SHEET = "Year End"
NEW_TITLE = "YEAR END"


def add_year_end(template: bytes) -> bytes | None:
    """The workbook with the Year End sheet, or None if it already has one."""
    with zipfile.ZipFile(io.BytesIO(template)) as z:
        names = z.namelist()
        files = {n: z.read(n) for n in names}
        infos = {n: z.getinfo(n) for n in names}

    workbook = files["xl/workbook.xml"].decode("utf-8")
    if f'name="{NEW_SHEET}"' in workbook:
        return None
    rels = files["xl/_rels/workbook.xml.rels"].decode("utf-8")

    source = re.search(rf'<sheet name="{SOURCE_SHEET}" sheetId="\d+" r:id="(rId\d+)"/>', workbook)
    if source is None:
        raise SystemExit(f"No {SOURCE_SHEET} sheet to copy.")
    target = re.search(rf'Id="{source.group(1)}"[^>]*Target="([^"]+)"', rels) or re.search(
        rf'Target="([^"]+)"[^>]*Id="{source.group(1)}"', rels
    )
    source_part = "xl/" + target.group(1)
    index = max(int(n) for n in re.findall(r"worksheets/sheet(\d+)\.xml", " ".join(names))) + 1
    new_part = f"xl/worksheets/sheet{index}.xml"
    new_rid = f"rId{max(int(n) for n in re.findall(r'Id=\"rId(\d+)\"', rels)) + 1}"
    new_sheet_id = max(int(n) for n in re.findall(r'sheetId="(\d+)"', workbook)) + 1

    # The sheet: Rollforward's XML, retitled, not the selected tab.
    sheet = files[source_part].decode("utf-8")
    sheet = sheet.replace(' tabSelected="1"', "", 1)
    title = re.search(r'<c r="B2"(\s[^>]*?)?(/>|>.*?</c>)', sheet, re.S)
    style = re.search(r'\ss="(\d+)"', title.group(0).split(">", 1)[0]) if title else None
    retitled = (
        f'<c r="B2"{f" s=\"{style.group(1)}\"" if style else ""} t="inlineStr">'
        f"<is><t>{NEW_TITLE}</t></is></c>"
    )
    sheet = sheet[: title.start()] + retitled + sheet[title.end():] if title else sheet
    files[new_part] = sheet.encode("utf-8")
    names.append(new_part)

    # Its own copy of the print settings, if Rollforward has any.
    source_rels = source_part.replace("worksheets/", "worksheets/_rels/") + ".rels"
    if source_rels in files:
        sheet_rels = files[source_rels].decode("utf-8")
        for printer in re.findall(r'Target="\.\./printerSettings/(printerSettings\d+\.bin)"', sheet_rels):
            number = max(
                int(n) for n in re.findall(r"printerSettings(\d+)\.bin", " ".join(names))
            ) + 1
            copy = f"printerSettings{number}.bin"
            files[f"xl/printerSettings/{copy}"] = files[f"xl/printerSettings/{printer}"]
            names.append(f"xl/printerSettings/{copy}")
            sheet_rels = sheet_rels.replace(printer, copy)
        new_rels = new_part.replace("worksheets/", "worksheets/_rels/") + ".rels"
        files[new_rels] = sheet_rels.encode("utf-8")
        names.append(new_rels)

    # Workbook: the sheet after Rollforward, and its filter range.
    workbook = workbook.replace(
        source.group(0),
        source.group(0) + f'<sheet name="{NEW_SHEET}" sheetId="{new_sheet_id}" r:id="{new_rid}"/>',
        1,
    )
    sheets = re.findall(r"<sheet [^>]*/>", workbook)
    position = len(sheets) - 1
    source_position = position - 1
    filter_name = re.search(
        rf'<definedName name="_xlnm._FilterDatabase" localSheetId="{source_position}"'
        rf' hidden="1">{SOURCE_SHEET}!([^<]+)</definedName>',
        workbook,
    )
    if filter_name:
        workbook = workbook.replace(
            "</definedNames>",
            f'<definedName name="_xlnm._FilterDatabase" localSheetId="{position}" hidden="1">'
            f"'{NEW_SHEET}'!{filter_name.group(1)}</definedName></definedNames>",
            1,
        )
    files["xl/workbook.xml"] = workbook.encode("utf-8")

    files["xl/_rels/workbook.xml.rels"] = rels.replace(
        "</Relationships>",
        f'<Relationship Id="{new_rid}" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        "</Relationships>",
        1,
    ).encode("utf-8")

    types = files["[Content_Types].xml"].decode("utf-8")
    files["[Content_Types].xml"] = types.replace(
        "</Types>",
        f'<Override PartName="/{new_part}" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        1,
    ).encode("utf-8")

    # Document properties: the sheet count and names.
    if "docProps/app.xml" in files:
        app = files["docProps/app.xml"].decode("utf-8")
        app = re.sub(
            r"(<vt:lpstr>Worksheets</vt:lpstr></vt:variant><vt:variant><vt:i4>)(\d+)",
            lambda m: f"{m.group(1)}{int(m.group(2)) + 1}",
            app,
            count=1,
        )
        app = re.sub(
            r'(<TitlesOfParts><vt:vector size=")(\d+)(" baseType="lpstr">)(.*?)(</vt:vector>)',
            lambda m: f"{m.group(1)}{int(m.group(2)) + 1}{m.group(3)}{m.group(4)}"
            f"<vt:lpstr>{NEW_SHEET}</vt:lpstr>{m.group(5)}",
            app,
            count=1,
            flags=re.S,
        )
        files["docProps/app.xml"] = app.encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            if n in infos:
                z.writestr(infos[n], files[n], compress_type=zipfile.ZIP_DEFLATED)
            else:
                z.writestr(n, files[n])
    return out.getvalue()


def main(path: Path) -> None:
    result = add_year_end(path.read_bytes())
    if result is None:
        print(f"{path.name} already has a {NEW_SHEET} sheet.")
        return
    path.write_bytes(result)
    print(f"Added the {NEW_SHEET} sheet to {path.name}.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(settings.CRP_TEMPLATE_PATH))
