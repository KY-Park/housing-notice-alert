from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import requests

from services.normalizer import Notice, make_notice
from utils.date import parse_date
from utils.logger import get_logger


BASE_URL = "http://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"
REGION_CODES = {"서울": "11", "경기": "41", "인천": "28"}
NOTICE_TYPE_CODES = {
    "05": "분양주택",
    "06": "임대주택",
    "39": "신혼희망타운",
}
STATUSES = ["공고중", "접수중", "정정공고중"]


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            return value
        return []
    if isinstance(value, dict):
        for key in ("dsList", "list", "items", "item", "data", "body"):
            found = _records(value.get(key))
            if found:
                return found
        candidates: list[dict[str, Any]] = []
        for nested in value.values():
            candidates.extend(_records(nested))
        return candidates
    return []


def collect_lh() -> list[Notice]:
    service_key = os.getenv("DATA_GO_KR_API_KEY")
    if not service_key:
        get_logger(__name__).warning("DATA_GO_KR_API_KEY is not set; skipping LH.")
        return []

    timeout = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
    lookback_days = int(os.getenv("LOOKBACK_DAYS", "90"))
    start = (date.today() - timedelta(days=lookback_days)).strftime("%Y.%m.%d")
    end = (date.today() + timedelta(days=365)).strftime("%Y.%m.%d")

    notices: list[Notice] = []
    seen: set[str] = set()
    session = requests.Session()

    for region_name, region_code in REGION_CODES.items():
        for type_code, type_name in NOTICE_TYPE_CODES.items():
            for status in STATUSES:
                page = 1
                while page <= 20:
                    params = {
                        "ServiceKey": service_key,
                        "PG_SZ": "100",
                        "PAGE": str(page),
                        "CNP_CD": region_code,
                        "UPP_AIS_TP_CD": type_code,
                        "PAN_SS": status,
                        "PAN_NT_ST_DT": start,
                        "CLSG_DT": end,
                    }
                    response = session.get(BASE_URL, params=params, timeout=timeout)
                    response.raise_for_status()
                    data = response.json()
                    records = _records(data)
                    if not records:
                        break

                    for row in records:
                        title = row.get("PAN_NM") or row.get("panNm") or row.get("title")
                        url = row.get("DTL_URL") or row.get("dtlUrl") or row.get("url")
                        if not title or not url:
                            continue
                        region_value = row.get("CNP_CD_NM") or region_name
                        if region_value == "전국":
                            region_value = region_name
                        notice_date = parse_date(
                            row.get("PAN_NT_ST_DT")
                            or row.get("PAN_NT_ST_DTTM")
                            or row.get("panNtStDt")
                            or row.get("noticeDate")
                        )
                        close_date = parse_date(row.get("CLSG_DT") or row.get("clsgDt"))
                        notice = make_notice(
                            provider="LH",
                            region=region_value,
                            notice_type=row.get("AIS_TP_CD_NM") or row.get("UPP_AIS_TP_NM") or type_name,
                            title=str(title),
                            notice_date=notice_date,
                            apply_end_date=close_date,
                            status=row.get("PAN_SS") or status,
                            url=str(url),
                        )
                        if notice.content_hash not in seen:
                            notices.append(notice)
                            seen.add(notice.content_hash)

                    if len(records) < 100:
                        break
                    page += 1

    return notices
