from __future__ import annotations

from html import escape as html_escape
from io import BytesIO
from textwrap import wrap
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from app.schemas import Report


def report_sections(report: Report) -> list[tuple[str, str]]:
    sections = [
        ("Executive Summary", report.executive_summary),
        ("Market Analysis", report.market_analysis),
        ("Trend Analysis", report.trend_analysis),
        ("Patent Analysis", report.patent_analysis),
        ("Competitor Analysis", report.competitor_analysis),
        ("Pain Point Analysis", report.pain_point_analysis),
        ("Supply Chain Analysis", report.supply_chain_analysis),
        ("Innovation Analysis", report.innovation_analysis),
        ("Final Recommendation", report.final_recommendation),
    ]
    if report.data_quality_summary:
        sections.append(("Data Sources and Confidence", report.data_quality_summary))
    sections.append(("Risk Notice", "OpportunityOS provides commercial intelligence and AI suggestions, not legal, investment, or patent infringement advice."))
    return sections


def safe_filename(value: str, extension: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return f"{cleaned[:80] or 'opportunity-report'}.{extension}"


def download_content_disposition(filename: str) -> str:
    stem, separator, extension = filename.rpartition(".")
    ascii_stem = "".join(
        char if char.isascii() and (char.isalnum() or char in {"-", "_"}) else "-"
        for char in (stem if separator else filename)
    )
    ascii_stem = "-".join(part for part in ascii_stem.split("-") if part)
    fallback = f"{ascii_stem[:64] or 'opportunity-report'}{f'.{extension}' if separator else ''}"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def markdown_bytes(report: Report) -> bytes:
    return report.markdown_content.encode("utf-8")


def xlsx_bytes(report: Report) -> bytes:
    rows = [
        ["Report Title", report.report_title],
        ["Score", str(report.report_score)],
        ["Status", report.status],
        ["Created At", report.created_at.isoformat()],
        [],
        ["Section", "Content"],
        *[[title, content] for title, content in report_sections(report)],
    ]

    def cell_ref(column_index: int, row_index: int) -> str:
        return f"{chr(65 + column_index)}{row_index}"

    sheet_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            escaped = html_escape(value)
            cells.append(f'<c r="{cell_ref(column_index, row_index)}" t="inlineStr"><is><t xml:space="preserve">{escaped}</t></is></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    worksheet = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <cols><col min="1" max="1" width="24" customWidth="1"/><col min="2" max="2" width="96" customWidth="1"/></cols>
  <sheetData>{''.join(sheet_rows)}</sheetData>
</worksheet>"""

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Opportunity Report" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return buffer.getvalue()


def docx_bytes(report: Report) -> bytes:
    paragraphs = [report.report_title, f"Score: {report.report_score}/100", ""]
    for title, content in report_sections(report):
        paragraphs.extend([title, content, ""])

    body = []
    for index, paragraph in enumerate(paragraphs):
        text = html_escape(paragraph)
        if index == 0:
            body.append(f'<w:p><w:r><w:rPr><w:b/><w:sz w:val="32"/></w:rPr><w:t xml:space="preserve">{text}</w:t></w:r></w:p>')
        elif paragraph in {title for title, _ in report_sections(report)}:
            body.append(f'<w:p><w:r><w:rPr><w:b/><w:sz w:val="24"/></w:rPr><w:t xml:space="preserve">{text}</w:t></w:r></w:p>')
        else:
            body.append(f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>')

    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {''.join(body)}
    <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>"""

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def pdf_bytes(report: Report) -> bytes:
    raw_lines = [report.report_title, f"Score: {report.report_score}/100", ""]
    for title, content in report_sections(report):
        raw_lines.extend([title, *wrap(content, width=92), ""])

    lines = [line.encode("latin-1", "replace").decode("latin-1") for line in raw_lines]
    pages = [lines[index : index + 42] for index in range(0, len(lines), 42)] or [[]]
    objects: list[bytes] = []

    def pdf_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_refs = " ".join(f"{4 + index * 2} 0 R" for index in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{page_refs}] /Count {len(pages)} >>".encode("latin-1"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page_index, page_lines in enumerate(pages):
        page_obj = 4 + page_index * 2
        content_obj = page_obj + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>".encode(
                "latin-1",
            ),
        )
        stream_lines = ["BT", "/F1 11 Tf", "50 750 Td", "15 TL"]
        for line in page_lines:
            stream_lines.append(f"({pdf_escape(line)}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1")
        objects.append(b"<< /Length " + str(len(stream)).encode("latin-1") + b" >>\nstream\n" + stream + b"\nendstream")

    result = BytesIO()
    result.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(result.tell())
        result.write(f"{index} 0 obj\n".encode("latin-1"))
        result.write(obj)
        result.write(b"\nendobj\n")
    xref_start = result.tell()
    result.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    result.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
    result.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("latin-1"))
    return result.getvalue()
