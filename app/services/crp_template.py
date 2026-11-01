"""Fill the client's Concurrent Review Process (CRP) workbook.

The template (CRP_TEMPLATE_PATH) has an introductory page, a hidden list of
dropdown values, and one sheet per phase — Test of Design (DE), Operating
Effectiveness (OE), Rollforward (RF) and Year End (YE) — each a row per control with the
tester's tracker columns and the reviewer's checks.

The workbook is edited at the XML level, cell by cell: openpyxl would drop the
template's dropdowns and conditional formatting (Excel extensions it does not
support) when saving, and the structure must stay exactly as the client gave
it. A filled cell keeps its style; only its value changes, written with the
exact text of the template's dropdown options.

Only columns the platform has evidence for are filled. Optro (status match,
issue opened) and the TeamMate+ upload are outside the platform and are left
on the template's "Please select…" placeholders.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

# The phase each sheet records. Year End was added to the client's template
# as a copy of Rollforward (scripts/add_crp_year_end_sheet.py).
PHASE_SHEETS = {
    "DE": "Test of Design",
    "OE": "Operating Effectiveness",
    "RF": "Rollforward",
    "YE": "Year End",
}

# Dropdown values, exactly as the template's hidden list spells them
# (several carry a trailing space).
DOCS_COMPLETE = "Complete for testing "
DOCS_INCOMPLETE = "Incomplete"
DOCS_NOT_PROVIDED = "Not provided "
READY_FOR_REVIEW = "Ready for review "
EFFECTIVE = "Effective "
INEFFECTIVE = "Ineffective"
NO_POPULATION = "No population "
PASS = "Pass"
NEEDS_ACTION = "Needs Action"
NOT_APPLICABLE = "Not applicable"
ADDRESSED = "Addressed and corrected"

# The template's placeholders, per column.
SELECT = "Please select…"
SELECT_SPACED = "Please select… "
COMPLETE_SECTION = "Please complete the section…"
COMMENTS = "Place for comments"

FREQUENCY_WORDS = {
    "annual": "Annually",
    "annually": "Annually",
    "bi-annual": "Bi-Annually",
    "bi-annually": "Bi-Annually",
    "upon occurrence": "Upon Occurrence",
}


def template_frequency(raw: str | None) -> str | None:
    """A frequency as the template words it (Annually, Bi-Annually, …)."""
    if not raw:
        return None
    return FREQUENCY_WORDS.get(raw.strip().lower(), raw.strip())


@dataclass
class CrpRow:
    """One control's row in a phase sheet. None leaves a cell as it is."""

    control_number: str
    entity_code: str | None
    # Written only where the sheet has no row for the control yet (Rollforward).
    short_name: str
    frequency: str | None
    control_type: str | None
    ipe: str | None
    documents: str
    test_performed: str
    test_result: str
    tester: str
    mandatory_fields: str
    ipe_section: str
    preparer_identified: str
    samples_appropriate: str
    comments: list[str] = field(default_factory=list)
    follow_up: str = NOT_APPLICABLE
    # Cell notes (Excel comments) by column: the detail behind the row.
    notes: dict[str, str] = field(default_factory=dict)
    # The phase is not complete: only the control's identity is shown, the
    # tracker and review cells stay on the template's placeholders.
    identity_only: bool = False

    @property
    def key(self) -> str:
        """How the template names the control: IA5.CA03.1.19A1."""
        return (
            f"{self.control_number}.{self.entity_code}" if self.entity_code else self.control_number
        )

    def cells(self, include_identity: bool) -> dict[str, str | None]:
        if self.identity_only:
            pending: dict[str, str | None] = {
                "D": self.short_name,
                "F": self.frequency,
                "H": self.control_type,
                "J": self.ipe,
                "L": SELECT_SPACED,
                "N": SELECT_SPACED,
                "P": SELECT_SPACED,
                "R": COMPLETE_SECTION,
                "T": SELECT,
                "V": SELECT,
                "X": SELECT,
                "Z": SELECT,
                "AB": COMMENTS,
                "AD": SELECT,
                "AF": SELECT,
                "AH": COMMENTS,
                "AJ": SELECT_SPACED,
                "AL": SELECT_SPACED,
            }
            return pending
        values: dict[str, str | None] = {
            "F": self.frequency,
            "H": self.control_type,
            "J": self.ipe,
            "L": self.documents,
            "N": self.test_performed,
            "P": self.test_result,
            "R": self.tester,
            "T": self.mandatory_fields,
            "V": self.ipe_section,
            "X": self.preparer_identified,
            "Z": self.samples_appropriate,
            "AB": "\n".join(self.comments) if self.comments else COMMENTS,
            # Outside the platform: Optro and TeamMate+ stay unselected.
            "AD": SELECT,
            "AF": SELECT,
            "AH": COMMENTS,
            "AJ": self.follow_up,
            "AL": SELECT_SPACED,
        }
        if include_identity:
            values["D"] = self.short_name
        return values


# ── XML plumbing ────────────────────────────────────────────────────────────


def _col_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def _split_ref(ref: str) -> tuple[str, int]:
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    if not m:
        raise ValueError(ref)
    return m.group(1), int(m.group(2))


def _sheet_paths(files: dict[str, bytes]) -> dict[str, str]:
    """Sheet name → its part path inside the package."""
    workbook = files["xl/workbook.xml"].decode("utf-8")
    rels = files["xl/_rels/workbook.xml.rels"].decode("utf-8")
    targets = {}
    for rel in re.findall(r"<Relationship [^>]*>", rels):
        rid = re.search(r'Id="([^"]+)"', rel)
        target = re.search(r'Target="([^"]+)"', rel)
        if rid and target:
            targets[rid.group(1)] = target.group(1)
    out: dict[str, str] = {}
    for name, rid in re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', workbook):
        target = targets.get(rid, "")
        out[_unescape(name)] = "xl/" + target.lstrip("/").removeprefix("xl/")
    return out


def _unescape(text: str) -> str:
    return (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )


def _shared_strings(files: dict[str, bytes]) -> list[str]:
    raw = files.get("xl/sharedStrings.xml")
    if not raw:
        return []
    out = []
    for si in re.findall(r"<si>(.*?)</si>", raw.decode("utf-8"), re.S):
        out.append(_unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))))
    return out


def _cell_text(cell_xml: str, shared: list[str]) -> str | None:
    if 't="s"' in cell_xml:
        m = re.search(r"<v>(\d+)</v>", cell_xml)
        return shared[int(m.group(1))] if m else None
    m = re.search(r"<t[^>]*>(.*?)</t>", cell_xml, re.S)
    if m:
        return _unescape(m.group(1))
    m = re.search(r"<v>(.*?)</v>", cell_xml, re.S)
    return _unescape(m.group(1)) if m else None


_CELL = r'<c r="{ref}"(?:\s[^>]*?)?(?:/>|>.*?</c>)'


def _row_xml(sheet: str, row: int) -> re.Match[str] | None:
    return re.search(rf'<row r="{row}"[^>]*?(?:/>|>.*?</row>)', sheet, re.S)


def _read(sheet: str, ref: str, shared: list[str]) -> str | None:
    m = re.search(_CELL.format(ref=ref), sheet, re.S)
    return _cell_text(m.group(0), shared) if m else None


def _write(sheet: str, ref: str, value: str) -> str:
    """Set a cell to a string, keeping its style; insert the cell if absent."""
    m = re.search(_CELL.format(ref=ref), sheet, re.S)
    text = escape(value)
    if m:
        style = re.search(r'\ss="(\d+)"', m.group(0).split(">", 1)[0])
        attrs = f' s="{style.group(1)}"' if style else ""
        new = f'<c r="{ref}"{attrs} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
        return sheet[: m.start()] + new + sheet[m.end() :]
    col, row = _split_ref(ref)
    rm = _row_xml(sheet, row)
    if rm is None:
        raise ValueError(f"Row {row} is not in the sheet; the template's rows are never added.")
    new = f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
    body = rm.group(0)
    if body.endswith("/>"):
        filled = body[:-2] + ">" + new + "</row>"
    else:
        # Keep cells in column order.
        cells = list(re.finditer(r'<c r="([A-Z]+)\d+"', body))
        at = next((c.start() for c in cells if _col_index(c.group(1)) > _col_index(col)), None)
        if at is None:
            at = body.rindex("</row>")
        filled = body[:at] + new + body[at:]
    return sheet[: rm.start()] + filled + sheet[rm.end() :]


def _find_row(sheet: str, key: str, shared: list[str], first: int = 6) -> int | None:
    """The row whose control column (D) names the control."""
    pattern = re.compile(rf"(?<![\w]){re.escape(key)}(?![\w])")
    for row in range(first, 400):
        text = _read(sheet, f"D{row}", shared)
        if text and pattern.search(text):
            return row
    return None


# ── Filling ─────────────────────────────────────────────────────────────────

# Columns a list row holds, besides the number (B, kept with its formula).
_ROW_COLUMNS = [
    "A",
    "D",
    "F",
    "H",
    "J",
    "L",
    "N",
    "P",
    "R",
    "T",
    "V",
    "X",
    "Z",
    "AB",
    "AD",
    "AF",
    "AH",
    "AJ",
    "AL",
]


def _clear(sheet: str, ref: str) -> str:
    """Empty a cell, keeping its style."""
    m = re.search(_CELL.format(ref=ref), sheet, re.S)
    if not m:
        return sheet
    style = re.search(r'\ss="(\d+)"', m.group(0).split(">", 1)[0])
    new = f'<c r="{ref}" s="{style.group(1)}"/>' if style else f'<c r="{ref}"/>'
    return sheet[: m.start()] + new + sheet[m.end() :]


def _set_hidden(sheet: str, row: int, hidden: bool) -> str:
    rm = _row_xml(sheet, row)
    if rm is None:
        return sheet
    head, rest = (
        rm.group(0).split(">", 1) if not rm.group(0).endswith("/>") else (rm.group(0)[:-2], "/>")
    )
    head = re.sub(r'\shidden="1"', "", head)
    if hidden:
        head += ' hidden="1"'
    joined = head + (rest if rest == "/>" else ">" + rest)
    return sheet[: rm.start()] + joined + sheet[rm.end() :]


def _list_rows(sheet: str, shared: list[str], first: int = 6) -> list[int]:
    """The numbered rows of a sheet's control list."""
    rows = []
    for row in range(first, 400):
        if _row_xml(sheet, row) is None:
            if rows:
                break
            continue
        b = re.search(_CELL.format(ref=f"B{row}"), sheet, re.S)
        if not b or (
            "<v>" not in b.group(0) and "<f>" not in b.group(0) and "<is>" not in b.group(0)
        ):
            break
        rows.append(row)
    return rows


def _note_rows(sheet: str, shared: list[str], after: int) -> list[int]:
    """Rows below the list that carry the template's scope notes (column D)."""
    return [
        row
        for row in range(after + 1, after + 8)
        if (_read(sheet, f"D{row}", shared) or "").strip()
    ]


def _comments_parts(notes: dict[str, str], idmap: int) -> tuple[str, str]:
    """Excel's comments part and its legacy VML drawing for some cell notes."""
    comments = []
    shapes = []
    for k, (ref, text) in enumerate(notes.items()):
        col, row = _split_ref(ref)
        c = _col_index(col) - 1
        runs = (
            '<r><rPr><b/><sz val="9"/><rFont val="Tahoma"/><family val="2"/></rPr>'
            '<t xml:space="preserve">Velora:</t></r>'
            '<r><rPr><sz val="9"/><rFont val="Tahoma"/><family val="2"/></rPr>'
            f'<t xml:space="preserve">\n{escape(text)}</t></r>'
        )
        comments.append(f'<comment ref="{ref}" authorId="0"><text>{runs}</text></comment>')
        lines = max(6, min(40, text.count("\n") + len(text) // 70 + 2))
        shapes.append(
            f'<v:shape id="_x0000_s{idmap * 1024 + k + 1}" type="#_x0000_t202" '
            'style="position:absolute;margin-left:80pt;margin-top:2pt;width:340pt;'
            f'height:{lines * 12}pt;z-index:{k + 1};visibility:hidden" fillcolor="#ffffe1" '
            'o:insetmode="auto"><v:fill color2="#ffffe1"/>'
            '<v:shadow on="t" color="black" obscured="t"/><v:path o:connecttype="none"/>'
            '<v:textbox style="mso-direction-alt:auto"><div style="text-align:left"></div></v:textbox>'
            '<x:ClientData ObjectType="Note"><x:MoveWithCells/><x:SizeWithCells/>'
            f"<x:Anchor>{c + 1}, 15, {row - 1}, 2, {c + 6}, 15, {row - 1 + lines // 2}, 2</x:Anchor>"
            f"<x:AutoFill>False</x:AutoFill><x:Row>{row - 1}</x:Row><x:Column>{c}</x:Column>"
            "</x:ClientData></v:shape>"
        )
    comments_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<authors><author>Velora</author></authors>"
        f'<commentList>{"".join(comments)}</commentList></comments>'
    )
    vml = (
        '<xml xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:x="urn:schemas-microsoft-com:office:excel">'
        f'<o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="{idmap}"/></o:shapelayout>'
        '<v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202" '
        'path="m,l,21600r21600,l21600,xe"><v:stroke joinstyle="miter"/>'
        '<v:path gradientshapeok="t" o:connecttype="rect"/></v:shapetype>'
        f'{"".join(shapes)}</xml>'
    )
    return comments_xml, vml


def _attach_notes(
    files: dict[str, bytes], names: list[str], part: str, notes: dict[str, str], idmap: int
) -> None:
    """Give a sheet cell notes: a comments part, its VML drawing, the
    relationships and content types, and the sheet's legacyDrawing link."""
    comments_xml, vml = _comments_parts(notes, idmap)
    comments_part = f"xl/comments{idmap}.xml"
    vml_part = f"xl/drawings/vmlDrawing{idmap}.vml"
    files[comments_part] = comments_xml.encode("utf-8")
    files[vml_part] = vml.encode("utf-8")
    names.extend([comments_part, vml_part])

    rels_part = part.replace("worksheets/", "worksheets/_rels/") + ".rels"
    rels = (
        files[rels_part].decode("utf-8")
        if rels_part in files
        else '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        "</Relationships>"
    )
    if rels_part not in files:
        names.append(rels_part)
    used = [int(n) for n in re.findall(r'Id="rId(\d+)"', rels)]
    vml_id, comments_id = f"rId{max(used, default=0) + 1}", f"rId{max(used, default=0) + 2}"
    base = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rels = rels.replace(
        "</Relationships>",
        f'<Relationship Id="{vml_id}" Type="{base}/vmlDrawing" '
        f'Target="../drawings/vmlDrawing{idmap}.vml"/>'
        f'<Relationship Id="{comments_id}" Type="{base}/comments" '
        f'Target="../comments{idmap}.xml"/></Relationships>',
    )
    files[rels_part] = rels.encode("utf-8")

    sheet = files[part].decode("utf-8")
    link = f'<legacyDrawing r:id="{vml_id}"/>'
    # legacyDrawing sits after drawing / page setup and before extLst.
    anchor = re.search(
        r"<legacyDrawingHF|<picture |<oleObjects|<controls|<tableParts|<extLst", sheet
    )
    sheet = (
        sheet[: anchor.start()] + link + sheet[anchor.start() :]
        if anchor
        else (sheet.replace("</worksheet>", link + "</worksheet>"))
    )
    files[part] = sheet.encode("utf-8")

    types = files["[Content_Types].xml"].decode("utf-8")
    if 'Extension="vml"' not in types:
        types = types.replace(
            "<Override ",
            '<Default Extension="vml" ContentType="application/vnd.openxmlformats-officedocument.vmlDrawing"/><Override ',
            1,
        )
    types = types.replace(
        "</Types>",
        f'<Override PartName="/{comments_part}" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"/></Types>',
    )
    files["[Content_Types].xml"] = types.encode("utf-8")


def fill_crp(
    template: bytes,
    rows_by_phase: dict[str, list[CrpRow]],
    intro: dict[str, str] | None = None,
    scope_notes: dict[str, list[str]] | None = None,
) -> bytes:
    """The template with each phase's sheet showing only the given controls.

    Each phase sheet's control list is rewritten from its first row with the
    controls in scope; the rest of the list is emptied (numbers kept) and
    hidden, and the scope notes under it are replaced with `scope_notes`.
    Cell notes carry the detail behind each row. Stale filter criteria are
    cleared so the rows shown are exactly the cycle's. Every other sheet,
    style, dropdown and format is left untouched.
    """
    with zipfile.ZipFile(io.BytesIO(template)) as z:
        names = z.namelist()
        files = {n: z.read(n) for n in names}
        infos = {n: z.getinfo(n) for n in names}
    shared = _shared_strings(files)
    paths = _sheet_paths(files)

    def listed_name(key: str) -> str | None:
        """How the client's own lists name a control."""
        for sheet_name in PHASE_SHEETS.values():
            part = paths.get(sheet_name)
            if not part:
                continue
            xml = files[part].decode("utf-8")
            row = _find_row(xml, key, shared)
            if row is not None:
                return _read(xml, f"D{row}", shared)
        return None

    names_by_key = {r.key: listed_name(r.key) for rows in rows_by_phase.values() for r in rows}
    idmap = 0
    for phase, rows in rows_by_phase.items():
        part = paths.get(PHASE_SHEETS.get(phase, ""))
        if not part:
            continue
        sheet = files[part].decode("utf-8")
        list_rows = _list_rows(sheet, shared)
        notes: dict[str, str] = {}
        for i, row in enumerate(list_rows):
            crp_row = rows[i] if i < len(rows) else None
            for col in _ROW_COLUMNS:
                sheet = _clear(sheet, f"{col}{row}")
            sheet = _set_hidden(sheet, row, crp_row is None)
            if crp_row is None:
                continue
            crp_row.short_name = names_by_key.get(crp_row.key) or crp_row.short_name
            for col, value in crp_row.cells(include_identity=True).items():
                if value is not None:
                    sheet = _write(sheet, f"{col}{row}", value)
            for col, text in crp_row.notes.items():
                notes[f"{col}{row}"] = text

        # The template's scope notes describe the client's full control list.
        if list_rows:
            lines = list((scope_notes or {}).get(phase, []))
            note_rows = _note_rows(sheet, shared, list_rows[-1])
            for j, row in enumerate(note_rows):
                text = (
                    "\n".join(lines[j:])
                    if j == len(note_rows) - 1
                    else (lines[j] if j < len(lines) else "")
                )
                sheet = _write(sheet, f"D{row}", text) if text else _clear(sheet, f"D{row}")

        # A saved filter would hide rows again when re-applied.
        sheet = re.sub(
            r"(<autoFilter [^>]*?)>(?:<filterColumn .*?</filterColumn>|<filterColumn [^>]*/>)+</autoFilter>",
            r"\1/>",
            sheet,
            flags=re.S,
        )
        files[part] = sheet.encode("utf-8")
        if notes:
            idmap += 1
            _attach_notes(files, names, part, notes, idmap)

    if intro:
        part = paths.get("Introductory Page")
        if part:
            sheet = files[part].decode("utf-8")
            for ref, value in intro.items():
                if value:
                    sheet = _write(sheet, ref, value)
            files[part] = sheet.encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            if n in infos:
                z.writestr(infos[n], files[n], compress_type=zipfile.ZIP_DEFLATED)
            else:
                z.writestr(n, files[n])
    return out.getvalue()
