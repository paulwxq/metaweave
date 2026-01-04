from pathlib import Path

import pytest

from metaweave.utils.file_utils import clear_dir_contents


def test_clear_dir_contents_removes_files_and_subdirs(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()

    (target / "a.txt").write_text("a", encoding="utf-8")
    sub = target / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("b", encoding="utf-8")

    clear_dir_contents(target)

    assert target.exists()
    assert list(target.iterdir()) == []


def test_clear_dir_contents_creates_directory_if_missing(tmp_path: Path):
    target = tmp_path / "missing"
    assert not target.exists()

    clear_dir_contents(target)

    assert target.exists()
    assert target.is_dir()
