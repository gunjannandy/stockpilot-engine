"""SKELETON-3: the web finds screens, panes and words files by folder; no area edits main.tsx."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web/src"


def test_main_discovers_panes_and_words_by_glob_and_imports_no_area():
    main = (WEB / "main.tsx").read_text()
    assert 'import.meta.glob("./panes/*/index.tsx"' in main
    assert 'import.meta.glob("./words/*.json"' in main
    area_imports = re.findall(r'from "\./(?:panes|words)/', main)
    assert area_imports == [], "main.tsx names an area, so adding one would edit it"


def test_every_pane_ships_english_and_bengali_words():
    for pane in (WEB / "panes").iterdir():
        if not pane.is_dir():
            continue
        for lang in ("en", "bn"):
            assert (WEB / "words" / f"{pane.name}.{lang}.json").is_file(), f"{pane.name} has no {lang} words"
