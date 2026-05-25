from __future__ import annotations

import os
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from services.normalizer import Notice, make_notice
from utils.date import parse_date


BASE_URL = "https://apply.gh.or.kr/sb/sr/sr7150/selectPbancRentHouseList.do"
HEADERS = {"User-Agent": "housing-notice-alert/1.0"}


def _row_cells(row) -> list[str]:
    return [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]


def collect_gh() -> list[Notice]:
    timeout = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
    response = requests.get(BASE_URL, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    notices: list[Notice] = []
    rows = soup.select("table tbody tr")
    if rows:
        for row in rows:
            cells = _row_cells(row)
            link = row.find("a", href=True)
            if len(cells) < 7:
                continue
            detail_url = urljoin(BASE_URL, link["href"]) if link else BASE_URL
            notices.append(
                make_notice(
                    provider="GH",
                    region=f"경기 {cells[3]}".strip(),
                    notice_type=cells[1],
                    title=cells[2],
                    notice_date=parse_date(cells[5]),
                    apply_end_date=parse_date(cells[6]),
                    status=cells[7] if len(cells) > 7 else None,
                    url=detail_url,
                )
            )
        return notices

    for anchor in soup.find_all("a", href=True):
        title = anchor.get_text(" ", strip=True)
        if not title or "공고" not in title:
            continue
        container = anchor.find_parent(["tr", "li", "div"])
        text = container.get_text(" ", strip=True) if container else title
        notices.append(
            make_notice(
                provider="GH",
                region="경기",
                notice_type=None,
                title=title,
                notice_date=parse_date(text),
                status="공고중" if "공고중" in text else "접수중" if "접수중" in text else None,
                url=urljoin(BASE_URL, anchor["href"]),
            )
        )
    return notices
