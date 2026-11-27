"""Lane V3: re-lock the vault with the new password, the nightly whole-database backup, and the restore proof.
Temp databases, temp keys, a local bare git repo as the remote; no network."""
import json
import subprocess

import pytest

from stockpilot import backup, store, vault

OLD, NEW = "old pass", "a much longer new vault password"


@pytest.fixture(scope="module")
def old_keys():
    return vault.create_keys(OLD)


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(path)], check=True)
    return str(path)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / "private").mkdir(parents=True)
    (root / "private" / "profile.yaml").write_text("age: 28\n")
    (root / ".env").write_text("X=1\n")
    return root


@pytest.fixture
def db(tmp_path):
    d = store.open(tmp_path / "live.duckdb")
    for sym in ("ACME", "BOLT"):
        d.execute("insert into trades (trade_key, source, kind, symbol, side, trade_date, quantity, price) "
                  "values (?, 'tradebook', 'stock', ?, 'buy', '2026-01-02', 5, 100.5)", [f"k-{sym}", sym])
        d.execute("insert into lots (kind, symbol, acquired_on, quantity, cost_per_unit) values ('stock', ?, '2026-01-02', 5, 100.5)", [sym])
    d.execute("insert into watchlist (symbol, exchange, added_by) values ('ACME', 'NSE', 'owner')")
    d.execute("insert into feedback (author, kind, text) values ('owner', 'want', 'Bigger fonts')")
    d.execute("insert into prices values ('2026-11-20', 'ACME', 'NSE', 'EQ', 1, 2, 0.5, 1.5, 1.1, 100, 1e6, 9)")
    return d


def commits(remote):
    return int(subprocess.run(["git", "--git-dir", remote, "rev-list", "--count", "vault"],
                              capture_output=True, text=True, check=True).stdout)


# --- rekey ------------------------------------------------------------------------------------------------
def test_after_a_rekey_only_the_new_password_opens_the_vault(old_keys, project, remote, tmp_path):
    vault.push(project, remote, old_keys, ["private", ".env"])
    new_keys = vault.rekey(remote, OLD, NEW, ["private", ".env"])
    with pytest.raises(vault.VaultError):
        vault.restore(remote, OLD, tmp_path / "old")
    vault.restore(remote, NEW, tmp_path / "new")
    assert (tmp_path / "new" / "private" / "profile.yaml").read_text() == "age: 28\n"
    assert new_keys.recipient != old_keys.recipient          # a fresh key pair, not the old one re-sealed
    assert commits(remote) == 1


def test_a_rekey_with_the_wrong_old_password_changes_nothing(old_keys, project, remote, tmp_path):
    vault.push(project, remote, old_keys, ["private"])
    before = subprocess.run(["git", "--git-dir", remote, "rev-parse", "vault"], capture_output=True, text=True, check=True).stdout
    with pytest.raises(vault.VaultError):
        vault.rekey(remote, "nope", NEW, ["private"])
    after = subprocess.run(["git", "--git-dir", remote, "rev-parse", "vault"], capture_output=True, text=True, check=True).stdout
    assert before == after
    vault.restore(remote, OLD, tmp_path / "still")


def test_a_new_password_that_is_too_short_is_refused(old_keys, project, remote):
    vault.push(project, remote, old_keys, ["private"])
    with pytest.raises(vault.VaultError, match="12"):
        vault.rekey(remote, OLD, "short", ["private"])


# --- nightly backup and the restore proof --------------------------------------------------------------------
def test_nightly_backup_is_one_encrypted_commit_with_a_manifest(db, old_keys, project, remote):
    out = backup.nightly(db, project, remote, old_keys)
    assert commits(remote) == 1
    manifest = json.loads((project / "private" / "state" / "manifest.json").read_text())
    assert manifest["tables"]["trades"]["rows"] == 2 and out["tables"]["trades"] == 2
    assert "Bigger fonts" not in json.dumps(manifest)
    backup.nightly(db, project, remote, old_keys)
    assert commits(remote) == 1                                   # replaced, not stacked


def test_the_restore_proof_matches_every_checksum(db, old_keys, project, remote, tmp_path):
    backup.nightly(db, project, remote, old_keys)
    proof = backup.prove_restore(remote, OLD, tmp_path / "scratch")
    assert proof["ok"] is True
    assert proof["tables"]["trades"] == 2 and proof["tables"]["lots"] == 2
    assert not (tmp_path / "scratch").exists() or not any((tmp_path / "scratch").glob("**/*.parquet"))   # no plaintext left


def test_the_restore_proof_fails_when_a_table_was_damaged(db, old_keys, project, remote, tmp_path):
    backup.nightly(db, project, remote, old_keys)
    manifest = project / "private" / "state" / "manifest.json"
    data = json.loads(manifest.read_text())
    data["tables"]["lots"]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(data))
    vault.push(project, remote, old_keys, ["private", ".env"])        # a backup whose manifest disagrees with its tables
    with pytest.raises(backup.BackupError, match="lots"):
        backup.prove_restore(remote, OLD, tmp_path / "scratch")


def test_the_restore_proof_needs_the_right_password(db, old_keys, project, remote, tmp_path):
    backup.nightly(db, project, remote, old_keys)
    with pytest.raises(vault.VaultError):
        backup.prove_restore(remote, "wrong", tmp_path / "scratch")
