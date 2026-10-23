from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from versarr.application.resilient_provider import RequestPacer
from versarr.domain import ProviderStatus, TrackIdentity
from versarr.infrastructure.provider import LrclibProvider

_IDENTITY = TrackIdentity(
    title="Song",
    artist="Artist",
    album="Album",
    album_artist=None,
    track_number=1,
    disc_number=1,
    duration_seconds=180,
    release_year=2024,
)


def _provider(
    handler: httpx.MockTransport | None = None,
    *,
    response: httpx.Response | None = None,
    search_fallback: bool = False,
    pacer: RequestPacer | None = None,
) -> LrclibProvider:
    transport = handler or httpx.MockTransport(lambda request: response or httpx.Response(500))
    return LrclibProvider(
        base_url="https://lrclib.test",
        timeout_seconds=1,
        user_agent="Versarr/test",
        metrics=MagicMock(),
        transport=transport,
        search_fallback=search_fallback,
        pacer=pacer,
    )


_MATCH_PAYLOAD = {
    "id": 7,
    "trackName": "Song",
    "artistName": "Artist",
    "duration": 180,
    "syncedLyrics": "[00:01.00]hello",
}


@pytest.mark.asyncio
async def test_matching_payload_is_matched() -> None:
    result = await _provider(response=httpx.Response(200, json=_MATCH_PAYLOAD)).fetch(_IDENTITY)

    assert result.status == ProviderStatus.MATCHED
    assert result.synced
    assert result.provider_track_id == "7"


@pytest.mark.asyncio
async def test_mismatched_payload_is_ambiguous() -> None:
    payload = {**_MATCH_PAYLOAD, "trackName": "Other", "artistName": "Someone"}

    result = await _provider(response=httpx.Response(200, json=payload)).fetch(_IDENTITY)

    assert result.status == ProviderStatus.AMBIGUOUS


@pytest.mark.asyncio
async def test_payload_without_lyrics_is_invalid_content() -> None:
    result = await _provider(response=httpx.Response(200, json={"id": 1, "trackName": "Song"})).fetch(_IDENTITY)

    assert result.status == ProviderStatus.INVALID_CONTENT


@pytest.mark.asyncio
async def test_not_found() -> None:
    result = await _provider(response=httpx.Response(404, json={"message": "not found"})).fetch(_IDENTITY)

    assert result.status == ProviderStatus.NOT_FOUND


@pytest.mark.parametrize("status_code", [429, 500, 502, 503])
@pytest.mark.asyncio
async def test_rate_limit_and_server_errors_are_transient(status_code: int) -> None:
    result = await _provider(response=httpx.Response(status_code)).fetch(_IDENTITY)

    assert result.status == ProviderStatus.TRANSIENT_FAILURE


@pytest.mark.parametrize("status_code", [400, 401, 403, 410])
@pytest.mark.asyncio
async def test_other_client_errors_are_rejected_not_cooled_down_as_content(status_code: int) -> None:
    result = await _provider(response=httpx.Response(status_code, json={"message": "nope"})).fetch(_IDENTITY)

    assert result.status == ProviderStatus.REJECTED


@pytest.mark.parametrize("body", [b"<html>bad gateway</html>", b"[]", b"null"])
@pytest.mark.asyncio
async def test_malformed_success_body_is_transient(body: bytes) -> None:
    result = await _provider(response=httpx.Response(200, content=body)).fetch(_IDENTITY)

    assert result.status == ProviderStatus.TRANSIENT_FAILURE


@pytest.mark.asyncio
async def test_network_error_is_transient() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    result = await _provider(httpx.MockTransport(fail)).fetch(_IDENTITY)

    assert result.status == ProviderStatus.TRANSIENT_FAILURE


@pytest.mark.parametrize(("header", "expected"), [("120", 120.0), ("0", 0.0), ("garbage", None)])
@pytest.mark.asyncio
async def test_retry_after_header_is_parsed(header: str, expected: float | None) -> None:
    result = await _provider(response=httpx.Response(429, headers={"Retry-After": header})).fetch(_IDENTITY)

    assert result.status == ProviderStatus.TRANSIENT_FAILURE
    assert result.retry_after_seconds == expected


def _routing_transport(get: httpx.Response, search: httpx.Response | None, calls: list[str] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.path)
        if request.url.path == "/api/get":
            return get
        assert search is not None, "search must not be called"
        return search

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_search_fallback_finds_track_when_get_misses() -> None:
    calls: list[str] = []
    transport = _routing_transport(
        httpx.Response(404),
        httpx.Response(
            200,
            json=[
                {"id": 1, "trackName": "Other", "artistName": "Else", "duration": 10, "plainLyrics": "no"},
                {**_MATCH_PAYLOAD, "id": 9, "duration": 181},
            ],
        ),
        calls,
    )

    result = await _provider(transport, search_fallback=True).fetch(_IDENTITY)

    assert result.status == ProviderStatus.MATCHED
    assert result.provider_track_id == "9"
    assert calls == ["/api/get", "/api/search"]


@pytest.mark.asyncio
async def test_search_fallback_prefers_synced_lyrics_among_equal_matches() -> None:
    plain = {**_MATCH_PAYLOAD, "id": 1, "syncedLyrics": None, "plainLyrics": "plain"}
    synced = {**_MATCH_PAYLOAD, "id": 2}
    transport = _routing_transport(httpx.Response(404), httpx.Response(200, json=[plain, synced]))

    result = await _provider(transport, search_fallback=True).fetch(_IDENTITY)

    assert result.provider_track_id == "2"
    assert result.synced


@pytest.mark.asyncio
async def test_search_fallback_without_acceptable_candidate_is_not_found() -> None:
    weak = {"id": 1, "trackName": "Another Song", "artistName": "Artist", "duration": 180, "plainLyrics": "x"}
    transport = _routing_transport(httpx.Response(404), httpx.Response(200, json=[weak]))

    result = await _provider(transport, search_fallback=True).fetch(_IDENTITY)

    assert result.status == ProviderStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_search_failure_is_transient() -> None:
    transport = _routing_transport(httpx.Response(404), httpx.Response(429))

    result = await _provider(transport, search_fallback=True).fetch(_IDENTITY)

    assert result.status == ProviderStatus.TRANSIENT_FAILURE


@pytest.mark.asyncio
async def test_search_is_skipped_when_fallback_disabled() -> None:
    transport = _routing_transport(httpx.Response(404), None)

    result = await _provider(transport, search_fallback=False).fetch(_IDENTITY)

    assert result.status == ProviderStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_every_http_request_goes_through_the_pacer() -> None:
    pacer = MagicMock()
    pacer.wait = _async_counter()
    transport = _routing_transport(httpx.Response(404), httpx.Response(200, json=[]))

    await _provider(transport, search_fallback=True, pacer=pacer).fetch(_IDENTITY)

    assert pacer.wait.calls == 2


def _async_counter() -> object:
    class _Counter:
        calls = 0

        async def __call__(self) -> None:
            self.calls += 1

    return _Counter()
