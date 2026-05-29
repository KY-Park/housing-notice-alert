from __future__ import annotations

import os
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from services.normalizer import Notice, make_notice
from utils.date import parse_date
from utils.logger import get_logger


# LH청약플러스 임대/분양 공고문 목록 (서버 렌더링 HTML)
LIST_URL = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do"
INFO_URL = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do"
HEADERS = {"User-Agent": "Mozilla/5.0 (housing-notice-alert)"}


def _detail_url(link) -> str:
    # wrtancInfoBtn: data-id1=panId, id2=ccrCnntSysDsCd, id3=uppAisTpCd, id4=aisTpCd
    pan_id = link.get("data-id1", "")
    ccr = link.get("data-id2", "")
    upp = link.get("data-id3", "")
    ais = link.get("data-id4", "")
    if not pan_id:
        return LIST_URL + "?mi=1026"
    return (
        f"{INFO_URL}?panId={pan_id}&ccrCnntSysDsCd={ccr}"
        f"&uppAisTpCd={upp}&aisTpCd={ais}&mi=1026"
    )


def _row_to_notice(row) -> Notice | None:
    cells = row.find_all("td")
    if len(cells) < 8:
        return None

    link = row.find("a", class_="wrtancInfoBtn")
    if not link:
        return None

    span = link.find("span")
    if span:
        for em in span.find_all("em"):
            em.extract()
        title = span.get_text(" ", strip=True)
    else:
        title = link.get_text(" ", strip=True)
    if not title:
        return None

    notice_type = cells[1].get_text(" ", strip=True)
    region = cells[3].get_text(" ", strip=True)
    notice_date = parse_date(cells[5].get_text(" ", strip=True))
    apply_end = parse_date(cells[6].get_text(" ", strip=True))
    status = cells[7].get_text(" ", strip=True)

    return make_notice(
        provider="LH",
        region=region,
        notice_type=notice_type,
        title=title,
        notice_date=notice_date,
        apply_end_date=apply_end,
        status=status,
        url=_detail_url(link),
    )


def collect_lh() -> list[Notice]:
    logger = get_logger(__name__)
    timeout = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
    lookback_days = int(os.getenv("LOOKBACK_DAYS", "90"))
    max_pages = int(os.getenv("LH_MAX_PAGES", "5"))

    start = (date.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = date.today().strftime("%Y-%m-%d")

    session = requests.Session()
    session.headers.update(HEADERS)

    notices: list[Notice] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        params = {
            "mi": "1026",
            "currPage": str(page),
            "srchY": "Y",
            "startDt": start,
            "endDt": end,
            "schTy": "0",
            "panSs": "",
        }
        response = session.get(LIST_URL, params=params, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        table = soup.find("table")
        rows = table.select("tbody tr") if table else []
        # "등록된 데이터가 없습니다" 한 줄짜리 빈 결과 처리
        if len(rows) <= 1 and (not rows or len(rows[0].find_all("td")) < 8):
            break

        page_count = 0
        for row in rows:
            notice = _row_to_notice(row)
            if notice and notice.content_hash not in seen:
                notices.append(notice)
                seen.add(notice.content_hash)
                page_count += 1

        logger.info("LH page=%s rows=%s new=%s total=%s", page, len(rows), page_count, len(notices))
        # 날짜검색 모드에서 마지막 페이지 이후 동일 결과가 반복되면 중단
        if len(rows) < 50 or page_count == 0:
            break

    return notices
