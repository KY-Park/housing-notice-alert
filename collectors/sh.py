from __future__ import annotations

import os

import requests
from bs4 import BeautifulSoup

from services.normalizer import Notice, make_notice
from utils.date import parse_date
from utils.logger import get_logger


# SH 공식 공고 게시판 (SH소식 > 공고 및 공지 > 전체)
LIST_URL = "https://www.i-sh.co.kr/main/lay2/program/S1T294C295/www/brd/m_241/list.do"
VIEW_URL = "https://www.i-sh.co.kr/main/lay2/program/S1T294C295/www/brd/m_241/view.do"
# 모집공고 카테고리 비트마스크 (주택분양/임대/매입 등 전체)
MULTI_ITM_SEQS = "1,2,4,8,16,32,64,128,256,512,1024"
HEADERS = {"User-Agent": "Mozilla/5.0 (housing-notice-alert)"}


def _row_to_notice(row) -> Notice | None:
    cells = row.find_all("td")
    if len(cells) < 5:
        return None

    link = row.find("a", onclick=True)
    if not link:
        return None

    # 제목: <span> 안의 텍스트에서 'NEW', 'n일전' 같은 꼬리표 제거
    span = link.find("span")
    if span:
        for em in span.find_all("em"):
            em.extract()
        title = span.get_text(" ", strip=True)
    else:
        title = link.get_text(" ", strip=True)
    title = title.replace("NEW", "").strip()
    if not title:
        return None

    # onclick="javascript:getDetailView('304864');..." 에서 seq 추출
    onclick = link.get("onclick", "")
    seq = onclick.split("'")[1] if "'" in onclick else ""
    url = f"{VIEW_URL}?seq={seq}" if seq else LIST_URL

    notice_date = parse_date(cells[3].get_text(" ", strip=True))

    return make_notice(
        provider="SH",
        region="서울",
        notice_type=None,
        title=title,
        notice_date=notice_date,
        status=None,
        url=url,
        attachment_url=None,
    )


def collect_sh() -> list[Notice]:
    logger = get_logger(__name__)
    timeout = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
    max_pages = int(os.getenv("SH_MAX_PAGES", "5"))

    session = requests.Session()
    session.headers.update(HEADERS)

    notices: list[Notice] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        params = {
            "multi_itm_seqs": MULTI_ITM_SEQS,
            "isRecrnoti": "Y",  # 모집공고만
            "page": str(page),
        }
        response = session.get(LIST_URL, params=params, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        target = None
        for table in soup.find_all("table"):
            if "getDetailView" in str(table):
                target = table
                break
        if target is None:
            break

        rows = target.select("tbody tr")
        page_count = 0
        for row in rows:
            notice = _row_to_notice(row)
            if notice and notice.content_hash not in seen:
                notices.append(notice)
                seen.add(notice.content_hash)
                page_count += 1

        logger.info("SH page=%s rows=%s new=%s total=%s", page, len(rows), page_count, len(notices))
        if page_count == 0:
            break

    return notices
