from __future__ import annotations

import re
from datetime import datetime


DATE_PATTERNS = [
    r"(20\d{2})[-.\/년]\s*(\d{1,2})[-.\/월]\s*(\d{1,2})",
    r"(\d{2})[.\/]\s*(\d{1,2})[.\/]\s*(\d{1,2})",
]


def parse_date(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text)
        if not match:
            continue
        year, month, day = match.groups()
        if len(year) == 2:
            year = f"20{year}"
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat()
        except ValueError:
            return None
    return None
