from __future__ import annotations

import hashlib


def content_hash(provider: str, title: str, notice_date: str | None, url: str) -> str:
    raw_key = f"{provider}|{title}|{notice_date or ''}|{url}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
