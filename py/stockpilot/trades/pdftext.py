"""Text out of a password-protected PDF (contract notes and CAS statements use the PAN)."""
import io

from pypdf import PdfReader


def text(data: bytes, password: str) -> str:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(password):
        raise ValueError("PDF password was not accepted (is it the PAN, in capitals?)")
    return "\n".join(page.extract_text() or "" for page in reader.pages)
