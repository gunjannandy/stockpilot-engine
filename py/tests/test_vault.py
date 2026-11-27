import subprocess

import pytest

from stockpilot import vault

PASSWORD = "correct horse"


@pytest.fixture(scope="module")
def keys():
    # Sealing the identity costs one password key-derivation, so do it once for the module.
    return vault.create_keys(PASSWORD)


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(path)], check=True)
    return str(path)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / "private" / "docs").mkdir(parents=True)
    (root / "private" / "profile.yaml").write_text("age: 28\n")
    (root / "private" / "docs" / "form16.pdf").write_bytes(b"%PDF fake \x00\x01")
    (root / ".env").write_text("VAULT_PASSWORD=pw\n")
    return root


def test_restore_returns_exactly_what_was_pushed(keys, project, remote, tmp_path):
    vault.push(project, remote, keys, ["private", ".env", "data/missing.duckdb"])
    dest = tmp_path / "restored"
    vault.restore(remote, PASSWORD, dest)
    assert (dest / "private" / "profile.yaml").read_text() == "age: 28\n"
    assert (dest / "private" / "docs" / "form16.pdf").read_bytes() == b"%PDF fake \x00\x01"
    assert (dest / ".env").read_text() == "VAULT_PASSWORD=pw\n"


def test_wrong_password_is_refused(keys, project, remote, tmp_path):
    vault.push(project, remote, keys, ["private"])
    with pytest.raises(vault.VaultError):
        vault.restore(remote, "wrong", tmp_path / "restored")


def test_vault_branch_keeps_only_the_newest_copy(keys, project, remote, tmp_path):
    vault.push(project, remote, keys, ["private"])
    (project / "private" / "profile.yaml").write_text("age: 29\n")
    vault.push(project, remote, keys, ["private"])
    count = subprocess.run(["git", "--git-dir", remote, "rev-list", "--count", "vault"],
                           capture_output=True, text=True, check=True).stdout.strip()
    assert count == "1"
    vault.restore(remote, PASSWORD, tmp_path / "restored")
    assert (tmp_path / "restored" / "private" / "profile.yaml").read_text() == "age: 29\n"
