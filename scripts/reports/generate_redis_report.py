#!/usr/bin/env python3
import sys
from pathlib import Path

import generate_sre_report as report


ROOT = Path(__file__).resolve().parents[2]
report.SOURCE = ROOT / "reports/redis-usage-monitoring-report.vi.md"
report.OUTPUT = ROOT / "reports/redis-usage-monitoring-report.vi.pdf"


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(report.colors.HexColor("#CBD5E1"))
    canvas.line(18 * report.mm, 15 * report.mm, 192 * report.mm, 15 * report.mm)
    canvas.setFont("NotoSans", 8)
    canvas.setFillColor(report.colors.HexColor("#64748B"))
    canvas.drawString(18 * report.mm, 10 * report.mm, "Production Backend Lab - Redis")
    canvas.drawRightString(192 * report.mm, 10 * report.mm, f"Trang {doc.page}")
    canvas.restoreState()


report.footer = footer


if __name__ == "__main__":
    sys.exit(report.main())
