from __future__ import annotations

from hashlib import sha256
from time import perf_counter

import httpx

from versarr.application.contracts import LyricsProvider
from versarr.domain import ProviderResult, ProviderStatus, TrackIdentity, normalize_lookup_text
from versarr.observability import MetricsFacade, get_logger


class LrclibProvider(LyricsProvider):
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: int,
        user_agent: str,
        metrics: MetricsFacade,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"User-Agent": user_agent},
        )
        self._metrics = metrics
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
            response = await self._client.get(
                "/api/get",
                params={
                    "track_name": identity.title,
                    "artist_name": identity.artist,
                    "album_name": identity.album,
                    "duration": identity.duration_seconds,
                },
            )
        except httpx.HTTPError as error:
            self._metrics.provider_requests_total.labels(
                provider="lrclib",
                status="transient_failure",
            ).inc()
            self._metrics.provider_latency_seconds.labels(provider="lrclib").observe(perf_counter() - started)
            logger.warning(
                "provider_query_failed",
                error_class=type(error).__name__,
                error_message=str(error),
            )
            return ProviderResult(
                status=ProviderStatus.TRANSIENT_FAILURE,
                provider_name="lrclib",
                lyrics_text=None,
                synced=False,
                provider_track_id=None,
                confidence=0.0,
            )

        self._metrics.provider_latency_seconds.labels(provider="lrclib").observe(perf_counter() - started)

        if response.status_code == 404:
            self._metrics.provider_requests_total.labels(
                provider="lrclib",
                status="not_found",
            ).inc()
            logger.info("provider_query_completed", status="not_found", http_status=404)
            return ProviderResult(
                status=ProviderStatus.NOT_FOUND,
                provider_name="lrclib",
                lyrics_text=None,
                synced=False,
                provider_track_id=None,
                confidence=0.0,
            )
        if response.status_code >= 500 or response.status_code == 429:
            self._metrics.provider_requests_total.labels(
                provider="lrclib",
                status="transient_failure",
            ).inc()
            logger.warning(
                "provider_query_completed",
                status="transient_failure",
                http_status=response.status_code,
            )
            return ProviderResult(
                status=ProviderStatus.TRANSIENT_FAILURE,
                provider_name="lrclib",
                lyrics_text=None,
                synced=False,
                provider_track_id=None,
                confidence=0.0,
            )

        payload = response.json()
        synced = bool(payload.get("syncedLyrics"))
        lyrics_text = payload.get("syncedLyrics") or payload.get("plainLyrics")
        if not lyrics_text:
            self._metrics.provider_requests_total.labels(
                provider="lrclib",
                status="invalid_content",
            ).inc()
            logger.warning(
                "provider_query_completed",
                status="invalid_content",
                http_status=response.status_code,
                provider_track_id=str(payload.get("id")) if payload.get("id") is not None else None,
            )
            return ProviderResult(
                status=ProviderStatus.INVALID_CONTENT,
                provider_name="lrclib",
                lyrics_text=None,
                synced=False,
                provider_track_id=str(payload.get("id")) if payload.get("id") is not None else None,
                confidence=0.0,
                raw_metadata_digest=sha256(repr(sorted(payload.items())).encode("utf-8")).hexdigest(),
            )

        confidence = _score_payload(identity, payload)
        status = ProviderStatus.MATCHED if confidence >= 0.8 else ProviderStatus.AMBIGUOUS
        status_label = "matched" if status == ProviderStatus.MATCHED else "ambiguous"
        self._metrics.provider_requests_total.labels(provider="lrclib", status=status_label).inc()
        logger.info(
            "provider_query_completed",
            status=status,
            http_status=response.status_code,
            provider_track_id=str(payload.get("id")) if payload.get("id") is not None else None,
            confidence=confidence,
            synced=synced,
        )
        return ProviderResult(
            status=status,
            provider_name="lrclib",
            lyrics_text=str(lyrics_text),
            synced=synced,
            provider_track_id=str(payload.get("id")) if payload.get("id") is not None else None,
            confidence=confidence,
            matched_identity=identity if status == ProviderStatus.MATCHED else None,
            raw_metadata_digest=sha256(repr(sorted(payload.items())).encode("utf-8")).hexdigest(),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _score_payload(identity: TrackIdentity, payload: dict[str, object]) -> float:
    score = 0.0
    if normalize_lookup_text(str(payload.get("trackName", ""))) == normalize_lookup_text(identity.title):
        score += 0.45
    if normalize_lookup_text(str(payload.get("artistName", ""))) == normalize_lookup_text(identity.artist):
        score += 0.45
    duration = payload.get("duration")
    if identity.duration_seconds is not None and isinstance(duration, int) and abs(duration - identity.duration_seconds) <= 2:
        score += 0.10
    return min(score, 1.0)
