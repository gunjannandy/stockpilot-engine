"""Copy the code, and only the code, to the public engine repo after a privacy scan.

The scan never prints a matched string: a finding names the file, the line and the rule.
The deny list of names lives outside git (default data/publish-deny.txt); without it nothing is published.
"""
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Folders and files that may leave. Everything else (docs, ops, config secrets, data) stays private.
ALLOW_DIRS = ("src", "tests", "web", "schemas", "prompts", "scripts", "probes")  # probes: probe-t2 runs probes/py on the public repo
ALLOW_FILES = (
    "pyproject.toml", "uv.lock", "README.public.md", "GLOSSARY.md",
    "config/stockpilot.yaml", "config/fund_house_sources.json", "config/levels_calibration.json", "config/price_flag_reasons.json", "config/profile.example.yaml",
)
# The public repo's workflows are kept here and land in .github/workflows/ on the other side.
PUBLIC_WORKFLOWS = "ops/public/workflows"

PRIVATE_DIRS = {"private", "data", "archive", "vault", "vault-identity", "node_modules", ".wrangler"}
PRIVATE_SUFFIXES = (".age", ".db", ".sqlite", ".pem", ".key", ".p12")
PRIVATE_NAMES = (".env",)

PAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Za-z0-9])")
DUMMY_PAN = re.compile(r"^(ABCDE1234F|([A-Z])\2{4}(\d)\3{3}\2)$")  # ABCDE1234F, AAAAA0000A, BBBBB1111B: obvious placeholders
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
# Placeholder domains and the public sender addresses of brokers and agencies: no person in them.
SAFE_EMAIL = re.compile(r"^(noreply|no-reply)@|@(example\.com|[\w.-]*\.test|users\.noreply\.github\.com|anthropic\.com|google\.com|smallcase\.com|cdslstatement\.com|([\w-]+\.)?zerodha\.net)$", re.I)
# A long digit run only counts where the line says what it is: market ids and timestamps are not accounts.
ACCOUNT = re.compile(r"(?<![\w.\-])\d{9,18}(?![\w.\-])")
ACCOUNT_CONTEXT = re.compile(r"\baccounts?\b|\ba/c\b|\bacct\b|\bfolio\b|client[ _-]?id|\bdemat\b|\bdp[ _-]?id|\bifsc\b|\biban\b|\bbo[ _-]?id\b", re.I)

DEFAULT_DENY_FILE = "data/publish-deny.txt"


@dataclass(frozen=True)
class Finding:
    path: str
    line: int  # 0 for a path-level finding
    rule: str


class Blocked(Exception):
    def __init__(self, message, findings=()):
        super().__init__(message)
        self.findings = list(findings)


def candidates(root: Path):
    """Every file that would leave, as (relative posix path, public path)."""
    root = Path(root)
    out = []
    for d in ALLOW_DIRS:
        base = root / d
        if base.is_dir():
            out += [(p.relative_to(root).as_posix(),) * 2 for p in sorted(base.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    for f in ALLOW_FILES:
        if (root / f).is_file():
            out.append((f, f))
    wf = root / PUBLIC_WORKFLOWS
    if wf.is_dir():
        out += [(p.relative_to(root).as_posix(), f".github/workflows/{p.name}") for p in sorted(wf.glob("*.yml"))]
    return out


def _private_path(rel):
    parts = rel.split("/")
    if any(p in PRIVATE_DIRS for p in parts[:-1]):
        return True
    name = parts[-1]
    return name in PRIVATE_NAMES or name.startswith(".env.") or name.endswith(PRIVATE_SUFFIXES)


def load_deny_terms(path):
    path = Path(path)
    if not path.is_file():
        return None
    lines = (ln.strip() for ln in path.read_text().splitlines())
    return [ln for ln in lines if ln and not ln.startswith("#")]


def scan(root, deny_terms):
    root = Path(root)
    terms = [t.lower() for t in deny_terms]
    found = []
    for rel, _ in candidates(root):
        if _private_path(rel):
            found.append(Finding(rel, 0, "private-path"))
            continue
        raw = (root / rel).read_bytes()
        if b"\0" in raw:
            continue
        for n, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
            low = line.lower()
            if any(not DUMMY_PAN.match(m.group(0)) for m in PAN.finditer(line)):
                found.append(Finding(rel, n, "pan"))
            if any(not SAFE_EMAIL.search(m.group(0)) for m in EMAIL.finditer(line)):
                found.append(Finding(rel, n, "email"))
            if ACCOUNT.search(line) and ACCOUNT_CONTEXT.search(line):
                found.append(Finding(rel, n, "account-number"))
            if any(t in low for t in terms):
                found.append(Finding(rel, n, "deny-term"))
    return found


def export(root, dest, deny_terms):
    """Scan, then copy. Blocks (and writes nothing) on any finding."""
    root, dest = Path(root), Path(dest)
    found = scan(root, deny_terms)
    if found:
        raise Blocked(f"privacy scan blocked the copy: {len(found)} finding(s)", found)
    copied = []
    for rel, public in candidates(root):
        target = dest / public
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
        copied.append(public)
    return copied


def _git(*args, cwd):
    return subprocess.run(
        ["git", "-c", "user.name=stockpilot-publisher", "-c", "user.email=noreply@users.noreply.github.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def run(root, remote, deny_file=DEFAULT_DENY_FILE, workdir=None, message="code copy", branch="main", ref=None):
    """Publish one snapshot of the code to `remote`. The first publish starts a fresh history; later ones add a snapshot commit.

    With `ref` (for example "origin/main") the snapshot is that commit, not the working tree.
    """
    root = Path(root)
    deny = load_deny_terms(deny_file if Path(deny_file).is_absolute() else root / deny_file)
    if deny is None:
        raise Blocked("no deny list found: create the private deny list before publishing")
    work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="sp-publish-"))
    work.mkdir(parents=True, exist_ok=True)
    if ref:
        snap = work / "snapshot"
        shutil.rmtree(snap, ignore_errors=True)
        snap.mkdir()
        archive = subprocess.run(["git", "archive", ref], cwd=root, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(snap)], input=archive, check=True)
        root = snap
    clone = work / "public"
    if clone.exists():
        shutil.rmtree(clone)
    work.mkdir(parents=True, exist_ok=True)
    exists = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", remote, branch], capture_output=True).returncode == 0
    if exists:
        _git("clone", "--quiet", "--depth", "1", "--branch", branch, remote, str(clone), cwd=work)
        for child in clone.iterdir():
            if child.name != ".git":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    else:
        clone.mkdir()
        _git("init", "--quiet", "-b", branch, cwd=clone)
        _git("remote", "add", "origin", remote, cwd=clone)
    try:
        export(root, clone, deny)  # scans before writing; a block leaves the clone empty and pushes nothing
    except Blocked:
        shutil.rmtree(work, ignore_errors=True)
        raise
    _git("add", "-A", cwd=clone)
    if exists and not _git("status", "--porcelain", cwd=clone):
        return False
    _git("commit", "--quiet", "-m", message, cwd=clone)
    _git("push", "--quiet", "origin", branch, cwd=clone)
    return True
