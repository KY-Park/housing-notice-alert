from __future__ import annotations

from dataclasses import dataclass

from utils.hash import content_hash


TARGET_REGIONS = ("서울", "경기", "인천")
TARGET_KEYWORDS = (
    "임대",
    "분양",
    "행복주택",
    "국민임대",
    "공공임대",
    "통합공공임대",
    "영구임대",
    "장기전세",
    "매입임대",
    "전세임대",
    "신혼희망타운",
    "입주자",
    "모집공고",
)


@dataclass(frozen=True)
class Notice:
    provider: str
    region: str
    notice_type: str | None
    title: str
    notice_date: str | None
    apply_start_date: str | None
    apply_end_date: str | None
    status: str | None
    url: str
    attachment_url: str | None
    content_hash: str


def clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def infer_notice_type(title: str, fallback: str | None = None) -> str | None:
    for keyword in (
        "행복주택",
        "국민임대",
        "공공임대",
        "통합공공임대",
        "영구임대",
        "장기전세",
        "매입임대",
        "전세임대",
        "신혼희망타운",
        "분양",
        "임대",
    ):
        if keyword in title:
            return keyword
    return clean_text(fallback)


def normalize_region(region: str | None, title: str = "") -> str:
    source = f"{region or ''} {title}"
    if "서울" in source:
        return "서울"
    if "인천" in source:
        return "인천"
    if "경기" in source or any(name in source for name in ("수원", "성남", "고양", "용인", "부천", "안산", "안양", "남양주", "화성", "평택", "의정부", "시흥", "파주", "김포", "광주", "광명", "군포", "하남", "오산", "양주", "이천", "구리", "안성", "포천", "의왕", "여주", "동두천", "과천", "가평", "양평", "연천")):
        return "경기"
    return clean_text(region) or "기타"


def make_notice(
    *,
    provider: str,
    region: str | None,
    notice_type: str | None,
    title: str,
    notice_date: str | None,
    url: str,
    apply_start_date: str | None = None,
    apply_end_date: str | None = None,
    status: str | None = None,
    attachment_url: str | None = None,
) -> Notice:
    clean_title = clean_text(title) or ""
    clean_url = clean_text(url) or ""
    clean_region = normalize_region(region, clean_title)
    clean_type = infer_notice_type(clean_title, notice_type)
    digest = content_hash(provider, clean_title, notice_date, clean_url)
    return Notice(
        provider=provider,
        region=clean_region,
        notice_type=clean_type,
        title=clean_title,
        notice_date=notice_date,
        apply_start_date=apply_start_date,
        apply_end_date=apply_end_date,
        status=clean_text(status),
        url=clean_url,
        attachment_url=clean_text(attachment_url),
        content_hash=digest,
    )


def is_target_notice(notice: Notice) -> bool:
    if not any(region in notice.region for region in TARGET_REGIONS):
        return False
    if notice.provider == "GH" and "경기" not in notice.region:
        return False
    text = f"{notice.title} {notice.notice_type or ''}"
    return any(keyword in text for keyword in TARGET_KEYWORDS)
