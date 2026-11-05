"""Report exports: CSV (first table), Excel (every section, report header on each sheet, right to left in Arabic) and
PowerPoint (title slide with KPIs, then tables of at most 14 rows per slide). PDF is the browser's print view of the
report page (print stylesheet), which keeps Arabic shaping exact without a server-side PDF engine."""
from __future__ import annotations

import csv
import io
import re

from ..core import pptx, xlsx

HEAD = xlsx.Style(bold=True, color="FFFFFF", fill="142029", border="D8D3C7")
TITLE = xlsx.Style(bold=True, size=14, color="142029")
META = xlsx.Style(italic=True, size=9, color="5B646B")
CELL = xlsx.Style(border="E3DFD5")
PCT = xlsx.Style(border="E3DFD5", percent=True)


def _fmt(value, kind):
    if value is None:
        return ""
    if kind == "percent" and isinstance(value, (int, float)):
        return f"{round(value)}%"
    if kind == "money" and isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return value


def _title(result: dict, lang: str) -> str:
    return result["titleAr"] if lang == "AR" else (f"{result['titleEn']} / {result['titleAr']}" if lang == "BILINGUAL"
                                                   else result["titleEn"])


def _meta_lines(result: dict, lang: str) -> list[str]:
    h = result["header"]
    ar = lang == "AR"
    filters = ", ".join(f"{k}: {v}" for k, v in (h.get("filters") or {}).items() if v not in (None, "")) or ("لا يوجد" if ar else "None")
    return [h["classification"],
            (f"تاريخ الإنشاء: {h['generatedAt'][:16].replace('T', ' ')} UTC · أنشئ بواسطة: {h['generatedBy']} · الدور: {h['role']}"
             if ar else f"Generated: {h['generatedAt'][:16].replace('T', ' ')} UTC · By: {h['generatedBy']} · Role: {h['role']}"),
            (f"عوامل التصفية: {filters}" if ar else f"Filters: {filters}")]


def file_name(result: dict, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9-]+", "-", result["key"]).strip("-") or "report"
    return f"{base}-{result['header']['asOf']}.{ext}"


def _safe(value):
    # A cell starting with = + - @ would run as a formula in a spreadsheet: prefix it (CSV injection).
    return ("'" + value) if isinstance(value, str) and value[:1] in ("=", "+", "-", "@") else value


def to_csv(result: dict, lang: str) -> bytes:
    table = next((s for s in result["sections"] if s["kind"] == "table"), None)
    out = io.StringIO()
    writer = csv.writer(out)
    if table:
        writer.writerow([c["label"] for c in table["columns"]])
        for row in table["rows"]:
            writer.writerow([_safe(_fmt(row.get(c["key"]), c["kind"])) for c in table["columns"]])
    return ("﻿" + out.getvalue()).encode("utf-8")


def to_xlsx(result: dict, lang: str) -> bytes:
    rtl = lang == "AR"
    sheets = []
    tables = [s for s in result["sections"] if s["kind"] in ("table", "kpis", "list")]
    for n, section in enumerate(tables, start=1):
        sheet = xlsx.Sheet(xlsx.safe_sheet_name(f"{n}. {section.get('title') or _title(result, lang)}"), right_to_left=rtl)
        sheet.add([xlsx.Cell(_title(result, lang), TITLE)], 22)
        for line in _meta_lines(result, lang):
            sheet.add([xlsx.Cell(line, META)])
        sheet.add([])
        if section["kind"] == "kpis":
            sheet.add([xlsx.Cell(section.get("title") or "", HEAD), xlsx.Cell("", HEAD)])
            for item in section["items"]:
                sheet.add([xlsx.Cell(item["label"], CELL), xlsx.Cell(item["value"], CELL)])
            sheet.widths = {0: 34, 1: 14}
        elif section["kind"] == "list":
            sheet.add([xlsx.Cell(section.get("title") or "", HEAD)])
            if section.get("basis"):
                sheet.add([xlsx.Cell(section["basis"], META)])
            for item in section["items"]:
                sheet.add([xlsx.Cell(item, CELL)])
            sheet.widths = {0: 110}
        else:
            header_row = sheet.add([xlsx.Cell(c["label"], HEAD) for c in section["columns"]])
            for row in section["rows"]:
                cells = []
                for c in section["columns"]:
                    v = row.get(c["key"])
                    if c["kind"] == "percent" and isinstance(v, (int, float)):
                        cells.append(xlsx.Cell(v / 100, PCT))
                    else:
                        cells.append(xlsx.Cell(_safe(v) if v is not None else None, CELL))
                sheet.add(cells)
            last = len(sheet.rows)
            sheet.freeze_rows = header_row
            if section["rows"]:
                sheet.autofilter = f"A{header_row}:{xlsx.column_letter(len(section['columns']) - 1)}{last}"
            sheet.widths = {i: min(max(12, len(c["label"]) + 4), 48) for i, c in enumerate(section["columns"])}
        sheets.append(sheet)
    return xlsx.workbook(sheets, _title(result, lang))


def to_pptx(result: dict, lang: str) -> bytes:
    rtl = lang == "AR"
    meta = " · ".join(_meta_lines(result, lang)[1:2])
    footer = result["header"]["classification"]
    slides = []
    kpis = [(i["label"], str(i["value"])) for s in result["sections"] if s["kind"] == "kpis" for i in s["items"]]
    slides.append(pptx.Slide(title=_title(result, lang), subtitle=meta, kpis=kpis[:12], footer=footer))
    for section in result["sections"]:
        if section["kind"] == "list":
            items = section["items"] or ["—"]
            for start in range(0, len(items), 12):
                slides.append(pptx.Slide(title=section.get("title") or _title(result, lang), subtitle=section.get("basis") or "",
                                         bullets=items[start:start + 12], footer=footer))
        elif section["kind"] == "table":
            columns = section["columns"][:8]
            rows = section["rows"]
            for start in range(0, max(len(rows), 1), 14):
                chunk = rows[start:start + 14]
                table = [[c["label"] for c in columns]] + [[str(_fmt(r.get(c["key"]), c["kind"])) for c in columns] for r in chunk]
                page = f" ({start // 14 + 1})" if len(rows) > 14 else ""
                slides.append(pptx.Slide(title=(section.get("title") or _title(result, lang)) + page, table=table, footer=footer))
        elif section["kind"] == "bar":
            items = section["items"][:12]
            slides.append(pptx.Slide(title=section.get("title") or _title(result, lang), kpis=[(i["label"], str(i["value"])) for i in items],
                                     footer=footer))
    return pptx.presentation(slides, _title(result, lang), rtl)


EXPORTERS = {"CSV": (to_csv, "text/csv", "csv"),
             "XLSX": (to_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
             "PPTX": (to_pptx, "application/vnd.openxmlformats-officedocument.presentationml.presentation", "pptx")}
