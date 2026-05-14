from __future__ import annotations

from hashlib import blake2b


def path_fingerprint(value: str) -> str:
    digest = blake2b(value.encode("utf-8"), digest_size=12)
    return digest.hexdigest()
