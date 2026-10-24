from pathlib import Path

from app.components import shared


def test_theme_is_light_and_high_contrast():
    cfg = (Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml").read_text()
    assert 'base = "light"' in cfg and 'textColor = "#000000"' in cfg and "maxUploadSize" in cfg
    assert "font-weight:700" in shared._CSS and "keji-result" in shared._CSS
    assert "#E2E2E2" not in shared._CSS and "#080809" not in shared._CSS     # the old dark colours are gone
