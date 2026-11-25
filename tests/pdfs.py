"""Build small password-protected text PDFs for parser tests (reportlab is a dev dependency)."""
import io

from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas


def make_pdf(lines: list[str], password: str | None = None) -> bytes:
    buf = io.BytesIO()
    enc = StandardEncryption(password, ownerPassword=password + "-owner") if password else None
    c = canvas.Canvas(buf, pagesize=(1200, 842), encrypt=enc)
    y = 800
    for line in lines:
        c.setFont("Helvetica", 9)
        c.drawString(20, y, line)
        y -= 14
    c.save()
    return buf.getvalue()
