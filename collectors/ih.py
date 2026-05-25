from __future__ import annotations

import os
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from services.normalizer import Notice, make_notice
from utils.date import parse_date


BASE_PAGES = [
    ("분양", "https://www.ih.co.kr/main/sale_lease/board/house_notice.jsp"),
    ("임대", "https://www.ih.co.kr/main/sale_lease/notice.jsp"),
]
HEADERS = {"User-Agent": "housing-notice-alert/1.0"}


def _collect_page(default_type: str, url: str, timeout: int) -> list[Notice]:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    notices: list[Notice] = []
    content = soup.find("main") or soup.find(id="contents") or soup
    for anchor in content.find_all("a", href=True):
        title = anchor.get_text(" ", strip=True)
        if not title:
            continue
        if title.startswith("Image:") or "다운받기" in title:
            continue
        if title in {"첫 페이지", "이전 페이지 그룹", "다음 페이지 그룹", "마지막 페이지"}:
            continue
        container = anchor.find_parent("li") or anchor.find_parent("tr") or anchor.parent
        text = container.get_text(" ", strip=True) if container else title
        date_value = parse_date(text)
        if not date_value:
            continue
        attachment = None
        for file_link in container.find_all("a", href=True) if container else []:
            label = file_link.get_text(" ", strip=True)
            if "다운받기" in label or "pdf" in label.lower() or "hwp" in label.lower():
                attachment = urljoin(url, file_link["href"])
                break
        notices.append(
            make_notice(
                provider="iH",
                region="인천",
                notice_type=default_type,
                title=title,
                notice_date=date_value,
                status=None,
                url=urljoin(url, anchor["href"]),
                attachment_url=attachment,
            )
        )
    return notices


def collect_ih() -> list[Notice]:
    timeout = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
    notices: list[Notice] = []
    for default_type, url in BASE_PAGES:
        notices.extend(_collect_page(default_type, url, timeout))
    deduped = {notice.content_hash: notice for notice in notices}
    return list(deduped.values())
