"""Build a tiny .xlsx in memory for tests (inline strings only): {sheet name: [row as {col: text}]}."""
import io
import zipfile
from xml.sax.saxutils import escape


def make_xlsx(sheets: dict) -> bytes:
    names = list(sheets)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, 1))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(names) + 1))
                   + "</Relationships>")
        for i, n in enumerate(names, 1):
            body = ""
            for r, row in enumerate(sheets[n], 1):
                cells = "".join(f'<c r="{col}{r}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>' for col, v in row.items())
                body += f'<row r="{r}">{cells}</row>'
            z.writestr(f"xl/worksheets/sheet{i}.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                       f"<sheetData>{body}</sheetData></worksheet>")
    return out.getvalue()
