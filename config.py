from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass
class Config:
    bot_token: str
    bot_username: str
    admin_ids: list[int]
    public_channel_id: str
    vip_channel_id: str
    price_unlock_signal_stars: int
    price_vip_monthly_stars: int
    price_deep_scan_stars: int
    auto_post_interval_minutes: int
    free_daily_scans: int
    referrals_per_free_unlock: int
    db_path: Path


def load_config() -> Config:
    raw_admins = os.getenv("ADMIN_IDS", "")
    admin_ids: list[int] = []
    for part in raw_admins.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            admin_ids.append(int(part))

    return Config(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        bot_username=os.getenv("BOT_USERNAME", "").strip().lstrip("@"),
        admin_ids=admin_ids,
        public_channel_id=os.getenv("PUBLIC_CHANNEL_ID", "").strip(),
        vip_channel_id=os.getenv("VIP_CHANNEL_ID", "").strip(),
        price_unlock_signal_stars=int(os.getenv("PRICE_UNLOCK_SIGNAL_STARS", "50")),
        price_vip_monthly_stars=int(os.getenv("PRICE_VIP_MONTHLY_STARS", "300")),
        price_deep_scan_stars=int(os.getenv("PRICE_DEEP_SCAN_STARS", "25")),
        auto_post_interval_minutes=int(os.getenv("AUTO_POST_INTERVAL_MINUTES", "45")),
        free_daily_scans=int(os.getenv("FREE_DAILY_SCANS", "1")),
        referrals_per_free_unlock=int(os.getenv("REFERRALS_PER_FREE_UNLOCK", "3")),
        db_path=BASE_DIR / "whale_radar.db",
    )
