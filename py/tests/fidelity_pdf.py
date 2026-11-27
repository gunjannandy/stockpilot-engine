"""A trimmed Fidelity 'Current Shares' PDF: wrapped cells, made-up numbers."""
import io

from reportlab.pdfgen import canvas

COLS = [49, 96, 139, 187, 237, 285, 335, 387, 437, 491, 526]
HEAD = [("Date ac", "quired"), ("Quanti", "ty"), ("Cost", "basis"), ("Cost bas", "is/share"), ("Value", ""), ("Gain/los", "s"),
        ("Sale avai", "lability"), ("Transfer", "availabili"), ("Grant", "date"), ("Shar", "e so"), ("Holdi", "ng pe")]


def _row(c, y, cells):
    for x, (a, b) in zip(COLS, cells):
        c.drawString(x, y, a)
        if b:
            c.drawString(x, y - 9, b)


def make(rows) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(595, 842))
    c.setFont("Helvetica", 5)
    c.drawString(40, 780, "CSV Export")
    _row(c, 727, HEAD)
    y = 683
    for r in rows:
        _row(c, y, r)
        y -= 36
    c.drawString(49, y - 20, "The values are displayed in INR")
    c.save()
    return buf.getvalue()


def lot(day_a, day_b, qty, basis, share, value, gain, sale, transfer, grant, term):
    return [(day_a, day_b), (qty[:6], qty[6:]), (basis[:7], basis[7:]), (share[:8], share[8:]), (value[:7], value[7:]), (gain[:7], gain[7:]),
            (sale[:9], sale[9:]), (transfer[:9], transfer[9:]), (grant[:9], grant[9:]), ("RS", "U"), (term, "")]


ROWS = [
    lot("Aug-17-", "2024", "10.0000", "100000.10", "10000.01", "120000.20", "20000.10", "Aug-17-2024", "Aug-17-2024", "Mar-01-2024", "Long"),
    lot("Nov-17-", "2025", "5.5000", "60000.00", "10909.09", "55000.00", "-5000.00", "Nov-17-2025", "Nov-17-2025", "Mar-01-2025", "Short"),
]
