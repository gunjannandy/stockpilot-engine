"""The vault: every private file, encrypted, kept as a single commit on a git branch.

Pushing uses only a public key, so it is fast and needs no password. The matching private key
travels with the vault, sealed with the owner's password (age passphrase mode), so the repo plus the
password is enough to restore anywhere. Password key-derivation (scrypt) needs ~256 MB of RAM, so it
runs only in create_keys() and restore(), never on a routine push.
"""
import io
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pyrage
from pyrage import passphrase, x25519

BRANCH = "vault"
BLOB, SEALED_KEY = "vault.tar.gz.age", "identity.age"
README = ("# stockpilot vault\n\nEncrypted private data. Restore with `sp vault restore` and the vault password.\n"
          "By hand: `age -d identity.age > id.txt` (asks for the password), then\n"
          "`age -d -i id.txt vault.tar.gz.age | tar xz`, then delete id.txt.\n")


class VaultError(RuntimeError):
    pass


@dataclass(frozen=True)
class Keys:
    recipient: str          # public key, safe to commit
    sealed_identity: bytes  # private key encrypted with the vault password, safe to commit

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "vault.pub").write_text(self.recipient + "\n")
        (folder / "vault-identity.age").write_bytes(self.sealed_identity)

    @classmethod
    def load(cls, folder: Path) -> "Keys":
        return cls((folder / "vault.pub").read_text().strip(), (folder / "vault-identity.age").read_bytes())


def create_keys(password: str) -> Keys:
    identity = x25519.Identity.generate()
    return Keys(str(identity.to_public()), passphrase.encrypt(str(identity).encode(), password))


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def push(root: Path | str, remote: str, keys: Keys, paths: list[str]) -> None:
    root = Path(root)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in paths:
            if (root / rel).exists():
                tar.add(root / rel, arcname=rel)
    sealed = pyrage.encrypt(buf.getvalue(), [x25519.Recipient.from_str(keys.recipient)])
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / BLOB).write_bytes(sealed)
        (Path(tmp) / SEALED_KEY).write_bytes(keys.sealed_identity)
        (Path(tmp) / "README.md").write_text(README)
        _git(tmp, "init", "-q", "-b", BRANCH)
        _git(tmp, "add", ".")
        _git(tmp, "-c", "user.name=stockpilot", "-c", "user.email=stockpilot@localhost",
             "commit", "-q", "-m", "vault")
        _git(tmp, "push", "-q", "--force", remote, f"{BRANCH}:{BRANCH}")


def restore(remote: str, password: str, dest: Path | str) -> None:
    dest = Path(dest)
    with tempfile.TemporaryDirectory() as tmp:
        _git(tmp, "clone", "-q", "--depth", "1", "-b", BRANCH, remote, "v")
        sealed = (Path(tmp) / "v" / BLOB).read_bytes()
        sealed_identity = (Path(tmp) / "v" / SEALED_KEY).read_bytes()
    try:
        identity = x25519.Identity.from_str(passphrase.decrypt(sealed_identity, password).decode())
    except Exception as err:  # pyrage raises its own DecryptError
        raise VaultError("Could not open the vault: wrong password or a damaged vault.") from err
    data = pyrage.decrypt(sealed, [identity])
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(dest, filter="data")


MIN_PASSWORD = 12


def rekey(remote: str, old_password: str, new_password: str, paths: list[str]) -> Keys:
    """Re-lock the vault: open it with the old password, make a new key pair sealed with the new password, push one new commit,
    then check that only the new password opens it. The old password is not re-used for anything. Returns the new keys; the
    caller saves them to config/ (and the market backup is written again so its recipient is the new key). A wrong old password
    or a short new one raises before anything is pushed."""
    if len(new_password) < MIN_PASSWORD:
        raise VaultError(f"The new vault password must be at least {MIN_PASSWORD} characters.")
    with tempfile.TemporaryDirectory() as tmp:
        restore(remote, old_password, tmp)
        keys = create_keys(new_password)
        push(tmp, remote, keys, paths)
    with tempfile.TemporaryDirectory() as check:
        restore(remote, new_password, check)           # the new password opens it
    with tempfile.TemporaryDirectory() as leftover:
        try:
            restore(remote, old_password, leftover)
        except VaultError:
            return keys
    raise VaultError("The vault still opens with the old password; it was not re-locked.")
