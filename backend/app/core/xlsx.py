"""A small Excel (.xlsx) writer, standard library only (zipfile + XML text): no new dependency.

Enough for a formatted report: several sheets, text and numbers, bold/coloured/filled cells, borders, wrapping,
percent format, column widths, merged title cells, frozen header rows, an autofilter, drop-down lists, hidden sheets
and right-to-left sheets (Arabic). Text is written as inline strings, so a value such as "=HYPERLINK(...)" is shown as text and never
becomes a formula.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape

# Characters XML 1.0 does not allow (control characters other than tab, newline and carriage return).
_INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_SHEET_NAME_BAD = re.compile(r"[\[\]:*?/\\]")


@dataclass(frozen=True)
class Style:
    bold: bool = False
    italic: bool = False
    size: float = 11
    color: str | None = None      # font colour, RRGGBB
    fill: str | None = None       # background, RRGGBB
    align: str | None = None      # left / center / right
    valign: str | None = None     # top / center / bottom
    wrap: bool = False
    border: str | None = None     # border colour, RRGGBB (thin, all sides)
    percent: bool = False         # number shown as 0%


@dataclass
class Cell:
    value: str | int | float | None
    style: Style = Style()


@dataclass
class Sheet:
    name: str
    rows: list[tuple[list[Cell], float | None]] = field(default_factory=list)
    widths: dict[int, float] = field(default_factory=dict)   # 0-based column -> width in characters
    merges: list[str] = field(default_factory=list)          # e.g. "A1:F1"
    freeze_rows: int = 0
    autofilter: str | None = None                            # e.g. "A5:H20"
    right_to_left: bool = False                              # column A on the right (an Arabic sheet)
    # Drop-down lists: ("B2:B500", ["A", "B"]) typed into the list itself (at most 255 characters, no commas in a
    # value), or ("B2:B500", list_range(other_sheet, column, count)) read from cells of another (often hidden) sheet.
    choices: list[tuple[str, list[str] | str]] = field(default_factory=list)
    hidden: bool = False                                     # not shown as a tab (e.g. the values of a drop-down list)

    def add(self, cells: list, height: float | None = None) -> int:
        """Append a row; plain values get the default style. Returns the 1-based row number."""
        self.rows.append(([c if isinstance(c, Cell) else Cell(c) for c in cells], height))
        return len(self.rows)


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _text(value: str) -> str:
    return escape(_INVALID_XML.sub("", value))


def list_range(sheet: Sheet, column: int, count: int) -> str:
    """The cells holding a drop-down list's values: the first `count` rows of `column` (0-based) on `sheet`, e.g.
    'Lists'!$A$1:$A$7."""
    letter = column_letter(column)
    return f"{_quoted(safe_sheet_name(sheet.name))}!${letter}$1:${letter}${max(count, 1)}"


def _list_formula(values: list[str] | str) -> str:
    return values if isinstance(values, str) else chr(34) + ",".join(values) + chr(34)


class _Styles:
    """Collects the distinct styles used and writes styles.xml (font, fill and border tables plus cellXfs)."""

    def __init__(self):
        self.fonts = [(False, False, 11, None)]
        self.fills = [None, "gray125"]      # the two fills Excel requires first
        self.borders = [None]
        self.xfs: list[tuple] = [(0, 0, 0, None, None, False, False)]
        self.index: dict[Style, int] = {Style(): 0}

    def _pos(self, table: list, item) -> int:
        if item not in table:
            table.append(item)
        return table.index(item)

    def of(self, style: Style) -> int:
        if style not in self.index:
            font = self._pos(self.fonts, (style.bold, style.italic, style.size, style.color))
            fill = self._pos(self.fills, style.fill) if style.fill else 0
            border = self._pos(self.borders, style.border) if style.border else 0
            self.xfs.append((font, fill, border, style.align, style.valign, style.wrap, style.percent))
            self.index[style] = len(self.xfs) - 1
        return self.index[style]

    def xml(self) -> str:
        fonts = "".join(
            "<font>" + ("<b/>" if bold else "") + ("<i/>" if italic else "") + f'<sz val="{size:g}"/>'
            + (f'<color rgb="FF{color}"/>' if color else "") + '<name val="Calibri"/><family val="2"/></font>'
            for bold, italic, size, color in self.fonts)
        fills = []
        for fill in self.fills:
            if fill is None:
                fills.append('<fill><patternFill patternType="none"/></fill>')
            elif fill == "gray125":
                fills.append('<fill><patternFill patternType="gray125"/></fill>')
            else:
                fills.append(f'<fill><patternFill patternType="solid"><fgColor rgb="FF{fill}"/>'
                             '<bgColor indexed="64"/></patternFill></fill>')
        borders = []
        for colour in self.borders:
            if colour is None:
                borders.append("<border><left/><right/><top/><bottom/><diagonal/></border>")
            else:
                side = f'style="thin"><color rgb="FF{colour}"/>'
                borders.append(f"<border><left {side}</left><right {side}</right><top {side}</top>"
                               f"<bottom {side}</bottom><diagonal/></border>")
        xfs = []
        for font, fill, border, align, valign, wrap, percent in self.xfs:
            attrs = (f'numFmtId="{9 if percent else 0}" fontId="{font}" fillId="{fill}" borderId="{border}" xfId="0"'
                     + (' applyNumberFormat="1"' if percent else "") + (' applyFont="1"' if font else "")
                     + (' applyFill="1"' if fill else "") + (' applyBorder="1"' if border else ""))
            if align or valign or wrap:
                alignment = ("<alignment" + (f' horizontal="{align}"' if align else "")
                             + (f' vertical="{valign}"' if valign else "") + (' wrapText="1"' if wrap else "") + "/>")
                xfs.append(f'<xf {attrs} applyAlignment="1">{alignment}</xf>')
            else:
                xfs.append(f"<xf {attrs}/>")
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<fonts count="{len(self.fonts)}">{fonts}</fonts>'
            f'<fills count="{len(self.fills)}">{"".join(fills)}</fills>'
            f'<borders count="{len(self.borders)}">{"".join(borders)}</borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>")


def _sheet_xml(sheet: Sheet, styles: _Styles) -> str:
    rows = []
    for number, (cells, height) in enumerate(sheet.rows, start=1):
        out = []
        for col, cell in enumerate(cells):
            ref = f"{column_letter(col)}{number}"
            s = styles.of(cell.style)
            style_attr = f' s="{s}"' if s else ""
            value = cell.value
            if value is None or value == "":
                if s:
                    out.append(f'<c r="{ref}"{style_attr}/>')
            elif isinstance(value, bool):
                out.append(f'<c r="{ref}"{style_attr} t="b"><v>{int(value)}</v></c>')
            elif isinstance(value, (int, float)):
                out.append(f'<c r="{ref}"{style_attr}><v>{value!r}</v></c>')
            else:
                text = _text(str(value))
                space = ' xml:space="preserve"' if text != text.strip() or "\n" in text else ""
                out.append(f'<c r="{ref}"{style_attr} t="inlineStr"><is><t{space}>{text}</t></is></c>')
        height_attr = f' ht="{height:g}" customHeight="1"' if height else ""
        rows.append(f'<row r="{number}"{height_attr}>{"".join(out)}</row>')
    rtl = ' rightToLeft="1"' if sheet.right_to_left else ""
    if sheet.freeze_rows:
        top = f"A{sheet.freeze_rows + 1}"
        view = (f'<sheetView{rtl} workbookViewId="0"><pane ySplit="{sheet.freeze_rows}" topLeftCell="{top}" '
                f'activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="{top}" '
                f'sqref="{top}"/></sheetView>')
    else:
        view = f'<sheetView{rtl} workbookViewId="0"/>'
    cols = "".join(f'<col min="{c + 1}" max="{c + 1}" width="{w:g}" customWidth="1"/>'
                   for c, w in sorted(sheet.widths.items()))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'  # print one page wide (pageSetup fitToWidth below)
        f"<sheetViews>{view}</sheetViews>"
        '<sheetFormatPr defaultRowHeight="15"/>'
        + (f"<cols>{cols}</cols>" if cols else "")
        + f'<sheetData>{"".join(rows)}</sheetData>'
        + (f'<autoFilter ref="{sheet.autofilter}"/>' if sheet.autofilter else "")
        + (f'<mergeCells count="{len(sheet.merges)}">'
           + "".join(f'<mergeCell ref="{m}"/>' for m in sheet.merges) + "</mergeCells>" if sheet.merges else "")
        + (f'<dataValidations count="{len(sheet.choices)}">' + "".join(
            f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="{ref}">'
            f'<formula1>{_text(_list_formula(values))}</formula1></dataValidation>'
            for ref, values in sheet.choices) + "</dataValidations>" if sheet.choices else "")
        + '<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>'
        '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>'
        "</worksheet>")


def safe_sheet_name(name: str) -> str:
    return (_SHEET_NAME_BAD.sub(" ", name).strip() or "Sheet")[:31]


def workbook(sheets: list[Sheet], title: str = "", created: datetime | None = None) -> bytes:
    styles = _Styles()
    sheet_xml = [_sheet_xml(sheet, styles) for sheet in sheets]  # first, so every style is registered
    created = (created or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = len(sheets)
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                      'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                      for i in range(1, n + 1))
            + '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '<Override PartName="/docProps/core.xml" '
            'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            "</Types>"),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/'
            'core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'extended-properties" Target="docProps/app.xml"/>'
            "</Relationships>"),
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{_text(title)}</dc:title><dc:creator>Capability Portfolio Command</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
            "</cp:coreProperties>"),
        "docProps/app.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            "<Application>Capability Portfolio Command</Application></Properties>"),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(f'<sheet name="{escape(safe_sheet_name(s.name), {chr(34): "&quot;"})}" sheetId="{i}"'
                      + (' state="hidden"' if s.hidden else "") + f' r:id="rId{i}"/>'
                      for i, s in enumerate(sheets, start=1))
            + "</sheets>"
            + _defined_names(sheets)
            + "</workbook>"),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                      f'relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, n + 1))
            + f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/styles" Target="styles.xml"/>'
            "</Relationships>"),
        "xl/styles.xml": styles.xml(),
    }
    for i, xml in enumerate(sheet_xml, start=1):
        files[f"xl/worksheets/sheet{i}.xml"] = xml
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text.encode("utf-8"))
    return buffer.getvalue()


def _defined_names(sheets: list[Sheet]) -> str:
    """The hidden name Excel keeps for each sheet's autofilter range."""
    names = "".join(
        f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
        f"{_text(_quoted(safe_sheet_name(s.name)))}!{_absolute(s.autofilter)}</definedName>"
        for i, s in enumerate(sheets) if s.autofilter)
    return f"<definedNames>{names}</definedNames>" if names else ""


def _quoted(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _absolute(ref: str) -> str:
    return re.sub(r"([A-Z]+)(\d+)", r"$\1$\2", ref)
