from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    joined_at INTEGER NOT NULL,
                    vip_until INTEGER DEFAULT 0,
                    credits INTEGER DEFAULT 0,
                    referred_by INTEGER DEFAULT NULL,
                    referral_count INTEGER DEFAULT 0,
                    free_scans_today INTEGER DEFAULT 0,
                    last_scan_date TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    signal_type TEXT NOT NULL,
                    chain TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    token_address TEXT NOT NULL,
                    pair_address TEXT DEFAULT '',
                    price_usd TEXT NOT NULL,
                    price_change_1h REAL DEFAULT 0,
                    price_change_24h REAL DEFAULT 0,
                    volume_24h REAL DEFAULT 0,
                    liquidity_usd REAL DEFAULT 0,
                    fdv REAL DEFAULT 0,
                    buys_1h INTEGER DEFAULT 0,
                    sells_1h INTEGER DEFAULT 0,
                    buy_ratio REAL DEFAULT 0,
                    security_summary TEXT DEFAULT '',
                    whale_score INTEGER DEFAULT 0,
                    entry_zone TEXT DEFAULT '',
                    targets_text TEXT DEFAULT '',
                    stop_loss TEXT DEFAULT '',
                    dex_url TEXT DEFAULT '',
                    teaser_text TEXT NOT NULL,
                    full_text TEXT NOT NULL,
                    posted_public INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS unlocked_signals (
                    user_id INTEGER NOT NULL,
                    signal_id TEXT NOT NULL,
                    unlocked_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, signal_id)
                );

                CREATE TABLE IF NOT EXISTS payments (
                    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    telegram_payment_charge_id TEXT UNIQUE NOT NULL,
                    provider_payment_charge_id TEXT DEFAULT '',
                    payload TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    item_ref TEXT DEFAULT '',
                    stars_amount INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    refunded INTEGER DEFAULT 0
                );
                """
            )

    def upsert_user(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        referred_by: Optional[int] = None,
        referrals_per_free_unlock: int = 3,
    ) -> tuple[bool, Optional[int]]:
        """
        Returns (is_new_user, referrer_id_if_rewarded).
        """
        now = int(time.time())
        rewarded_referrer: Optional[int] = None

        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()

            if row is not None:
                conn.execute(
                    "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                    (username or "", first_name or "", user_id),
                )
                return False, None

            valid_ref: Optional[int] = None
            if referred_by and referred_by != user_id:
                ref_row = conn.execute(
                    "SELECT user_id, referral_count FROM users WHERE user_id = ?",
                    (referred_by,),
                ).fetchone()
                if ref_row is not None:
                    valid_ref = referred_by
                    new_count = int(ref_row["referral_count"]) + 1
                    bonus_credit = (
                        1 if (new_count % referrals_per_free_unlock == 0) else 0
                    )
                    conn.execute(
                        """
                        UPDATE users
                        SET referral_count = ?, credits = credits + ?
                        WHERE user_id = ?
                        """,
                        (new_count, bonus_credit, valid_ref),
                    )
                    if bonus_credit > 0:
                        rewarded_referrer = valid_ref

            conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, joined_at, credits, referred_by)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (user_id, username or "", first_name or "", now, valid_ref),
            )
            return True, rewarded_referrer

    def get_user(self, user_id: int) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def is_vip(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user:
            return False
        return int(user["vip_until"]) > int(time.time())

    def extend_vip(self, user_id: int, days: int = 30) -> int:
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT vip_until FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            current_until = int(row["vip_until"]) if row else 0
            base_time = max(now, current_until)
            new_until = base_time + (days * 86400)
            conn.execute(
                "UPDATE users SET vip_until = ? WHERE user_id = ?",
                (new_until, user_id),
            )
            return new_until

    def add_credits(self, user_id: int, amount: int) -> int:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET credits = MAX(0, credits + ?) WHERE user_id = ?",
                (amount, user_id),
            )
            row = conn.execute(
                "SELECT credits FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return int(row["credits"]) if row else 0

    def use_credit_for_signal(self, user_id: int, signal_id: str) -> bool:
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT credits FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row or int(row["credits"]) <= 0:
                return False
            conn.execute(
                "UPDATE users SET credits = credits - 1 WHERE user_id = ?",
                (user_id,),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO unlocked_signals (user_id, signal_id, unlocked_at)
                VALUES (?, ?, ?)
                """,
                (user_id, signal_id, now),
            )
            return True

    def check_and_consume_free_scan(self, user_id: int, daily_limit: int) -> bool:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT free_scans_today, last_scan_date, vip_until FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return False
            if int(row["vip_until"]) > int(time.time()):
                return True
            scans = int(row["free_scans_today"])
            last_date = str(row["last_scan_date"])
            if last_date != today:
                scans = 0
            if scans >= daily_limit:
                return False
            conn.execute(
                """
                UPDATE users
                SET free_scans_today = ?, last_scan_date = ?
                WHERE user_id = ?
                """,
                (scans + 1, today, user_id),
            )
            return True

    def save_signal(self, signal: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO signals (
                    signal_id, created_at, signal_type, chain, symbol, name,
                    token_address, pair_address, price_usd, price_change_1h,
                    price_change_24h, volume_24h, liquidity_usd, fdv,
                    buys_1h, sells_1h, buy_ratio, security_summary, whale_score,
                    entry_zone, targets_text, stop_loss, dex_url,
                    teaser_text, full_text, posted_public
                ) VALUES (
                    :signal_id, :created_at, :signal_type, :chain, :symbol, :name,
                    :token_address, :pair_address, :price_usd, :price_change_1h,
                    :price_change_24h, :volume_24h, :liquidity_usd, :fdv,
                    :buys_1h, :sells_1h, :buy_ratio, :security_summary, :whale_score,
                    :entry_zone, :targets_text, :stop_loss, :dex_url,
                    :teaser_text, :full_text, :posted_public
                )
                """,
                signal,
            )

    def mark_signal_posted(self, signal_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE signals SET posted_public = 1 WHERE signal_id = ?",
                (signal_id,),
            )

    def get_signal(self, signal_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM signals WHERE signal_id = ?", (signal_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_recent_signals(self, limit: int = 8) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def has_recent_token_signal(
        self, token_address: str, within_seconds: int = 14400
    ) -> bool:
        cutoff = int(time.time()) - within_seconds
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT signal_id FROM signals
                WHERE LOWER(token_address) = LOWER(?) AND created_at > ?
                LIMIT 1
                """,
                (token_address, cutoff),
            ).fetchone()
            return row is not None

    def unlock_signal(self, user_id: int, signal_id: str) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO unlocked_signals (user_id, signal_id, unlocked_at)
                VALUES (?, ?, ?)
                """,
                (user_id, signal_id, now),
            )

    def is_signal_unlocked(self, user_id: int, signal_id: str) -> bool:
        if self.is_vip(user_id):
            return True
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM unlocked_signals
                WHERE user_id = ? AND signal_id = ?
                """,
                (user_id, signal_id),
            ).fetchone()
            return row is not None

    def record_payment(
        self,
        user_id: int,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str,
        payload: str,
        item_type: str,
        item_ref: str,
        stars_amount: int,
    ) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO payments (
                    user_id, telegram_payment_charge_id, provider_payment_charge_id,
                    payload, item_type, item_ref, stars_amount, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    telegram_payment_charge_id,
                    provider_payment_charge_id,
                    payload,
                    item_type,
                    item_ref,
                    stars_amount,
                    now,
                ),
            )

    def mark_payment_refunded(self, charge_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE payments SET refunded = 1 WHERE telegram_payment_charge_id = ?",
                (charge_id,),
            )

    def get_stats(self) -> dict[str, Any]:
        now = int(time.time())
        with self._connect() as conn:
            total_users = conn.execute(
                "SELECT COUNT(*) AS c FROM users"
            ).fetchone()["c"]
            active_vips = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE vip_until > ?", (now,)
            ).fetchone()["c"]
            total_signals = conn.execute(
                "SELECT COUNT(*) AS c FROM signals"
            ).fetchone()["c"]
            total_stars = conn.execute(
                "SELECT COALESCE(SUM(stars_amount), 0) AS s FROM payments WHERE refunded = 0"
            ).fetchone()["s"]
            total_payments = conn.execute(
                "SELECT COUNT(*) AS c FROM payments WHERE refunded = 0"
            ).fetchone()["c"]
            recent_payments = conn.execute(
                """
                SELECT user_id, item_type, stars_amount, telegram_payment_charge_id, created_at
                FROM payments
                ORDER BY created_at DESC
                LIMIT 5
                """
            ).fetchall()
            return {
                "total_users": int(total_users),
                "active_vips": int(active_vips),
                "total_signals": int(total_signals),
                "total_stars": int(total_stars),
                "total_payments": int(total_payments),
                "recent_payments": [dict(r) for r in recent_payments],
            }

    def get_all_user_ids(self) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT user_id FROM users").fetchall()
            return [int(r["user_id"]) for r in rows]
