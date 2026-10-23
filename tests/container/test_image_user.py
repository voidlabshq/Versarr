from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.container

_IMAGE = os.environ.get("VERSARR_TEST_IMAGE")

if not _IMAGE or shutil.which("docker") is None:
    pytest.skip("set VERSARR_TEST_IMAGE and install docker to run container tests", allow_module_level=True)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", "run", "--rm", *args], capture_output=True, text=True, check=False, timeout=120)


def test_image_runs_as_uid_gid_1000() -> None:
    result = _run(str(_IMAGE), "sh", "-c", "id -u; id -g")

    assert result.stdout.split() == ["1000", "1000"]


def test_state_bind_mount_owned_by_1000_is_writable(tmp_path: Path) -> None:
    if os.getuid() != 1000:
        pytest.skip("host user is not uid 1000")
    result = _run("-v", f"{tmp_path}:/state", str(_IMAGE), "sh", "-c", "touch /state/versarr.lock && echo writable")

    assert result.stdout.strip() == "writable"


def test_explicit_user_override_still_works(tmp_path: Path) -> None:
    result = _run("--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{tmp_path}:/state", str(_IMAGE), "sh", "-c", "touch /state/x && echo writable")

    assert result.stdout.strip() == "writable"
