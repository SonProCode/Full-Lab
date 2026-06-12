#!/usr/bin/env python3
import hashlib
import html
import re
import sys
from pathlib import Path

_openssl_md5 = hashlib.md5
hashlib.md5 = lambda data=b"", **kwargs: _openssl_md5(data)

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/rabbitmq-retry-dlq-explained.vi.md"
OUTPUT = ROOT / "reports/rabbitmq-retry-dlq-explained.vi.pdf"
FONT_REGULAR = ROOT / "reports/assets/NotoSans-Regular.ttf"
FONT_BOLD = ROOT / "reports/assets/NotoSans-Bold.ttf"


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.line(18 * mm, 15 * mm, 192 * mm, 15 * mm)
    canvas.setFont("NotoSans", 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(18 * mm, 10 * mm, "Production Backend Lab - RabbitMQ Retry và DLQ")
    canvas.drawRightString(192 * mm, 10 * mm, f"Trang {doc.page}")
    canvas.restoreState()


def inline_markup(text):
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r'<font name="NotoSans">\1</font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return escaped


def parse_table(lines, styles):
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append([Paragraph(inline_markup(cell), styles["table"]) for cell in cells])
    if not rows:
        return None
    width = 174 * mm
    table = Table(rows, colWidths=[width / len(rows[0])] * len(rows[0]), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F4C81")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "NotoSans-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def build_story(text, styles):
    story, paragraph, table_lines, code_lines = [], [], [], []
    in_code = False

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            story.extend([
                Paragraph(inline_markup(" ".join(x.strip() for x in paragraph)), styles["body"]),
                Spacer(1, 2 * mm),
            ])
            paragraph = []

    def flush_table():
        nonlocal table_lines
        if table_lines:
            table = parse_table(table_lines, styles)
            if table:
                story.extend([table, Spacer(1, 3 * mm)])
            table_lines = []

    for line in text.splitlines():
        if line.startswith("```"):
            flush_paragraph()
            flush_table()
            if in_code:
                story.extend([Preformatted("\n".join(code_lines), styles["code"]), Spacer(1, 3 * mm)])
                code_lines = []
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        if line.startswith("|"):
            flush_paragraph()
            table_lines.append(line)
            continue
        flush_table()
        if not line.strip():
            flush_paragraph()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            story.extend([Paragraph(inline_markup(heading.group(2)), styles[f"h{level}"]), Spacer(1, 2 * mm)])
            continue
        bullet = re.match(r"^-\s+(.+)$", line)
        if bullet:
            flush_paragraph()
            story.append(Paragraph(inline_markup(bullet.group(1)), styles["bullet"], bulletText="•"))
            continue
        numbered = re.match(r"^(\d+)\.\s+(.+)$", line)
        if numbered:
            flush_paragraph()
            story.append(Paragraph(inline_markup(numbered.group(2)), styles["bullet"], bulletText=f"{numbered.group(1)}."))
            continue
        paragraph.append(line)

    flush_paragraph()
    flush_table()
    return story


def main():
    pdfmetrics.registerFont(TTFont("NotoSans", str(FONT_REGULAR)))
    pdfmetrics.registerFont(TTFont("NotoSans-Bold", str(FONT_BOLD)))
    pdfmetrics.registerFontFamily("NotoSans", normal="NotoSans", bold="NotoSans-Bold")

    sample = getSampleStyleSheet()
    styles = {
        "h1": ParagraphStyle(
            "Title", parent=sample["Title"], fontName="NotoSans-Bold", fontSize=20,
            leading=26, textColor=colors.HexColor("#0F4C81"), alignment=TA_CENTER, spaceAfter=8 * mm,
        ),
        "h2": ParagraphStyle(
            "H2", parent=sample["Heading2"], fontName="NotoSans-Bold", fontSize=14,
            leading=18, textColor=colors.HexColor("#0F4C81"), spaceBefore=5 * mm,
        ),
        "h3": ParagraphStyle(
            "H3", parent=sample["Heading3"], fontName="NotoSans-Bold", fontSize=11,
            leading=15, textColor=colors.HexColor("#334155"), spaceBefore=3 * mm,
        ),
        "body": ParagraphStyle(
            "Body", parent=sample["BodyText"], fontName="NotoSans", fontSize=9.3,
            leading=14, alignment=TA_JUSTIFY, textColor=colors.HexColor("#1E293B"),
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=sample["BodyText"], fontName="NotoSans", fontSize=9.2,
            leading=13.5, leftIndent=7 * mm, firstLineIndent=-4 * mm,
            bulletIndent=2 * mm, textColor=colors.HexColor("#1E293B"), spaceAfter=1 * mm,
        ),
        "code": ParagraphStyle(
            "Code", parent=sample["Code"], fontName="NotoSans", fontSize=7.4,
            leading=10.2, leftIndent=4 * mm, rightIndent=4 * mm,
            borderColor=colors.HexColor("#CBD5E1"), borderWidth=0.5,
            borderPadding=5, backColor=colors.HexColor("#F1F5F9"), textColor=colors.HexColor("#0F172A"),
        ),
        "table": ParagraphStyle(
            "Table", parent=sample["BodyText"], fontName="NotoSans", fontSize=7.6,
            leading=10.3, textColor=colors.HexColor("#1E293B"),
        ),
    }

    doc = BaseDocTemplate(
        str(OUTPUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title="Giải thích RabbitMQ Retry và Dead Letter Queue",
        author="Production Backend Lab",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates(PageTemplate(id="report", frames=frame, onPage=footer))
    doc.build(build_story(SOURCE.read_text(encoding="utf-8"), styles))
    print(OUTPUT)


if __name__ == "__main__":
    sys.exit(main())
