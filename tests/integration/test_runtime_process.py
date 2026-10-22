from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

_SERVE_COMMAND = [sys.executable, "-c", "from versarr.cli import app; app()", "serve"]
_STARTUP_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class _Deployment:
    root: Path
    state_dir: Path

    def env(self, port: int) -> dict[str, str]:
        return {
            **os.environ,
            "VERSARR_LIBRARY_ROOTS": f'["{self.root}"]',
            "VERSARR_STATE_DIR": str(self.state_dir),
            "VERSARR_SQLITE_PATH": str(self.state_dir / "versarr.db"),
            "VERSARR_HTTP_BIND_HOST": "127.0.0.1",
            "VERSARR_HTTP_BIND_PORT": str(port),
            "VERSARR_PROVIDER_BASE_URL": "http://127.0.0.1:9",
        }


@pytest.fixture
def deployment(tmp_path: Path) -> _Deployment:
    root = tmp_path / "music"
    state_dir = tmp_path / "state"
    root.mkdir()
    state_dir.mkdir()
    return _Deployment(root=root, state_dir=state_dir)


@pytest.fixture
def spawned() -> Iterator[list[subprocess.Popen[str]]]:
    processes: list[subprocess.Popen[str]] = []
    yield processes
    for process in processes:
        if process.poll() is None:
            process.kill()
        if process.stdout is not None and not process.stdout.closed:
            process.communicate()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _spawn(deployment: _Deployment, spawned: list[subprocess.Popen[str]]) -> tuple[subprocess.Popen[str], int]:
    port = _free_port()
    process = subprocess.Popen(
        _SERVE_COMMAND,
        env=deployment.env(port),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    spawned.append(process)
    return process, port


def _wait_until_ready(process: subprocess.Popen[str], port: int) -> None:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        assert process.poll() is None, "server exited before becoming ready"
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.2)
    pytest.fail("server did not become ready in time")


def test_second_instance_fails_cleanly_while_first_keeps_running(deployment: _Deployment, spawned: list[subprocess.Popen[str]]) -> None:
    first, first_port = _spawn(deployment, spawned)
    _wait_until_ready(first, first_port)

    second, _ = _spawn(deployment, spawned)
    output, _ = second.communicate(timeout=_STARTUP_TIMEOUT_SECONDS)

    assert second.returncode != 0
    assert "instance_lock_held" in output
    assert "lock already held" in output
    assert first.poll() is None
    with urllib.request.urlopen(f"http://127.0.0.1:{first_port}/ready", timeout=2) as response:
        assert response.status == 200


def test_lock_is_released_when_holder_is_killed(deployment: _Deployment, spawned: list[subprocess.Popen[str]]) -> None:
    first, first_port = _spawn(deployment, spawned)
    _wait_until_ready(first, first_port)
    first.kill()
    first.communicate()

    second, second_port = _spawn(deployment, spawned)

    _wait_until_ready(second, second_port)
