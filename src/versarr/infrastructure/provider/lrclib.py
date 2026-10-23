from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from time import perf_counter
from typing import Any

import httpx

from versarr.application.contracts import LyricsProvider
from versarr.application.resilient_provider import RequestPacer
from versarr.domain import ProviderResult, ProviderStatus, TrackIdentity, normalize_lookup_text
from versarr.observability import MetricsFacade, get_logger

_MATCH_THRESHOLD = 0.8


class LrclibProvider(LyricsProvider):
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: int,
        user_agent: str,
        metrics: MetricsFacade,
        transport: httpx.AsyncBaseTransport | None = None,
        pacer: RequestPacer | None = None,
        search_fallback: bool = False,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"User-Agent": user_agent},
            transport=transport,
        )
        self._metrics = metrics
        self._pacer = pacer
        self._search_fallback = search_fallback
        self._logger = get_logger("provider", provider="lrclib")

    async def fetch(self, identity: TrackIdentity) -> ProviderResult:
        logger = self._logger.bind(
            track_title=identity.title,
            track_artist=identity.artist,
            track_album=identity.album,
            duration_seconds=identity.duration_seconds,
        )
        logger.info("provider_query_started")
        started = perf_counter()
        try:
            response = await self._get(
                "/api/get",
                {
                    "track_name": identity.title,
                    "artist_name": identity.artist,
                    "album_name": identity.album,
                    "duration": identity.duration_seconds,
                },
            )
        except httpx.HTTPError as error:
            self._metrics.provider_latency_seconds.labels(provider="lrclib").observe(perf_counter() - started)
            return self._network_failure(error, logger)
        self._metrics.provider_latency_seconds.labels(provider="lrclib").observe(perf_counter() - started)

        if response.status_code == 404:
            if self._search_fallback:
                searched = await self._search(identity, logger)
                if searched is not None:
                    return searched
            return self._finish(ProviderStatus.NOT_FOUND, logger, http_status=404)
        failure = self._http_failure(response, logger)
        if failure is not None:
            return failure
        payload = _json_object(response)
        if payload is None:
            return self._finish(
                ProviderStatus.TRANSIENT_FAILURE,
                logger,
                http_status=response.status_code,
                reason="malformed_body",
            )
        return self._result_from_payload(identity, payload, response.status_code, logger)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, str | int | None]) -> httpx.Response:
        if self._pacer is not None:
            await self._pacer.wait()
        return await self._client.get(path, params=params)

    async def _search(self, identity: TrackIdentity, logger: Any) -> ProviderResult | None:
        """Look for the track via /api/search; ``None`` means no acceptable candidate."""
        try:
            response = await self._get(
                "/api/search",
                {"track_name": identity.title, "artist_name": identity.artist},
            )
        except httpx.HTTPError as error:
            return self._network_failure(error, logger)
        failure = self._http_failure(response, logger)
        if failure is not None:
            return failure
        try:
            candidates = response.json()
        except ValueError:
            candidates = None
        if not isinstance(candidates, list):
            return self._finish(
                ProviderStatus.TRANSIENT_FAILURE,
                logger,
                http_status=response.status_code,
                reason="malformed_body",
            )
        usable = [
            candidate for candidate in candidates if isinstance(candidate, dict) and (candidate.get("syncedLyrics") or candidate.get("plainLyrics"))
        ]
        if not usable:
            return None
        best = max(usable, key=lambda candidate: (_score_payload(identity, candidate), bool(candidate.get("syncedLyrics"))))
        if _score_payload(identity, best) < _MATCH_THRESHOLD:
            return None
        logger.info("provider_search_fallback_matched", provider_track_id=best.get("id"))
        return self._result_from_payload(identity, best, response.status_code, logger)

    def _network_failure(self, error: httpx.HTTPError, logger: Any) -> ProviderResult:
        logger.warning(
            "provider_query_failed",
            error_class=type(error).__name__,
            error_message=str(error),
        )
        return self._finish(ProviderStatus.TRANSIENT_FAILURE, logger, log=False)

    def _http_failure(self, response: httpx.Response, logger: Any) -> ProviderResult | None:
        status_code = response.status_code
        if status_code >= 500 or status_code == 429:
            return self._finish(
                ProviderStatus.TRANSIENT_FAILURE,
                logger,
                http_status=status_code,
                retry_after_seconds=_parse_retry_after(response.headers.get("Retry-After")),
            )
        if 400 <= status_code < 500 and status_code != 404:
            return self._finish(ProviderStatus.REJECTED, logger, http_status=status_code)
        return None

    def _result_from_payload(
        self,
        identity: TrackIdentity,
        payload: dict[str, Any],
        http_status: int,
        logger: Any,
    ) -> ProviderResult:
        track_id = str(payload.get("id")) if payload.get("id") is not None else None
        synced = bool(payload.get("syncedLyrics"))
        lyrics_text = payload.get("syncedLyrics") or payload.get("plainLyrics")
        digest = sha256(repr(sorted(payload.items())).encode("utf-8")).hexdigest()
        if not lyrics_text:
            return self._finish(
                ProviderStatus.INVALID_CONTENT,
                logger,
                http_status=http_status,
                provider_track_id=track_id,
                raw_metadata_digest=digest,
            )
        confidence = _score_payload(identity, payload)
        status = ProviderStatus.MATCHED if confidence >= _MATCH_THRESHOLD else ProviderStatus.AMBIGUOUS
        return self._finish(
            status,
            logger,
            http_status=http_status,
            lyrics_text=str(lyrics_text),
            synced=synced,
            provider_track_id=track_id,
            confidence=confidence,
            matched_identity=identity if status == ProviderStatus.MATCHED else None,
            raw_metadata_digest=digest,
        )

    def _finish(
        self,
        status: ProviderStatus,
        logger: Any,
        *,
        http_status: int | None = None,
        log: bool = True,
        reason: str | None = None,
        **result_fields: Any,
    ) -> ProviderResult:
        self._metrics.provider_requests_total.labels(provider="lrclib", status=status).inc()
        if log:
            log_fields: dict[str, Any] = {"status": status, "http_status": http_status}
            if reason is not None:
                log_fields["reason"] = reason
            if "provider_track_id" in result_fields:
                log_fields["provider_track_id"] = result_fields["provider_track_id"]
            if "confidence" in result_fields:
                log_fields["confidence"] = result_fields["confidence"]
            if "synced" in result_fields:
                log_fields["synced"] = result_fields["synced"]
            warn = status in {ProviderStatus.TRANSIENT_FAILURE, ProviderStatus.REJECTED, ProviderStatus.INVALID_CONTENT}
            (logger.warning if warn else logger.info)("provider_query_completed", **log_fields)
        return ProviderResult(
            status=status,
            provider_name="lrclib",
            lyrics_text=result_fields.get("lyrics_text"),
            synced=result_fields.get("synced", False),
            provider_track_id=result_fields.get("provider_track_id"),
            confidence=result_fields.get("confidence", 0.0),
            matched_identity=result_fields.get("matched_identity"),
            raw_metadata_digest=result_fields.get("raw_metadata_digest"),
            retry_after_seconds=result_fields.get("retry_after_seconds"),
        )


def _json_object(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - datetime.now(UTC)).total_seconds(), 0.0)


def _score_payload(identity: TrackIdentity, payload: dict[str, Any]) -> float:
    score = 0.0
    if normalize_lookup_text(str(payload.get("trackName", ""))) == normalize_lookup_text(identity.title):
        score += 0.45
    if normalize_lookup_text(str(payload.get("artistName", ""))) == normalize_lookup_text(identity.artist):
        score += 0.45
    duration = payload.get("duration")
    if identity.duration_seconds is not None and isinstance(duration, int) and abs(duration - identity.duration_seconds) <= 2:
        score += 0.10
    return min(score, 1.0)
