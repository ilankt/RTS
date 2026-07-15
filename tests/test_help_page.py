"""Help page (§ Help): generator produces a valid self-contained page, and
the launcher opens it without ever raising."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def test_generator_builds_self_contained_page(tmp_path):
    from tools.generate_help import build

    out = build(str(tmp_path / "help.html"))
    html = open(out, encoding="utf-8").read()

    # self-contained: no external resource references
    assert 'src="http' not in html and 'href="http' not in html
    assert "<!doctype html>" in html and "</html>" in html
    # all four sections present
    for anchor in ("basics", "units", "buildings", "economy", "controls"):
        assert f'id="{anchor}"' in html
    # every buildable unit shows an animated GIF, buildings show stills
    assert html.count("data:image/gif") >= 6      # 6 buildable units
    assert html.count('<article class="card"') >= 15  # units + buildings
    # stats come from the live data, not hardcoded
    assert "Battering Ram" in html and "Forged Blades" in html
    # no leaked format placeholders
    import re
    assert not re.search(r"\{[a-z_]+\}", html)


def test_launcher_never_raises(monkeypatch):
    import core.help_launcher as launcher

    opened = {}
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.setdefault("url", url))
    # the committed page exists after a normal build; force the happy path
    monkeypatch.setattr(launcher.os.path, "exists", lambda p: True)
    assert launcher.open_help() is True
    assert opened["url"].startswith("file:")


def test_launcher_swallows_failure(monkeypatch):
    import core.help_launcher as launcher

    def boom(url):
        raise RuntimeError("no browser")

    monkeypatch.setattr(launcher.os.path, "exists", lambda p: True)
    monkeypatch.setattr(launcher.webbrowser, "open", boom)
    assert launcher.open_help() is False  # never propagates
