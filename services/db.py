from __future__ import annotations

import os
from pathlib import Path

from services.normalizer import Notice


class NoticeRepository:
    def __init__(self, db_url: str):
        self.db_url = db_url

    @classmethod
    def from_env(cls) -> "NoticeRepository":
        db_url = os.getenv("SUPABASE_DB_URL")
        password = os.getenv("SUPABASE_DB_PASSWORD")
        if not db_url:
            raise RuntimeError("SUPABASE_DB_URL is required unless running with --dry-run.")
        if password:
            db_url = db_url.replace("[password]", password).replace("[YOUR-PASSWORD]", password)
        return cls(db_url)

    def _connect(self):
        import psycopg

        return psycopg.connect(self.db_url)

    def ensure_schema(self) -> None:
        schema = Path("schema.sql").read_text(encoding="utf-8")
        with self._connect() as conn:
            for statement in schema.split(";"):
                if statement.strip():
                    conn.execute(statement)
            conn.commit()

    def insert_new_notices(self, notices: list[Notice]) -> list[Notice]:
        if not notices:
            return []

        inserted: set[str] = set()
        sql = """
            INSERT INTO notices (
                provider, region, notice_type, title, notice_date,
                apply_start_date, apply_end_date, status, url,
                attachment_url, content_hash
            )
            VALUES (
                %(provider)s, %(region)s, %(notice_type)s, %(title)s, %(notice_date)s,
                %(apply_start_date)s, %(apply_end_date)s, %(status)s, %(url)s,
                %(attachment_url)s, %(content_hash)s
            )
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING content_hash
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                for notice in notices:
                    cur.execute(sql, notice.__dict__)
                    row = cur.fetchone()
                    if row:
                        inserted.add(row[0])
            conn.commit()
        return [notice for notice in notices if notice.content_hash in inserted]

    def mark_notified(self, notices: list[Notice]) -> None:
        if not notices:
            return
        hashes = [notice.content_hash for notice in notices]
        with self._connect() as conn:
            conn.execute(
                "UPDATE notices SET notified_at = NOW() WHERE content_hash = ANY(%s)",
                (hashes,),
            )
            conn.commit()
