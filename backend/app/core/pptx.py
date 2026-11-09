"""A small PowerPoint (.pptx) writer using only the standard library (zipfile + XML), like core/xlsx.py.

Slides hold a title, an optional subtitle, KPI boxes, bullet lines and one table. Arabic slides set right-to-left
paragraphs. Text is always written as text (escaped), never interpreted."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape

EMU = 12700  # per point
SLIDE_W, SLIDE_H = 12192000, 6858000
NAVY, GOLD, GREY, WHITE = "142029", "B9995A", "5B646B", "FFFFFF"

NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')


@dataclass
class Slide:
    title: str
    subtitle: str = ""
    kpis: list[tuple[str, str]] = field(default_factory=list)      # (label, value)
    bullets: list[str] = field(default_factory=list)
    table: list[list[str]] | None = None                          # first row = header
    footer: str = ""


def _t(text) -> str:
    return escape("" if text is None else str(text)).replace("\x00", "")


def _para(text, size=14, bold=False, color="1C252D", rtl=False, align=None) -> str:
    algn = align or ("r" if rtl else "l")
    return (f'<a:p><a:pPr algn="{algn}"{" rtl=\"1\"" if rtl else ""}/><a:r><a:rPr lang="{"ar-AE" if rtl else "en-GB"}" '
            f'sz="{size * 100}" b="{1 if bold else 0}" dirty="0"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            f'<a:latin typeface="Arial"/><a:cs typeface="Arial"/></a:rPr><a:t>{_t(text)}</a:t></a:r></a:p>')


def _box(sid, name, x, y, w, h, paras, fill=None, line=None) -> str:
    fill_xml = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else "<a:noFill/>"
    line_xml = f'<a:ln w="9525"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line else "<a:ln><a:noFill/></a:ln>"
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{_t(name)}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            f'{fill_xml}{line_xml}</p:spPr><p:txBody><a:bodyPr wrap="square" lIns="91440" rIns="91440" tIns="45720" bIns="45720">'
            f'<a:normAutofit/></a:bodyPr><a:lstStyle/>{"".join(paras)}</p:txBody></p:sp>')


def _table(sid, x, y, w, rows: list[list[str]], rtl: bool) -> str:
    cols = max(len(r) for r in rows)
    col_w = w // cols
    row_h = 330000
    grid = "".join(f'<a:gridCol w="{col_w}"/>' for _ in range(cols))
    body = []
    for i, row in enumerate(rows):
        cells = []
        for value in (list(reversed(row)) if rtl else row) + [""] * (cols - len(row)):
            header = i == 0
            fill = NAVY if header else ("F3F1EC" if i % 2 == 0 else WHITE)
            cells.append(f'<a:tc><a:txBody><a:bodyPr/><a:lstStyle/>{_para(value, 10, header, WHITE if header else "1C252D", rtl)}</a:txBody>'
                         f'<a:tcPr marL="45720" marR="45720" marT="22860" marB="22860"><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill></a:tcPr></a:tc>')
        body.append(f'<a:tr h="{row_h}">{"".join(cells)}</a:tr>')
    return (f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{sid}" name="Table {sid}"/><p:cNvGraphicFramePr>'
            f'<a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr><p:nvPr/></p:nvGraphicFramePr>'
            f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{row_h * len(rows)}"/></p:xfrm>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table"><a:tbl>'
            f'<a:tblPr firstRow="1" bandRow="1"{" rtl=\"1\"" if rtl else ""}/><a:tblGrid>{grid}</a:tblGrid>{"".join(body)}</a:tbl>'
            f'</a:graphicData></a:graphic></p:graphicFrame>')


def _slide_xml(slide: Slide, rtl: bool) -> str:
    margin = 457200
    width = SLIDE_W - 2 * margin
    shapes = [_box(2, "Bar", 0, 0, SLIDE_W, 91440, [], fill=GOLD),
              _box(3, "Title", margin, 228600, width, 640080, [_para(slide.title, 26, True, NAVY, rtl)])]
    y = 868680
    if slide.subtitle:
        shapes.append(_box(4, "Subtitle", margin, y, width, 365760, [_para(slide.subtitle, 12, False, GREY, rtl)]))
        y += 411480
    sid = 5
    if slide.kpis:
        per_row = 4
        box_w = (width - (per_row - 1) * 137160) // per_row
        for i, (label, value) in enumerate(slide.kpis[:12]):
            row, col = divmod(i, per_row)
            col = per_row - 1 - col if rtl else col
            shapes.append(_box(sid, f"KPI {i}", margin + col * (box_w + 137160), y + row * 822960, box_w, 731520,
                               [_para(label, 11, False, GREY, rtl), _para(value, 24, True, NAVY, rtl)], fill="F7F5F0", line="E3DFD5"))
            sid += 1
        y += ((len(slide.kpis[:12]) + per_row - 1) // per_row) * 822960
    if slide.bullets:
        h = min(len(slide.bullets) * 320040 + 91440, SLIDE_H - y - 640080)
        shapes.append(_box(sid, "Bullets", margin, y, width, h, [_para(f"• {b}", 13, False, "1C252D", rtl) for b in slide.bullets[:14]]))
        sid += 1
        y += h
    if slide.table:
        shapes.append(_table(sid, margin, y + 91440, width, slide.table, rtl))
        sid += 1
    if slide.footer:
        shapes.append(_box(sid, "Footer", margin, SLIDE_H - 457200, width, 320040, [_para(slide.footer, 9, False, GREY, rtl)]))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld {NS}><p:cSld><p:spTree><p:nvGrpSpPr>'
            f'<p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
            f'<a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>{"".join(shapes)}'
            f'</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')


_THEME = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="CPC">'
          '<a:themeElements><a:clrScheme name="CPC"><a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
          '<a:dk2><a:srgbClr val="142029"/></a:dk2><a:lt2><a:srgbClr val="F3F1EC"/></a:lt2><a:accent1><a:srgbClr val="2F6FD6"/></a:accent1>'
          '<a:accent2><a:srgbClr val="B9995A"/></a:accent2><a:accent3><a:srgbClr val="12804A"/></a:accent3><a:accent4><a:srgbClr val="E3A92B"/></a:accent4>'
          '<a:accent5><a:srgbClr val="D24B3E"/></a:accent5><a:accent6><a:srgbClr val="6B52B8"/></a:accent6><a:hlink><a:srgbClr val="1F5FBF"/></a:hlink>'
          '<a:folHlink><a:srgbClr val="5B3FA6"/></a:folHlink></a:clrScheme><a:fontScheme name="CPC"><a:majorFont><a:latin typeface="Arial"/>'
          '<a:ea typeface=""/><a:cs typeface="Arial"/></a:majorFont><a:minorFont><a:latin typeface="Arial"/><a:ea typeface=""/><a:cs typeface="Arial"/>'
          '</a:minorFont></a:fontScheme><a:fmtScheme name="CPC"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
          '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
          '<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="12700"><a:solidFill>'
          '<a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
          '</a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle>'
          '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
          '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
          '</a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>')

_EMPTY_TREE = ('<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>'
               '<a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>'
               '</p:grpSpPr></p:spTree></p:cSld>')

_MASTER = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster {NS}>{_EMPTY_TREE}'
           '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
           'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
           '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
           '<p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>')

_LAYOUT = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout {NS} type="blank" preserve="1">'
           f'{_EMPTY_TREE.replace("<p:cSld>", "<p:cSld name=\"Blank\">")}<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')

_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _rels(items: list[tuple[str, str, str]]) -> str:
    body = "".join(f'<Relationship Id="{rid}" Type="{rtype}" Target="{target}"/>' for rid, rtype, target in items)
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{_PKG_REL}">{body}</Relationships>'


def presentation(slides: list[Slide], title: str = "", rtl: bool = False, created: datetime | None = None) -> bytes:
    created = (created or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        slide_overrides = "".join(
            f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            for i in range(1, len(slides) + 1))
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
                   '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
                   '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
                   '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
                   f'{slide_overrides}'
                   '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                   '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>')
        z.writestr("_rels/.rels", _rels([
            ("rId1", f"{_REL}/officeDocument", "ppt/presentation.xml"),
            ("rId2", "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", "docProps/core.xml"),
            ("rId3", f"{_REL}/extended-properties", "docProps/app.xml")]))
        z.writestr("docProps/core.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
                   'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
                   'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                   f'<dc:title>{_t(title)}</dc:title><dc:creator>National Guard Capability System</dc:creator>'
                   f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created></cp:coreProperties>')
        z.writestr("docProps/app.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties '
                   'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                   f'<Application>National Guard Capability System</Application><Slides>{len(slides)}</Slides></Properties>')
        slide_ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i + 3}"/>' for i in range(len(slides)))
        z.writestr("ppt/presentation.xml",
                   f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation {NS}>'
                   '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                   f'<p:sldIdLst>{slide_ids}</p:sldIdLst><p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}"/><p:notesSz cx="6858000" cy="9144000"/>'
                   '</p:presentation>')
        z.writestr("ppt/_rels/presentation.xml.rels", _rels(
            [("rId1", f"{_REL}/slideMaster", "slideMasters/slideMaster1.xml"), ("rId2", f"{_REL}/theme", "theme/theme1.xml")]
            + [(f"rId{i + 3}", f"{_REL}/slide", f"slides/slide{i + 1}.xml") for i in range(len(slides))]))
        z.writestr("ppt/slideMasters/slideMaster1.xml", _MASTER)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _rels(
            [("rId1", f"{_REL}/slideLayout", "../slideLayouts/slideLayout1.xml"), ("rId2", f"{_REL}/theme", "../theme/theme1.xml")]))
        z.writestr("ppt/slideLayouts/slideLayout1.xml", _LAYOUT)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _rels(
            [("rId1", f"{_REL}/slideMaster", "../slideMasters/slideMaster1.xml")]))
        z.writestr("ppt/theme/theme1.xml", _THEME)
        for i, slide in enumerate(slides, start=1):
            z.writestr(f"ppt/slides/slide{i}.xml", _slide_xml(slide, rtl))
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", _rels(
                [("rId1", f"{_REL}/slideLayout", "../slideLayouts/slideLayout1.xml")]))
    return out.getvalue()
