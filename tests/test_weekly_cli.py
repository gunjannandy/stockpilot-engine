from stockpilot import cli, store


def test_sp_weekly_runs_green_on_an_empty_store_and_writes_the_pack(tmp_path, capsys):
    store.open(tmp_path / "data" / "stockpilot.duckdb").close()
    assert cli.main(["--root", str(tmp_path), "weekly", "--analyse-only", "--date", "2026-11-21"]) == 0
    assert "'status': 'ok'" in capsys.readouterr().out
    assert (tmp_path / "data" / "tax_pack" / "2026-27" / "summary.json").exists()


def test_private_profile_feeds_target_losses_and_2018_prices(tmp_path):
    from stockpilot import weekly
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "profile.yaml").write_text(
        "target_allocation: {stocks: 0.6, equity_funds: 0.4}\n"
        "carried_losses: [{year: 2024, stcl: 5000, ltcl: 0}]\ntaxable_income_ex_gains: 1500000\n")
    (tmp_path / "private" / "fmv_2018.csv").write_text("isin,price\nINE000A01010,150\n")
    got = weekly.load_private(tmp_path)
    assert got["target"]["stocks"] == 0.6 and got["carried"][0]["stcl"] == 5000
    assert got["slab_income"] == 1_500_000 and got["fmv_2018"] == {"INE000A01010": 150.0}
