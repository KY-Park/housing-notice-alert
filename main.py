from __future__ import annotations

import argparse
import os
from collections import Counter

from dotenv import load_dotenv

from collectors.gh import collect_gh
from collectors.ih import collect_ih
from collectors.lh import collect_lh
from collectors.sh import collect_sh
from services.db import NoticeRepository
from services.emailer import send_notice_email
from services.normalizer import Notice, is_target_notice
from utils.logger import get_logger, setup_logging


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def collect_all() -> list[Notice]:
    logger = get_logger(__name__)
    collectors = [
        ("LH", collect_lh),
        ("SH", collect_sh),
        ("GH", collect_gh),
        ("iH", collect_ih),
    ]

    notices: list[Notice] = []
    for name, collector in collectors:
        try:
            items = collector()
            filtered = [notice for notice in items if is_target_notice(notice)]
            notices.extend(filtered)
            logger.info("%s collected=%s filtered=%s", name, len(items), len(filtered))
        except Exception:
            logger.exception("%s collector failed; continuing with other providers", name)

    deduped: dict[str, Notice] = {}
    for notice in notices:
        deduped[notice.content_hash] = notice
    return list(deduped.values())


def main() -> int:
    load_dotenv()
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    parser = argparse.ArgumentParser(description="Check new housing notices and email them.")
    parser.add_argument("--dry-run", action="store_true", help="Collect only; do not write DB or send email.")
    args = parser.parse_args()

    logger = get_logger(__name__)
    initial_sync = env_bool("INITIAL_SYNC_MODE", False)
    notices = collect_all()

    by_provider = Counter(notice.provider for notice in notices)
    logger.info("Collected %s unique target notices: %s", len(notices), dict(by_provider))

    if args.dry_run:
        for notice in sorted(notices, key=lambda item: (item.provider, item.notice_date or "", item.title), reverse=True):
            logger.info("[%s] %s | %s | %s", notice.provider, notice.notice_date, notice.title, notice.url)
        return 0

    repository = NoticeRepository.from_env()
    repository.ensure_schema()
    new_notices = repository.insert_new_notices(notices)
    logger.info("New notices inserted=%s", len(new_notices))

    if initial_sync:
        logger.info("INITIAL_SYNC_MODE=true; email skipped after seeding notices.")
        return 0

    if not new_notices:
        logger.info("No new notices; email skipped.")
        return 0

    send_notice_email(new_notices)
    repository.mark_notified(new_notices)
    logger.info("Email sent and notified_at updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
