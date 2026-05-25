from __future__ import annotations

import os
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from services.normalizer import Notice, make_notice
from utils.date import parse_date


BASE_URLS = [
    ("공공임대", "https://housing.seoul.go.kr/site/main/sh/publicLease/list"),
    ("공공분양", "https://housing.seoul.go.kr/site/main/sh/publicSale/list"),
]
HEADERS = {"User-Agent": "housing-notice-alert/1.0"}


def _parse_listing(html: str, page_url: str, default_type: str) -> list[Notice]:
    soup = BeautifulSoup(html, "html.parser")
    notices: list[Notice] = []

    table = soup.find("table")
    if table:
        for row in table.select("tbody tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            link = row.find("a", href=True)
            if len(cells) < 4 or not link:
                continue
            notice_type = cells[1] if len(cells) > 1 else default_type
            link_text = link.get_text(" ", strip=True)
            title = cells[2] if link_text in {"바로가기", "상세보기"} else link_text or cells[2]
            date_candidates = [parse_date(cell) for cell in cells]
            notice_date = next((item for item in date_candidates if item), None)
            notices.append(
                make_notice(
                    provider="SH",
                    region="서울",
                    notice_type=notice_type or default_type,
                    title=title,
                    notice_date=notice_date,
                    status=" ".join(cell for cell in cells if "모집" in cell) or None,
                    url=urljoin(page_url, link["href"]),
                )
            )
        return notices

    for anchor in soup.find_all("a", href=True):
        title = anchor.get_text(" ", strip=True)
        href = anchor["href"]
        if not title or title in {"바로가기", "SH공사 바로가기 >"}:
            continue
        container = anchor.find_parent(["tr", "li", "div"])
        text = container.get_text(" ", strip=True) if container else title
        if "모집공고" not in text and "공고" not in title:
            continue
        date_value = parse_date(text)
        status = "모집중" if "모집중" in text else "모집마감" if "모집마감" in text else None
        notices.append(
            make_notice(
                provider="SH",
                region="서울",
                notice_type=default_type,
                title=title,
                notice_date=date_value,
                status=status,
                url=urljoin(page_url, href),
            )
        )

    return notices


def collect_sh() -> list[Notice]:
    timeout = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
    session = requests.Session()
    session.headers.update(HEADERS)
    notices: list[Notice] = []
    for default_type, url in BASE_URLS:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        notices.extend(_parse_listing(response.text, url, default_type))
    return notices
