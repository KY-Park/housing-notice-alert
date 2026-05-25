from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage

from services.normalizer import Notice


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required.")
    return value


def _subject(notices: list[Notice]) -> str:
    return f"[공고 알림] 서울·경기·인천 신규 임대/분양 공고 {len(notices)}건"


def _plain_text(notices: list[Notice]) -> str:
    lines = ["신규 공고가 발견되었습니다.", ""]
    for index, notice in enumerate(notices, start=1):
        lines.extend(
            [
                f"{index}. [{notice.provider}] {notice.title}",
                f"- 지역: {notice.region}",
                f"- 유형: {notice.notice_type or '-'}",
                f"- 공고일: {notice.notice_date or '-'}",
                f"- 접수기간: {notice.apply_start_date or '-'} ~ {notice.apply_end_date or '-'}",
                f"- 상태: {notice.status or '-'}",
                f"- 링크: {notice.url}",
                "",
            ]
        )
    return "\n".join(lines)


def _html(notices: list[Notice]) -> str:
    items = []
    for notice in notices:
        items.append(
            f"""
            <li style="margin:0 0 18px 0;">
              <div style="font-weight:700;">[{html.escape(notice.provider)}] {html.escape(notice.title)}</div>
              <div>지역: {html.escape(notice.region)}</div>
              <div>유형: {html.escape(notice.notice_type or "-")}</div>
              <div>공고일: {html.escape(notice.notice_date or "-")}</div>
              <div>접수기간: {html.escape(notice.apply_start_date or "-")} ~ {html.escape(notice.apply_end_date or "-")}</div>
              <div>상태: {html.escape(notice.status or "-")}</div>
              <div><a href="{html.escape(notice.url)}">공고 바로가기</a></div>
            </li>
            """
        )
    return f"""
    <!doctype html>
    <html lang="ko">
      <body style="font-family:Arial, sans-serif; line-height:1.55;">
        <p>신규 공고가 발견되었습니다.</p>
        <ol>
          {''.join(items)}
        </ol>
      </body>
    </html>
    """


def send_notice_email(notices: list[Notice]) -> None:
    sender = _required_env("GMAIL_ADDRESS")
    password = _required_env("GMAIL_APP_PASSWORD")
    recipient = _required_env("EMAIL_TO")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = _subject(notices)
    message.set_content(_plain_text(notices))
    message.add_alternative(_html(notices), subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)
