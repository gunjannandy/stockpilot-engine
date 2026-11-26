"""Deploy-time fetch: copy the public data files from the engine repo's releases into the site folder.

GitHub release assets send no CORS header (docs/research/probes-v2.md, probe 2), so the browser cannot read them. Pages
serves static files, so `sp` ships them with the site. Public market data only. A file that cannot be fetched is skipped
and the copy already in the site (if any) stays, so a bad night never blanks a screen."""
import io
import json
import tarfile
from pathlib import Path

MISSING = object()          # the release listing was read and does not hold this asset
ENGINE_REPO = "gunjannandy/stockpilot-engine"
BASE = "https://github.com/{repo}/releases/download/"

# release asset -> path in the site
SINGLE = (("data-latest/search-index.json", "search/index.json"), ("data-latest/universe.json", "screen/universe.json"))
# release asset -> folder in the site. `nested` False: the tar.gz already holds that folder (funds/..., chart/...);
# True: the tar.gz holds files at its root (the weekly facts pack `./SYMBOL.json`), which belong inside the folder.
TARS = (("data-latest/funds.tar.gz", "funds", False), ("data-latest/chart.tar.gz", "chart", False), ("data-latest/stock-facts.tar.gz", "stock", True))


def _write(path: Path, data: bytes) -> bool:
    """Write the file unless it already holds exactly these bytes (then it is left alone: no write, same mtime). True if written."""
    try:
        if path.stat().st_size == len(data) and path.read_bytes() == data:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return True


def _unpack(blob: bytes, out: Path) -> list[str]:
    """Extract the regular files, one at a time. Returns their paths relative to `out`."""
    out = out.resolve()
    made = []
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
        for m in t.getmembers():
            target = (out / m.name).resolve()
            if m.isfile() and out in target.parents:        # no links, no paths that leave the site
                _write(target, t.extractfile(m).read())
                made.append(str(target.relative_to(out)))
    return made


def release_listing(repo: str, tag: str, fetch=None) -> dict[str, str]:
    """{asset name: stamp} for one release, from the releases API (one small call). The stamp changes when the asset is uploaded
    again (id, updated_at and size), so equal stamps mean the same file. Raises when the API cannot be read."""
    if fetch is None:
        from stockpilot.sources.http import fetch as _f
        fetch = _f
    body = fetch(f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    return {a["name"]: f"{a['id']}:{a['updated_at']}:{a['size']}" for a in json.loads(body)["assets"]}


def _load(path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError, TypeError):
        return {}


def _save(path, state: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True))
    tmp.replace(path)


def fetch_into(site, repo=ENGINE_REPO, fetch=None, mechanical_days=None, state=None, listing=None) -> list[str]:
    """Returns the site paths written (or already current). `mechanical_days`: the ISO dates of the mechanical files to ship
    (default: the last three days). `state`: a JSON file that remembers each asset's stamp and the files it laid down. With it, an
    asset whose stamp is unchanged and whose files are all still in the site is not downloaded or unpacked again, and a file whose
    bytes did not change is not rewritten. Without it every asset is downloaded, as before. `listing(repo, tag)`: asset stamps
    (default: the releases API); when it cannot be read everything is downloaded."""
    if fetch is None:
        from stockpilot.sources.http import fetch as _f
        fetch = _f
    listing = listing or (lambda r, t: release_listing(r, t))
    site, base, done = Path(site), BASE.format(repo=repo), []
    if mechanical_days is None:
        from datetime import date, timedelta
        mechanical_days = [str(date.today() - timedelta(days=n)) for n in range(3)]
    known = _load(state) if state else {}
    kept, stamps = {}, {}

    def stamp(asset):
        tag, name = asset.split("/", 1)
        if tag not in stamps:
            try:
                stamps[tag] = listing(repo, tag)
            except Exception:  # noqa: BLE001  no listing: download, the old way
                stamps[tag] = None
        return stamps[tag].get(name, MISSING) if stamps[tag] is not None else None

    def current(asset, new):
        old = known.get(asset)
        return bool(state and new and old and old["stamp"] == new and all((site / f).exists() for f in old["files"]))

    def remember(asset, new, files):
        if state and new and files:
            kept[asset] = {"stamp": new, "files": files}

    singles = list(SINGLE) + [(f"mechanical-latest/{d}.json", f"mechanical/{d}.json") for d in mechanical_days]
    for asset, rel in singles:
        new = stamp(asset)
        if new is MISSING:
            continue          # the release does not hold it: nothing to download
        if current(asset, new):
            kept[asset] = known[asset]
            done.append(rel)
            continue
        try:
            blob = fetch(base + asset)
        except Exception:  # noqa: BLE001  a night's network trouble must not stop the deploy
            continue
        if blob:
            _write(site / rel, blob)
            done.append(rel)
            remember(asset, new, [rel])
    for asset, folder, nested in TARS:
        new = stamp(asset)
        if new is MISSING:
            continue          # the release does not hold it: nothing to download
        if current(asset, new):
            kept[asset] = known[asset]
            done.append(f"{folder}/index.json")
            continue
        try:
            blob = fetch(base + asset)
        except Exception:  # noqa: BLE001
            continue
        if blob:
            root = site / folder if nested else site
            made = _unpack(blob, root)
            done.append(f"{folder}/index.json")
            prefix = root.resolve().relative_to(site.resolve()) if nested else Path(".")
            remember(asset, new, [str(prefix / f) for f in made])
    if state:
        _save(state, kept)
    return done


def main(argv=None):
    """python -m stockpilot.sources.public_files SITE_DIR [REPO]"""
    import sys
    args = argv or sys.argv[1:]
    done = fetch_into(args[0], *(args[1:2]))
    print(json.dumps({"fetched": done}))


if __name__ == "__main__":
    main()
