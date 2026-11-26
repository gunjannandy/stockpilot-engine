"""The deploy-time fetch: public release files are copied into the site so Pages serves them (release assets have no CORS)."""
import gzip
import io
import json
import tarfile

from stockpilot.sources import public_files


def _tar(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name); info.size = len(data); t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def make_fetch(assets):
    calls = []
    def fetch(url, **kw):
        calls.append(url)
        return assets.get(url.split("/releases/download/")[1])
    fetch.calls = calls
    return fetch


def test_lays_files_at_the_contract_paths(tmp_path):
    assets = {
        "data-latest/search-index.json": b'{"entries":[]}',
        "data-latest/universe.json": b'{"n":0}',
        "data-latest/funds.tar.gz": _tar({"funds/index.json": b"{}", "funds/f1.json": b"{}", "../evil.json": b"x"}),
        "mechanical-latest/2026-11-25.json": b'{"results":[]}',
        "mechanical-latest/2026-11-24.json": b'{"results":[1]}',
    }
    fetch = make_fetch(assets)
    done = public_files.fetch_into(tmp_path, "o/r", fetch=fetch, mechanical_days=["2026-11-25"])
    assert json.loads((tmp_path / "search/index.json").read_text()) == {"entries": []}
    assert (tmp_path / "screen/universe.json").exists()
    assert (tmp_path / "funds/index.json").exists() and (tmp_path / "funds/f1.json").exists()
    assert not (tmp_path.parent / "evil.json").exists()
    assert (tmp_path / "mechanical/2026-11-25.json").exists()
    assert {"search/index.json", "screen/universe.json", "funds/index.json"} <= set(done)


def test_a_missing_asset_is_skipped_not_fatal(tmp_path):
    done = public_files.fetch_into(tmp_path, "o/r", fetch=make_fetch({}), mechanical_days=[])
    assert done == [] and not (tmp_path / "search").exists()


def test_a_failed_download_keeps_the_file_already_in_the_site(tmp_path):
    (tmp_path / "search").mkdir(); (tmp_path / "search/index.json").write_text("old")
    def boom(url, **kw): raise OSError("network")
    public_files.fetch_into(tmp_path, "o/r", fetch=boom, mechanical_days=[])
    assert (tmp_path / "search/index.json").read_text() == "old"
