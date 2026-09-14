from __future__ import annotations

import json
import os
import stat
from unittest.mock import patch

import pytest

from metaweave.utils.file_utils import atomic_write_json


def test_atomic_write_json_replaces_target_and_cleans_temp(tmp_path):
    target = tmp_path / "metadata.json"
    target.write_text('{"old": true}', encoding="utf-8")

    atomic_write_json({"new": True}, target)

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    assert list(tmp_path.glob(".metadata.json.*.tmp")) == []


@pytest.mark.skipif(os.name == "nt", reason="Windows 不提供相同的 POSIX 权限语义")
def test_atomic_write_json_uses_readable_mode_for_new_file(tmp_path):
    target = tmp_path / "metadata.json"

    atomic_write_json({"new": True}, target)

    assert stat.S_IMODE(target.stat().st_mode) == 0o644


@pytest.mark.skipif(os.name == "nt", reason="Windows 不提供相同的 POSIX 权限语义")
def test_atomic_write_json_preserves_existing_file_mode(tmp_path):
    target = tmp_path / "metadata.json"
    target.write_text('{"old": true}', encoding="utf-8")
    target.chmod(0o640)

    atomic_write_json({"new": True}, target)

    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_atomic_write_json_cleans_temp_and_preserves_target_on_replace_error(
    tmp_path,
):
    target = tmp_path / "metadata.json"
    original = '{"old": true}'
    target.write_text(original, encoding="utf-8")

    with patch("metaweave.utils.file_utils.os.replace", side_effect=OSError("boom")):
        with pytest.raises(OSError, match="boom"):
            atomic_write_json({"new": True}, target)

    assert target.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".metadata.json.*.tmp")) == []
