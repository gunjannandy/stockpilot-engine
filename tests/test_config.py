import pytest

from stockpilot import config


def write(root, yaml_text, env_text=""):
    (root / "config").mkdir()
    (root / "config" / "stockpilot.yaml").write_text(yaml_text)
    (root / ".env").write_text(env_text)


def test_reads_settings_and_secrets(tmp_path, monkeypatch):
    monkeypatch.delenv("VAULT_PASSWORD", raising=False)
    write(tmp_path, "runner: claude\nuniverse:\n  liquidity_floor_cr: 1\n", "VAULT_PASSWORD=hunter2\n")
    cfg = config.load(tmp_path)
    assert cfg.get("runner") == "claude"
    assert cfg.get("universe.liquidity_floor_cr") == 1
    assert cfg.secret("VAULT_PASSWORD") == "hunter2"


def test_names_every_missing_secret_at_once(tmp_path, monkeypatch):
    for name in ("VAULT_PASSWORD", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    write(tmp_path, "secrets:\n  VAULT_PASSWORD: the owner's vault password\n  CLOUDFLARE_API_TOKEN: from the Cloudflare dashboard\n")
    cfg = config.load(tmp_path)
    with pytest.raises(config.MissingSecrets) as err:
        cfg.require("VAULT_PASSWORD", "CLOUDFLARE_API_TOKEN")
    msg = str(err.value)
    assert "VAULT_PASSWORD (the owner's vault password)" in msg
    assert "CLOUDFLARE_API_TOKEN (from the Cloudflare dashboard)" in msg


def test_environment_overrides_env_file(tmp_path, monkeypatch):
    write(tmp_path, "{}\n", "VAULT_PASSWORD=from-file\n")
    monkeypatch.setenv("VAULT_PASSWORD", "from-env")
    assert config.load(tmp_path).secret("VAULT_PASSWORD") == "from-env"
