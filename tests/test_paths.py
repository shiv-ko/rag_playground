from pathlib import Path

from src.utils.paths import ROOT, to_repo_relative


def test_root_is_repo_root():
    assert (ROOT / "CLAUDE.md").exists()


def test_to_repo_relative_inside():
    p = ROOT / "data" / "raw" / "x.txt"
    assert to_repo_relative(p) == "data/raw/x.txt"


def test_to_repo_relative_outside_returns_str():
    assert to_repo_relative(Path("/etc/hosts")) == "/etc/hosts"
