"""인천도시공사(iH) 분양/임대 공고 수집기.

원본은 일단 동작하지만 두 가지 한계가 있어 개선합니다:

1. **페이지 1만 수집**: 페이지당 10건이라 LOOKBACK_DAYS=90이면 누락 가능.
   iH는 `/main/bbs/bbsMsgList.do?...&pgno=N` 형태의 GET으로 페이지네이션을 지원합니다.
2. **셀렉터가 느슨함**: `content.find_all("a")`로 모든 a를 훑어 데이터 셀과
   네비게이션을 구분하기 어려웠습니다. 실제 마크업
   `.board_list ul.generalList > li` 단위로 정확히 잡습니다.
"""

from __future__ import annotations

import os
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from services.normalizer import Notice, make_notice
from utils.date import parse_date
from utils.logger import get_logger


# (공고 종류, 첫 페이지 URL, 2페이지 이후 URL 템플릿)
BOARDS: list[tuple[str, str, str]] = [
    (
        "분양",
        "https://www.ih.co.kr/main/sale_lease/board/house_notice.jsp",
        "https://www.ih.co.kr/main/bbs/bbsMsgList.do?cate1=a&bcd=sale_lease&pgno={page}",
    ),
    (
        "임대",
        "https://www.ih.co.kr/main/sale_lease/notice.jsp",
        "https://www.ih.co.kr/main/bbs/bbsMsgList.do?cate1=general&bcd=notice&pgdiv=general&pgno={page}",
    ),
]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}
MAX_PAGES = 3  # 페이지당 10건 -> 게시판당 최대 30건 (LOOKBACK 90일 충분)


def _parse_items(html: str, page_url: str, default_type: str) -> list[Notice]:
    soup = BeautifulSoup(html, "html.parser")
    notices: list[Notice] = []

    items = soup.select(".board_list ul.generalList > li")
    if not items:
        # 페이지 구조가 약간 다를 수 있어 fallback
        items = soup.select("ul.generalList > li")

    for li in items:
        title_anchor = li.select_one("p.title a")
        if not title_anchor:
            continue
        title = title_anchor.get_text(" ", strip=True)
        if not title:
            continue
        detail_href = title_anchor.get("href", "").strip()
        if not detail_href:
            continue
        detail_url = urljoin(page_url, detail_href)

        # writer_info 안의 메타데이터(공고종류, 작성일, 작성자) 추출
        info_lis = li.select(".writer_info li")
        notice_type = default_type
        notice_date: str | None = None
        for info in info_lis:
            title_attr = (info.get("title") or "").strip()
            text_value = info.get_text(" ", strip=True)
            if title_attr == "공지사항" and text_value:
                notice_type = text_value
            elif title_attr == "작성일" and text_value:
                notice_date = parse_date(text_value) or notice_date

        # 첨부파일 (li.file 안의 a)
        attachment_url = None
        file_anchor = li.select_one("li.file a[href]")
        if file_anchor:
            attachment_url = urljoin(page_url, file_anchor["href"])

        notices.append(
            make_notice(
                provider="iH",
                region="인천",
                notice_type=notice_type,
                title=title,
                notice_date=notice_date,
                status=None,
                url=detail_url,
                attachment_url=attachment_url,
            )
        )
    return notices


def _collect_board(default_type: str, first_url: str, page_template: str, timeout: int) -> list[Notice]:
    logger = get_logger(__name__)
    session = requests.Session()
    session.headers.update(HEADERS)

    collected: list[Notice] = []
    seen_hashes: set[str] = set()

    for page in range(1, MAX_PAGES + 1):
        url = first_url if page == 1 else page_template.format(page=page)
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("iH %s page=%s request failed: %s", default_type, page, exc)
            break

        page_notices = _parse_items(response.text, url, default_type)
        if not page_notices:
            logger.info("iH %s page=%s: empty", default_type, page)
            break

        new_count = 0
        for notice in page_notices:
            if notice.content_hash not in seen_hashes:
                seen_hashes.add(notice.content_hash)
                collected.append(notice)
                new_count += 1

        logger.info(
            "iH %s page=%s items=%s new=%s total=%s",
            default_type,
            page,
            len(page_notices),
            new_count,
            len(collected),
        )

        if new_count == 0:
            break
        if len(page_notices) < 10:
            break

    return collected


def collect_ih() -> list[Notice]:
    timeout = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
    notices: list[Notice] = []
    for default_type, first_url, template in BOARDS:
        notices.extend(_collect_board(default_type, first_url, template, timeout))
    # 게시판 간 중복(드물지만 가능) 제거
    deduped = {notice.content_hash: notice for notice in notices}
    return list(deduped.values())
