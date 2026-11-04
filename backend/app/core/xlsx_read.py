"""A small reader for the first sheet of an Excel (.xlsx) file, or a CSV file, standard library only (zipfile + XML):
no new dependency, like the writer in core/xlsx.py.

Returns the sheet as rows of text, each with its row number as Excel shows it. Only cell values are read (shared
strings, inline strings, numbers, true/false); formulas give their last calculated value, formatting is ignored.
Guarded against hostile files: the size of every part is checked before it is unpacked, and XML with a DOCTYPE
(entity tricks) is refused.
"""
from __future__ import annotations

import csv
import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_PART_MAX = 20 * 1024 * 1024  # unpacked size of one part (a 2 MB upload is at most a few MB unpacked)
_CELL_REF = re.compile(r"^([A-Z]{1,3})([0-9]+)$")


class UnreadableFile(ValueError):
    """The file is not a workbook or CSV this reader understands. The message is for the user."""


def read_rows(data: bytes, filename: str = "", max_rows: int = 10_000) -> list[tuple[int, list[str]]]:
    """[(row number, [cell text, ...]), ...] for the first sheet (or the CSV), blank rows left out."""
    if data[:4] == b"PK\x03\x04":
        return _xlsx_rows(data, max_rows)
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise UnreadableFile("This is an older Excel file (.xls). In Excel, use Save As and choose Excel Workbook (.xlsx).")
    if filename.lower().endswith((".csv", ".txt")):
        return _csv_rows(data, max_rows)
    raise UnreadableFile("This file is not an Excel workbook (.xlsx) or a CSV file.")


def _part(book: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        info = book.getinfo(name)
    except KeyError:
        return None
    if info.file_size > _PART_MAX:
        raise UnreadableFile("This file is not an Excel workbook (.xlsx) or a CSV file.")
    with book.open(info) as stream:
        content = stream.read(_PART_MAX + 1)
    if len(content) > _PART_MAX or b"<!DOCTYPE" in content[:4096].upper():
        raise UnreadableFile("This file is not an Excel workbook (.xlsx) or a CSV file.")
    return content


def _xml(content: bytes) -> ET.Element:
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        raise UnreadableFile("This file is not an Excel workbook (.xlsx) or a CSV file.") from None


def _first_sheet_path(book: zipfile.ZipFile) -> str:
    workbook = _part(book, "xl/workbook.xml")
    if workbook is None:
        raise UnreadableFile("This file is not an Excel workbook (.xlsx) or a CSV file.")
    sheet = _xml(workbook).find(f"{_MAIN}sheets/{_MAIN}sheet")
    rels = _part(book, "xl/_rels/workbook.xml.rels")
    if sheet is not None and rels is not None:
        rel_id = sheet.get(f"{_REL}id")
        for rel in _xml(rels).iter(f"{_PKG_REL}Relationship"):
            if rel.get("Id") == rel_id:
                target = rel.get("Target", "")
                return target.lstrip("/") if target.startswith("/") else posixpath.normpath(f"xl/{target}")
    return "xl/worksheets/sheet1.xml"


def _text_of(node: ET.Element) -> str:
    """The text of a shared or inline string: plain <t>, or the runs of rich text (phonetic hints left out)."""
    plain = node.find(f"{_MAIN}t")
    if plain is not None:
        return plain.text or ""
    return "".join(run.findtext(f"{_MAIN}t") or "" for run in node.findall(f"{_MAIN}r"))


def _number(text: str) -> str:
    try:
        value = float(text)
    except ValueError:
        return text
    return str(int(value)) if value.is_integer() and abs(value) < 1e15 else text


def _column_index(letters: str) -> int:
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def _xlsx_rows(data: bytes, max_rows: int) -> list[tuple[int, list[str]]]:
    try:
        book = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UnreadableFile("This file is not an Excel workbook (.xlsx) or a CSV file.") from None
    with book:
        shared_xml = _part(book, "xl/sharedStrings.xml")
        shared = [_text_of(si) for si in _xml(shared_xml).iter(f"{_MAIN}si")] if shared_xml else []
        sheet_xml = _part(book, _first_sheet_path(book))
        if sheet_xml is None:
            raise UnreadableFile("This file is not an Excel workbook (.xlsx) or a CSV file.")
        sheet = _xml(sheet_xml)
    rows: list[tuple[int, list[str]]] = []
    last_row = 0
    for row in sheet.iter(f"{_MAIN}row"):
        number = int(row.get("r") or last_row + 1)
        last_row = number
        cells: dict[int, str] = {}
        next_col = 0
        for cell in row.iter(f"{_MAIN}c"):
            match = _CELL_REF.match(cell.get("r") or "")
            col = _column_index(match.group(1)) if match else next_col
            next_col = col + 1
            kind = cell.get("t")
            value = cell.find(f"{_MAIN}v")
            if kind == "inlineStr":
                inline = cell.find(f"{_MAIN}is")
                text = _text_of(inline) if inline is not None else ""
            elif value is None or value.text is None:
                text = ""
            elif kind == "s":
                try:
                    text = shared[int(value.text)]
                except (ValueError, IndexError):
                    text = ""
            elif kind == "b":
                text = "TRUE" if value.text == "1" else "FALSE"
            elif kind in ("str", "e"):
                text = value.text
            else:
                text = _number(value.text)
            if text.strip() and col < 200:
                cells[col] = text
        if cells:
            rows.append((number, [cells.get(i, "") for i in range(max(cells) + 1)]))
            if len(rows) > max_rows:
                break
    return rows


def _csv_rows(data: bytes, max_rows: int) -> list[tuple[int, list[str]]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1256", errors="replace")  # Excel's plain "CSV" on an Arabic Windows
    if "\x00" in text:
        raise UnreadableFile("This file is not an Excel workbook (.xlsx) or a CSV file.")
    first_line = text.split("\n", 1)[0]
    delimiter = max(",;\t", key=first_line.count)  # Excel uses ";" where the decimal mark is a comma
    rows: list[tuple[int, list[str]]] = []
    for number, record in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1):
        if any(cell.strip() for cell in record):
            rows.append((number, record))
            if len(rows) > max_rows:
                break
    return rows
