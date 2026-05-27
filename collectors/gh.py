"""경기주택도시공사(GH) 임대주택 공고 수집기.

이 사이트는 두 가지 문제 때문에 기본 requests로는 막힙니다:

1. **SSL handshake 실패**: 서버가 OpenSSL의 최근 보안 레벨에서 거부하는
   약한 cipher / 구버전 TLS만 지원합니다. `SECLEVEL=0` 컨텍스트로 우회합니다.
2. **상세 페이지가 POST 전용**: 제목 anchor가 `href="#a"` 이고 JS가
   `bbsSearchFrm`을 `selectPbancDetailView.do`로 submit 합니다. 알림 용도에는
   목록 페이지 URL + pbancNo fragment 로 충분합니다.
"""

from __future__ import annotations

import os
import re
import ssl
from typing import Iterable
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from services.normalizer import Notice, make_notice
from utils.date import parse_date
from utils.logger import get_logger


BASE_URL = "https://apply.gh.or.kr/sb/sr/sr7150/selectPbancRentHouseList.do"
HEADERS = {
    # housing-notice-alert/1.0 같은 비표준 UA를 차단하는 경우가 있어 일반 브라우저 UA 사용
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}
MAX_PAGES = 5  # 한 페이지당 10건 -> 최대 50건 확인 (LOOKBACK_DAYS=90 커버에 충분)
DATE_RE = re.compile(r"\b(\d{4}[-./]\d{1,2}[-./]\d{1,2})\b")


class _LegacySSLAdapter(HTTPAdapter):
    """약한 cipher / 구버전 TLS를 허용하는 HTTP adapter.

    경기주택도시공사 서버는 신형 OpenSSL의 기본 보안 레벨(SECLEVEL=2)에서는
    handshake 실패가 발생합니다. SECLEVEL=0으로 낮춰 연결을 성립시킵니다.
    """

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=0")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def _make_session() -> requests.Session:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session = requests.Session()
    session.mount("https://", _LegacySSLAdapter())
    session.headers.update(HEADERS)
    return session


def _first_date_in(text: str) -> str | None:
    match = DATE_RE.search(text or "")
    return parse_date(match.group(1)) if match else None


def _extract_status(text: str) -> str | None:
    for keyword in ("접수중", "공고중", "접수마감", "공고마감", "정정공고"):
        if keyword in text:
            return keyword
    return None


def _parse_rows(rows: Iterable) -> list[Notice]:
    notices: list[Notice] = []
    for row in rows:
        tds = row.find_all("td")
        cells = [td.get_text(" ", strip=True) for td in tds]
        if len(cells) < 3:
            continue

        # 셀 구조 (HTML 마크업이 일부 닫히지 않아 셀이 합쳐져 보일 수 있어
        # 안전하게 정규식과 fallback을 함께 사용한다):
        #   [0] 번호 [1] 공고종류 [2] 제목 [3] 지역(+나머지 뭉침)
        #   [4] 첨부 [5] 공고일 [6] 마감일(+뭉침) [7] 상태(+뭉침)
        notice_type = cells[1] if len(cells) > 1 else None
        title = cells[2] if len(cells) > 2 else None
        if not title:
            continue

        region_cell = cells[3] if len(cells) > 3 else ""
        # "광주시 2026-05-08 2026-05-22 접수마감 ..." 처럼 뭉쳐 있으니 첫 토큰만
        region_token = region_cell.split()[0] if region_cell else ""
        region = f"경기 {region_token}".strip() if region_token else "경기"

        notice_date = (
            parse_date(cells[5]) if len(cells) > 5 else None
        ) or _first_date_in(region_cell)

        end_cell = cells[6] if len(cells) > 6 else ""
        apply_end = _first_date_in(end_cell)

        status_cell = cells[7] if len(cells) > 7 else end_cell
        status = _extract_status(status_cell)

        # 상세는 POST 기반이라 직접 GET 불가. 목록 URL에 pbancNo를 fragment로
        # 붙여서 (a) 사용자가 클릭하면 목록 페이지로 이동 (b) content_hash가
        # 공고별로 unique 해지도록 한다.
        anchor = row.select_one("a[data-pbancNo], button[data-pbancNo]")
        pbanc_no = anchor.get("data-pbancno") if anchor else None
        url = f"{BASE_URL}#pbancNo={pbanc_no}" if pbanc_no else BASE_URL

        notices.append(
            make_notice(
                provider="GH",
                region=region,
                notice_type=notice_type,
                title=title,
                notice_date=notice_date,
                apply_end_date=apply_end,
                status=status,
                url=url,
            )
        )
    return notices


def collect_gh() -> list[Notice]:
    logger = get_logger(__name__)
    timeout = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))

    session = _make_session()
    notices: list[Notice] = []
    seen_hashes: set[str] = set()

    for page in range(1, MAX_PAGES + 1):
        try:
            # 첫 페이지는 GET, 이후 페이지는 POST(form: pageIndex)로 페이지네이션
            if page == 1:
                response = session.get(BASE_URL, timeout=timeout, verify=False)
            else:
                response = session.post(
                    BASE_URL,
                    data={"pageIndex": str(page)},
                    timeout=timeout,
                    verify=False,
                )
            response.raise_for_status()
        except requests.exceptions.SSLError as exc:
            logger.warning("GH SSL error on page %s: %s", page, exc)
            break
        except requests.RequestException as exc:
            logger.warning("GH request failed on page %s: %s", page, exc)
            break

        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("table.board_tbl tbody tr")
        if not rows:
            # 페이지가 비었거나 구조 변경 - 종료
            logger.info("GH page %s: no rows", page)
            break

        page_notices = _parse_rows(rows)

        # 중복 차단 + 새 공고 0건이면 페이지네이션 중단
        new_count = 0
        for notice in page_notices:
            if notice.content_hash not in seen_hashes:
                seen_hashes.add(notice.content_hash)
                notices.append(notice)
                new_count += 1

        logger.info(
            "GH page=%s rows=%s new=%s total=%s",
            page,
            len(rows),
            new_count,
            len(notices),
        )

        if new_count == 0:
            break
        # 10개 미만이면 마지막 페이지
        if len(rows) < 10:
            break

    return notices
