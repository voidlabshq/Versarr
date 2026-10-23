from __future__ import annotations

from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from versarr.interfaces.http import build_http_app
from versarr.observability import MetricsFacade


@dataclass
class _Readiness:
    ready: bool = True


@dataclass
class _Status:
    readiness: _Readiness = field(default_factory=_Readiness)
    healthy: bool = True


class _FakeRuntime:
    def __init__(self) -> None:
        self.status = _Status()
        self.metrics = MetricsFacade()
        self.supervisor_healthy = True
        self.events: list[str] = []

    @property
    def healthy(self) -> bool:
        return self.status.healthy and self.supervisor_healthy

    async def start(self) -> None:
        self.events.append("start")

    async def stop(self) -> None:
        self.events.append("stop")


def test_health_reports_ok_and_degraded() -> None:
    runtime = _FakeRuntime()
    with TestClient(build_http_app(runtime)) as client:  # type: ignore[arg-type]
        assert client.get("/health").json() == {"status": "ok"}

        runtime.supervisor_healthy = False

        assert client.get("/health").json() == {"status": "degraded"}


def test_ready_requires_readiness_and_health() -> None:
    runtime = _FakeRuntime()
    with TestClient(build_http_app(runtime)) as client:  # type: ignore[arg-type]
        assert client.get("/ready").status_code == 200

        runtime.status.readiness.ready = False
        not_ready = client.get("/ready")
        runtime.status.readiness.ready = True
        runtime.supervisor_healthy = False
        unhealthy = client.get("/ready")

    assert not_ready.status_code == 503
    assert not_ready.json() == {"status": "not_ready"}
    assert unhealthy.status_code == 503


def test_metrics_endpoint_serves_prometheus_text() -> None:
    with TestClient(build_http_app(_FakeRuntime())) as client:  # type: ignore[arg-type]
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "versarr_jobs_enqueued_total" in response.text
    assert "python_gc_objects_collected_total" in response.text


def test_lifespan_starts_and_stops_the_runtime() -> None:
    runtime = _FakeRuntime()
    with TestClient(build_http_app(runtime)):  # type: ignore[arg-type]
        assert runtime.events == ["start"]

    assert runtime.events == ["start", "stop"]


def test_metrics_facades_do_not_share_a_registry() -> None:
    first = MetricsFacade()
    second = MetricsFacade()

    first.jobs_enqueued_total.labels(trigger="watcher").inc()

    assert first.registry is not second.registry
