"""Fund holdings: a fund house's monthly portfolio sheet becomes dated ISIN rows; overlap with a list of held ISINs is a
pure function (the real match runs privately). Fixtures use invented funds and ISINs."""
import io
import json
import zipfile
from datetime import date
from xml.sax.saxutils import escape

from stockpilot.sources import fund_holdings as fh, fund_universe as fu


def xlsx(sheets: dict[str, list[list]]) -> bytes:
    """A minimal workbook with inline strings, enough for stockpilot.trades.xlsx.Workbook."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' +
                   "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(sheets, 1)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
                   "".join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1)) + "</Relationships>")
        for i, rows in enumerate(sheets.values(), 1):
            body = ""
            for r, row in enumerate(rows, 1):
                cells = "".join(f'<c r="{chr(65 + c)}{r}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'
                                for c, v in enumerate(row) if v is not None)
                body += f'<row r="{r}">{cells}</row>'
            z.writestr(f"xl/worksheets/sheet{i}.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + body + "</sheetData></worksheet>")
    return buf.getvalue()


HEADER = ["Name of the Instrument", "ISIN", "Rating / Industry", "Quantity", "Market/Fair Value (Rs. in Lacs)", "% to NAV"]
ALPHA = [["Alpha Mutual Fund"], ["Alpha Flexi Cap Fund"], ["Monthly Portfolio Statement as on 31st October 2026"], [],
         HEADER,
         ["Equity & Equity related"],
         ["Aaa Bank Ltd", "INE000A01011", "Banks", "1,000", "2,500.50", "6.25%"],
         ["Bbb Motors Ltd", "INE000B01012", "Auto", "500", "1000", "2.5"],
         ["Ccc Pharma Ltd", "INE000C01013", "Pharma", "250", "500", "1.25"],
         ["Total", None, None, None, "4000.50", "10"],
         ["Debt"],
         ["7.1% GOI 2034", "IN0020240001", "Sovereign", "10", "100", "0.25"],
         ["Net receivables", None, None, None, "50", "0.1"]]
BETA = [["Beta Mutual Fund"], ["Beta Large Cap Fund"], ["Portfolio as at 31/10/2026"], HEADER,
        ["Aaa Bank Ltd", "INE000A01011", "Banks", "10", "80", "8"], ["Ddd Steel Ltd", "INE000D01014", "Metals", "10", "20", "2"]]


def test_a_sheet_becomes_dated_isin_rows_and_skips_totals_and_blank_isins():
    p = fh.parse_sheet(__import__("stockpilot.trades.xlsx", fromlist=["x"]).Workbook(xlsx({"S1": ALPHA})).rows("S1"))
    assert p["title"] == "Alpha Flexi Cap Fund" and p["amc"] == "Alpha Mutual Fund"
    assert p["as_of"] == date(2026, 10, 31)
    assert [r["isin"] for r in p["rows"]] == ["INE000A01011", "INE000B01012", "INE000C01013", "IN0020240001"]
    first = p["rows"][0]
    assert first == {"isin": "INE000A01011", "name": "Aaa Bank Ltd", "quantity": 1000.0, "value_lakh": 2500.5, "pct_nav": 6.25}


def test_percent_signs_commas_and_slash_dates_are_read():
    p = fh.parse_sheet(__import__("stockpilot.trades.xlsx", fromlist=["x"]).Workbook(xlsx({"S": BETA})).rows("S"))
    assert p["as_of"] == date(2026, 10, 31) and p["rows"][1]["pct_nav"] == 2.0


def test_a_sheet_without_an_isin_column_is_not_a_portfolio():
    assert fh.parse_sheet([{"A": "Notes"}, {"A": "Index"}]) is None


def test_workbook_gives_one_portfolio_per_portfolio_sheet():
    ps = fh.parse_workbook(xlsx({"Index": [["Contents"]], "A": ALPHA, "B": BETA}))
    assert [p["title"] for p in ps] == ["Alpha Flexi Cap Fund", "Beta Large Cap Fund"]


def test_csv_portfolio_is_read_too():
    csv = "Alpha Mutual Fund\nAlpha Flexi Cap Fund\nAs on 31-Oct-2026\nName,ISIN,Quantity,% to NAV\nAaa Bank Ltd,INE000A01011,\"1,000\",6.25\n"
    ps = fh.parse_workbook(csv.encode(), "alpha.csv")
    assert ps[0]["rows"][0]["isin"] == "INE000A01011" and ps[0]["as_of"] == date(2026, 10, 31)


def funds():
    def s(code, amc, name):
        return dict(code=code, amc=amc, category="Equity Scheme - Flexi Cap Fund", name=name, plan="Direct", option="Growth",
                    label="Growth", nav=1.0, isin=None, day=None)
    return fu.group_funds([s(1, "Alpha Mutual Fund", "Alpha Flexi Cap Fund - Direct Plan - Growth"),
                           s(2, "Alpha Mutual Fund", "Alpha Flexi Cap Fund - Regular Plan - Growth"),
                           s(3, "Beta Mutual Fund", "Beta Large Cap Fund - Direct Plan - Growth"),
                           s(4, "Alpha Mutual Fund", "Alpha Gilt Fund - Direct Plan - Growth")])


def test_a_portfolio_is_matched_to_the_fund_of_its_house_by_name():
    fs = funds()
    p = fh.parse_workbook(xlsx({"A": ALPHA}))[0]
    assert fh.match_fund(p, fs)["name"] == "Alpha Flexi Cap Fund"
    p["title"] = "Totally Unknown Fund"
    assert fh.match_fund(p, fs) is None


def test_a_name_in_another_house_is_not_matched():
    fs = funds()
    p = fh.parse_workbook(xlsx({"A": ALPHA}))[0]
    p["amc"] = "Beta Mutual Fund"
    assert fh.match_fund(p, fs) is None


def test_overlap_counts_shared_stocks_and_their_weight_in_the_fund():
    p = fh.parse_workbook(xlsx({"A": ALPHA}))[0]
    o = fh.overlap(p["rows"], {"INE000A01011", "INE000C01013", "INE999Z01019"})
    assert o["shared"] == [{"isin": "INE000A01011", "name": "Aaa Bank Ltd", "pct_nav": 6.25},
                           {"isin": "INE000C01013", "name": "Ccc Pharma Ltd", "pct_nav": 1.25}]
    assert o["pct_nav"] == 7.5 and o["n_shared"] == 2 and o["n_held"] == 3
    assert o["pct_of_fund_stocks"] == round(100 * 2 / 3, 1)      # 2 of the fund's 3 equities


def test_overlap_with_nothing_held_is_zero_not_an_error():
    o = fh.overlap([], set())
    assert o["pct_nav"] == 0 and o["n_shared"] == 0 and o["shared"] == []


def test_load_house_reads_each_file_and_reports_what_it_could_not():
    blobs = {"u1": xlsx({"A": ALPHA}), "u2": None}
    got = fh.load_house(lambda u: blobs[u], ["u1", "u2"], funds())
    assert len(got["matched"]) == 1 and got["matched"][0]["fund_id"] == next(f["id"] for f in funds() if f["name"] == "Alpha Flexi Cap Fund")
    assert got["unmatched"] == [] and got["failed"] == ["u2"]


def test_load_house_lists_portfolios_it_could_not_match():
    got = fh.load_house(lambda u: xlsx({"B": BETA}), ["u"], [f for f in funds() if f["amc"] == "Alpha Mutual Fund"])
    assert got["matched"] == [] and got["unmatched"] == ["Beta Large Cap Fund"]


def test_publish_writes_dated_per_fund_files_and_a_house_report(tmp_path):
    fs = funds()
    a = fh.load_house(lambda u: xlsx({"A": ALPHA}), ["u"], fs)
    b = fh.load_house(lambda u: xlsx({"B": BETA}), ["u"], fs)
    report = fh.publish({"Alpha Mutual Fund": a, "Beta Mutual Fund": b, "Gamma Mutual Fund": {"matched": [], "unmatched": [], "failed": ["g"]}},
                        tmp_path, "2026-11-25T10:00:00+05:30")
    idx = json.loads((tmp_path / "fund_holdings" / "index.json").read_text())
    assert report == idx["counts"]
    assert report["houses_loaded"] == 2 and report["houses_total"] == 3 and report["funds"] == 2
    assert idx["houses"]["Gamma Mutual Fund"] == {"funds": 0, "as_of": None, "failed_files": 1}
    assert idx["houses"]["Alpha Mutual Fund"]["as_of"] == "2026-10-31"
    fund = json.loads((tmp_path / "fund_holdings" / f"{a['matched'][0]['fund_id']}.json").read_text())
    assert fund["as_of"] == "2026-10-31" and fund["holdings"][0]["isin"] == "INE000A01011" and fund["amc"] == "Alpha Mutual Fund"


def test_ten_houses_are_listed_with_their_amfi_names():
    assert len(fh.HOUSES) == 10 and len(set(fh.HOUSES)) == 10 and all(h.endswith("Mutual Fund") for h in fh.HOUSES)
