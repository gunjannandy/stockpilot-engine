"""A small .xlsx reader on the standard library (no new dependency, no pandas: the VM has 1 GB). Reads cell values
only, as text, one sheet at a time and row by row; numbers stay as the text Excel stored."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_RELS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class Workbook:
    def __init__(self, data: bytes):
        self._zip = zipfile.ZipFile(io.BytesIO(data))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))}
        self.sheets: dict[str, str] = {}   # name -> path inside the zip
        for s in ET.fromstring(self._zip.read("xl/workbook.xml")).find(_M + "sheets"):
            target = rels[s.get(_R + "id")].lstrip("/")
            self.sheets[s.get("name")] = target if target.startswith("xl/") else f"xl/{target}"
        self._strings: list[str] | None = None

    def _shared(self) -> list[str]:
        if self._strings is None:
            self._strings = []
            if "xl/sharedStrings.xml" in self._zip.namelist():
                for si in ET.fromstring(self._zip.read("xl/sharedStrings.xml")).findall(_M + "si"):
                    self._strings.append("".join(t.text or "" for t in si.iter(_M + "t")))
        return self._strings

    def rows(self, sheet: str) -> list[dict[str, str]]:
        """Every row as {column letter: text}; an empty row is {}."""
        strings, out = self._shared(), []
        for _, el in ET.iterparse(self._zip.open(self.sheets[sheet])):
            if el.tag != _M + "row":
                continue
            row = {}
            for c in el.findall(_M + "c"):
                v, kind = c.find(_M + "v"), c.get("t")
                if kind == "inlineStr":
                    row[re.match(r"[A-Z]+", c.get("r"))[0]] = "".join(t.text or "" for t in c.iter(_M + "t"))
                elif v is not None and v.text is not None:
                    row[re.match(r"[A-Z]+", c.get("r"))[0]] = strings[int(v.text)] if kind == "s" else v.text
            out.append(row)
            el.clear()
        return out
