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


# ---- FASTDEPLOY: download and unpack a release asset only when it changed; never rewrite a file that did not ----



def cached_run(tmp_path, assets_by_name, stamps):
    state = tmp_path / "state" / "public-files.json"
    site = tmp_path / "site"
    fetch = make_fetch(assets_by_name)
    done = public_files.fetch_into(site, "o/r", fetch=fetch, mechanical_days=[], state=state,
                                   listing=lambda repo, tag: {n.split("/", 1)[1]: s for n, s in stamps.items() if n.startswith(tag + "/")})
    return site, fetch, done


def test_an_unchanged_asset_is_not_downloaded_again(tmp_path):
    blobs = {"data-latest/chart.tar.gz": _tar({"chart/A.json": b"1", "chart/B.json": b"2"}), "data-latest/search-index.json": b"{}"}
    stamps = {"data-latest/chart.tar.gz": "v1", "data-latest/search-index.json": "s1"}
    site, fetch, first = cached_run(tmp_path, blobs, stamps)
    assert len(fetch.calls) == 2 and (site / "chart/A.json").exists()
    site, fetch, second = cached_run(tmp_path, blobs, stamps)
    assert fetch.calls == [] and (site / "chart/B.json").read_bytes() == b"2"
    assert set(second) >= {"chart/index.json", "search/index.json"}     # same report as a fresh run: callers see what is in the site


def test_a_changed_asset_is_downloaded_and_only_changed_files_are_rewritten(tmp_path):
    blobs = {"data-latest/chart.tar.gz": _tar({"chart/A.json": b"1", "chart/B.json": b"2"})}
    site, _, _ = cached_run(tmp_path, blobs, {"data-latest/chart.tar.gz": "v1"})
    a = site / "chart/A.json"
    before = a.stat().st_ino, a.stat().st_mtime_ns
    blobs = {"data-latest/chart.tar.gz": _tar({"chart/A.json": b"1", "chart/B.json": b"22"})}
    site, fetch, _ = cached_run(tmp_path, blobs, {"data-latest/chart.tar.gz": "v2"})
    assert len(fetch.calls) == 1 and (site / "chart/B.json").read_bytes() == b"22"
    assert (a.stat().st_ino, a.stat().st_mtime_ns) == before            # identical bytes: the file was left alone


def test_an_unchanged_asset_is_fetched_again_when_its_files_are_gone_from_the_site(tmp_path):
    import shutil
    blobs = {"data-latest/chart.tar.gz": _tar({"chart/A.json": b"1"})}
    stamps = {"data-latest/chart.tar.gz": "v1"}
    site, _, _ = cached_run(tmp_path, blobs, stamps)
    shutil.rmtree(site)                                               # a fresh site folder
    site, fetch, _ = cached_run(tmp_path, blobs, stamps)
    assert len(fetch.calls) == 1 and (site / "chart/A.json").exists()


def test_a_failed_download_is_retried_next_time_not_remembered_as_done(tmp_path):
    stamps = {"data-latest/chart.tar.gz": "v1"}
    site, fetch, done = cached_run(tmp_path, {}, stamps)
    assert done == []
    site, fetch, _ = cached_run(tmp_path, {"data-latest/chart.tar.gz": _tar({"chart/A.json": b"1"})}, stamps)
    assert len(fetch.calls) == 1 and (site / "chart/A.json").exists()


def test_when_the_listing_fails_everything_is_downloaded_as_before(tmp_path):
    blobs = {"data-latest/search-index.json": b"{}"}
    fetch = make_fetch(blobs)
    def down(repo, tag): raise OSError("api down")
    done = public_files.fetch_into(tmp_path / "site", "o/r", fetch=fetch, mechanical_days=[], state=tmp_path / "s.json", listing=down)
    assert "search/index.json" in done and len(fetch.calls) >= 1


def test_release_listing_reads_asset_id_time_and_size():
    body = json.dumps({"assets": [{"name": "chart.tar.gz", "id": 7, "updated_at": "2026-11-25T10:00:00Z", "size": 9}]}).encode()
    got = public_files.release_listing("o/r", "data-latest", fetch=lambda url, **kw: body)
    assert got == {"chart.tar.gz": "7:2026-11-25T10:00:00Z:9"}
