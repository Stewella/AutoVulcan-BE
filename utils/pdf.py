import json
from typing import Any


def build_simple_pdf(data: Any, out_path: str) -> None:
    """
    Try to generate a simple PDF containing JSON summary of the result.
    If reportlab is not available, fall back to writing a minimal PDF header.
    """
    try:
        from reportlab.pdfgen import canvas  # type: ignore
        c = canvas.Canvas(out_path)
        c.setTitle("AutoVulcan Result")
        c.drawString(72, 800, "Analysis Result")
        text_obj = c.beginText(72, 780)
        text_obj.setFont("Helvetica", 10)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        for line in payload.splitlines()[:50]:  # limit lines
            text_obj.textLine(line)
        c.drawText(text_obj)
        c.showPage()
        c.save()
    except Exception:
        # Minimal PDF content (non-pretty), ensures a valid PDF file is created
        minimal_pdf = (
            b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
            b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
            b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 72 720 Td (Result Export) Tj ET\nendstream\nendobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n"
        )
        with open(out_path, "wb") as f:
            f.write(minimal_pdf)