"""Deploy-time fetch: copy the public data files from the engine repo's releases into the site folder.

GitHub release assets send no CORS header (docs/research/probes-v2.md, probe 2), so the browser cannot read them. Pages
serves static files, so `sp` ships them with the site. Public market data only. A file that cannot be fetched is skipped
and the copy already in the site (if any) stays, so a bad night never blanks a screen."""
import io
import json
import tarfile
from pathlib import Path

ENGINE_REPO = "gunjannandy/stockpilot-engine"
BASE = "https://github.com/{repo}/releases/download/"

# release asset -> path in the site
SINGLE = (("data-latest/search-index.json", "search/index.json"), ("data-latest/universe.json", "screen/universe.json"))
# release asset -> folder in the site. `nested` False: the tar.gz already holds that folder (funds/..., chart/...);
# True: the tar.gz holds files at its root (the weekly facts pack `./SYMBOL.json`), which belong inside the folder.
TARS = (("data-latest/funds.tar.gz", "funds", False), ("data-latest/chart.tar.gz", "chart", False), ("data-latest/stock-facts.tar.gz", "stock", True))


def _write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _unpack(blob: bytes, out: Path):
    out = out.resolve()
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
        for m in t.getmembers():
            target = (out / m.name).resolve()
            if m.isfile() and out in target.parents:        # no links, no paths that leave the site
                _write(target, t.extractfile(m).read())


def fetch_into(site, repo=ENGINE_REPO, fetch=None, mechanical_days=None) -> list[str]:
    """Returns the site paths written. `mechanical_days`: the ISO dates of the mechanical files to ship (default: the last three days)."""
    if fetch is None:
        from stockpilot.sources.http import fetch as _f
        fetch = _f
    site, base, done = Path(site), BASE.format(repo=repo), []
    if mechanical_days is None:
        from datetime import date, timedelta
        mechanical_days = [str(date.today() - timedelta(days=n)) for n in range(3)]
    singles = list(SINGLE) + [(f"mechanical-latest/{d}.json", f"mechanical/{d}.json") for d in mechanical_days]
    for asset, rel in singles:
        try:
            blob = fetch(base + asset)
        except Exception:  # noqa: BLE001  a night's network trouble must not stop the deploy
            continue
        if blob:
            _write(site / rel, blob)
            done.append(rel)
    for asset, folder, nested in TARS:
        try:
            blob = fetch(base + asset)
        except Exception:  # noqa: BLE001
            continue
        if blob:
            _unpack(blob, site / folder if nested else site)
            done.append(f"{folder}/index.json")
    return done


def main(argv=None):
    """python -m stockpilot.sources.public_files SITE_DIR [REPO]"""
    import sys
    args = argv or sys.argv[1:]
    done = fetch_into(args[0], *(args[1:2]))
    print(json.dumps({"fetched": done}))


if __name__ == "__main__":
    main()
