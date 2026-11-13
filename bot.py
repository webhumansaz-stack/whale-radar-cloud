from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

from config import Config, load_config
from database import Database
from promoter import (
    DEFAULT_PUBLIC_CHANNEL_URL,
    auto_post_tweet_via_chrome,
    build_pinned_welcome_post,
    build_viral_promo_pack,
    post_to_cmc_cloud,
)
from scanner import MarketScanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("WhaleRadarBot")


class WhaleRadarBot:
    def __init__(self, config: Config, db: Database, scanner: MarketScanner) -> None:
        self.cfg = config
        self.db = db
        self.scanner = scanner
        self.api_base = f"https://api.telegram.org/bot{self.cfg.bot_token}"
        self._offset = 0
        self._session: Optional[aiohttp.ClientSession] = None

    async def api_call(self, method: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        url = f"{self.api_base}/{method}"
        try:
            async with self._session.post(url, json=payload or {}, timeout=35) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    logger.warning("Telegram API error on %s: %s", method, data)
                return data
        except Exception as exc:
            logger.error("Request failed (%s): %s", method, exc)
            return {"ok": False, "description": str(exc)}

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_markup: Optional[dict[str, Any]] = None,
        disable_web_page_preview: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self.api_call("sendMessage", payload)

    async def edit_message(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        reply_markup: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self.api_call("editMessageText", payload)

    async def send_stars_invoice(
        self,
        chat_id: int,
        title: str,
        description: str,
        payload_str: str,
        stars_amount: int,
        button_label: str,
    ) -> dict[str, Any]:
        """
        Sends an official Telegram Stars (XTR) invoice.
        Note: For Telegram Stars digital items, currency='XTR' and provider_token=''.
        """
        invoice_payload = {
            "chat_id": chat_id,
            "title": title,
            "description": description,
            "payload": payload_str,
            "provider_token": "",
            "currency": "XTR",
            "prices": [{"label": title, "amount": stars_amount}],
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": f"⭐ {button_label} ({stars_amount} ⭐)", "pay": True}],
                    [{"text": "🔙 Back to Menu", "callback_data": "menu:home"}],
                ]
            },
        }
        return await self.api_call("sendInvoice", invoice_payload)

    def main_menu_keyboard(self, user_id: int) -> dict[str, Any]:
        rows = [
            [
                {"text": "🐋 Live Whale Signals", "callback_data": "menu:signals"},
                {"text": "⚡ Arbitrage Radar", "callback_data": "menu:arb"},
            ],
            [
                {"text": "🕵️‍♂️ Audit Any Token", "callback_data": "menu:scan_help"},
                {
                    "text": f"👑 VIP All-Access ({self.cfg.price_vip_monthly_stars} ⭐)",
                    "callback_data": "menu:vip",
                },
            ],
            [
                {"text": "🎁 Earn Free Unlocks", "callback_data": "menu:referral"},
                {"text": "👤 My Account", "callback_data": "menu:profile"},
            ],
        ]
        if user_id in self.cfg.admin_ids:
            rows.append(
                [{"text": "🛠 Admin Control Panel", "callback_data": "admin:panel"}]
            )
        return {"inline_keyboard": rows}

    def public_channel_keyboard(self, signal_id: str) -> dict[str, Any]:
        bot_user = self.cfg.bot_username
        return {
            "inline_keyboard": [
                [
                    {
                        "text": f"🔓 Unlock Signal & Contract ({self.cfg.price_unlock_signal_stars} ⭐)",
                        "url": f"https://t.me/{bot_user}?start=unlock_{signal_id}",
                    }
                ],
                [
                    {
                        "text": f"👑 Join 24/7 VIP Instant Feed ({self.cfg.price_vip_monthly_stars} ⭐/mo)",
                        "url": f"https://t.me/{bot_user}?start=vip",
                    },
                    {
                        "text": "🕵️‍♂️ Free Token Scanner",
                        "url": f"https://t.me/{bot_user}?start=scanner",
                    },
                ],
            ]
        }

    def signal_bot_keyboard(self, user_id: int, signal_id: str) -> dict[str, Any]:
        unlocked = self.db.is_signal_unlocked(user_id, signal_id)
        if unlocked:
            return {
                "inline_keyboard": [
                    [
                        {
                            "text": "🔓 View Full Unlocked Signal",
                            "callback_data": f"view_unlocked:{signal_id}",
                        }
                    ],
                    [{"text": "🔙 All Signals", "callback_data": "menu:signals"}],
                ]
            }

        user = self.db.get_user(user_id) or {}
        credits = int(user.get("credits") or 0)
        rows = [
            [
                {
                    "text": f"🔓 Unlock Instantly ({self.cfg.price_unlock_signal_stars} ⭐)",
                    "callback_data": f"buy_signal:{signal_id}",
                }
            ]
        ]
        if credits > 0:
            rows.append(
                [
                    {
                        "text": f"🎁 Unlock with 1 Credit (You have {credits})",
                        "callback_data": f"credit_unlock:{signal_id}",
                    }
                ]
            )
        rows.append(
            [
                {
                    "text": f"👑 Get Unlimited VIP ({self.cfg.price_vip_monthly_stars} ⭐/mo)",
                    "callback_data": "menu:vip",
                }
            ]
        )
        rows.append([{"text": "🔙 Back to Signals", "callback_data": "menu:signals"}])
        return {"inline_keyboard": rows}

    def welcome_text(self, first_name: str, user_id: int) -> str:
        is_vip = self.db.is_vip(user_id)
        user = self.db.get_user(user_id) or {}
        credits = int(user.get("credits") or 0)
        status_badge = "👑 <b>VIP ALL-ACCESS ACTIVE</b>" if is_vip else "🆓 Standard Member"
        return (
            f"🐋 <b>Welcome to Whale & Arbitrage Radar Global, {html.escape(first_name or 'Trader')}!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"We track real-time <b>Institutional Whale Accumulation</b>, <b>Smart-Money DEX Momentum</b> "
            f"(Solana • Base • Ethereum • BSC), and <b>Cross-Exchange Arbitrage Spreads</b> 24/7.\n\n"
            f"📌 <b>Your Status:</b> {status_badge} | 🎁 <b>Credits:</b> <code>{credits}</code>\n\n"
            f"🔥 <b>What you can do right now:</b>\n"
            f"• 🐋 <b>Live Whale Signals:</b> Unlock high-conviction whale buys for <b>{self.cfg.price_unlock_signal_stars} ⭐</b>.\n"
            f"• ⚡ <b>Arbitrage Scanner:</b> Compare live Binance, Bybit & KuCoin spreads.\n"
            f"• 🕵️‍♂️ <b>On-Chain Token Auditor:</b> Paste any token address or ticker here for a live whale + rug check!\n"
            f"• 👑 <b>VIP Feed ({self.cfg.price_vip_monthly_stars} ⭐/mo):</b> Instant 0-second alerts + all signals unlocked."
        )

    async def generate_and_publish_signal(
        self, post_to_channels: bool = True
    ) -> Optional[dict[str, Any]]:
        signal = await self.scanner.discover_whale_signal(
            exclude_checker=lambda addr: self.db.has_recent_token_signal(addr, 7200)
        )
        if not signal:
            signal = await self.scanner.discover_whale_signal(exclude_checker=None)
        if not signal:
            return None

        self.db.save_signal(signal)
        sig_id = signal["signal_id"]

        if post_to_channels:
            if self.cfg.public_channel_id:
                res = await self.send_message(
                    self.cfg.public_channel_id,
                    signal["teaser_text"],
                    reply_markup=self.public_channel_keyboard(sig_id),
                )
                if res.get("ok"):
                    self.db.mark_signal_posted(sig_id)
            if self.cfg.vip_channel_id:
                await self.send_message(
                    self.cfg.vip_channel_id,
                    signal["full_text"],
                )
            promo = build_viral_promo_pack(
                signal,
                public_channel_url=DEFAULT_PUBLIC_CHANNEL_URL,
                bot_username=self.cfg.bot_username or "WhaleAlphaStars_bot",
            )
            asyncio.create_task(auto_post_tweet_via_chrome(promo["tweet_plain"]))
        return signal

    async def handle_start(
        self, chat_id: int, user_id: int, username: str, first_name: str, arg: str
    ) -> None:
        referred_by: Optional[int] = None
        if arg.startswith("ref_"):
            ref_str = arg.replace("ref_", "").strip()
            if ref_str.isdigit():
                referred_by = int(ref_str)

        is_new_user, rewarded_referrer = self.db.upsert_user(
            user_id=user_id,
            username=username,
            first_name=first_name,
            referred_by=referred_by,
            referrals_per_free_unlock=self.cfg.referrals_per_free_unlock,
        )

        if rewarded_referrer:
            await self.send_message(
                rewarded_referrer,
                "🎉 <b>Referral Milestone Reached!</b>\n"
                "You just earned <b>+1 Free Signal Unlock Credit (🎁)</b> because your invited friends joined the bot!",
            )

        # Deep-link: ?start=unlock_WHALE-XXXXXX
        if arg.startswith("unlock_"):
            signal_id = arg.replace("unlock_", "").strip()
            signal = self.db.get_signal(signal_id)
            if not signal:
                await self.send_message(
                    chat_id,
                    "⚠️ Signal not found or expired. Browse our latest live signals below:",
                    reply_markup=self.main_menu_keyboard(user_id),
                )
                return

            if self.db.is_signal_unlocked(user_id, signal_id):
                await self.send_message(
                    chat_id,
                    signal["full_text"],
                    reply_markup=self.main_menu_keyboard(user_id),
                )
                return

            await self.send_message(
                chat_id,
                signal["teaser_text"],
                reply_markup=self.signal_bot_keyboard(user_id, signal_id),
            )
            await self.send_stars_invoice(
                chat_id=chat_id,
                title=f"Unlock Whale Signal {signal_id}",
                description=(
                    f"Instant access to exact Token Ticker, Contract Address, "
                    f"Security Audit & Entry/TP/SL zones for {signal_id} ({signal['chain']})."
                ),
                payload_str=f"unlock_signal:{signal_id}",
                stars_amount=self.cfg.price_unlock_signal_stars,
                button_label=f"Unlock {signal_id} Now",
            )
            return

        # Deep-link: ?start=vip
        if arg == "vip":
            await self.send_vip_offer(chat_id, user_id)
            return

        # Deep-link: ?start=arb
        if arg == "arb":
            arb_report = await self.scanner.scan_cex_arbitrage()
            await self.send_message(
                chat_id,
                arb_report,
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "🔄 Refresh Arbitrage Spreads", "callback_data": "menu:arb"}],
                        [{"text": f"👑 Join 24/7 VIP Instant Feed ({self.cfg.price_vip_monthly_stars} ⭐/mo)", "callback_data": "menu:vip"}],
                        [{"text": "🔙 Main Menu", "callback_data": "menu:home"}],
                    ]
                },
            )
            return

        # Deep-link: ?start=scanner or ?start=scan
        if arg in ("scanner", "scan"):
            await self.send_message(
                chat_id,
                "🕵️‍♂️ <b>ON-CHAIN TOKEN SECURITY & WHALE AUDITOR</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Send any <b>Token Ticker</b> (e.g. <code>SOL</code>, <code>PEPE</code>, <code>WIF</code>, <code>BONK</code>) "
                "or paste a <b>Smart Contract Address</b> directly in this chat to run a live DEX liquidity, orderflow & RugCheck/GoPlus security audit.",
                reply_markup=self.main_menu_keyboard(user_id),
            )
            return

        # Deep-link: ?start=welcome_gift or new user signup bonus
        if arg == "welcome_gift" or is_new_user:
            user_row = self.db.get_user(user_id) or {}
            credits = int(user_row.get("credits") or 0)
            if credits == 0 and arg == "welcome_gift":
                credits = self.db.add_credits(user_id, 1)
            recent = self.db.get_recent_signals(limit=1)
            latest_sid = recent[0]["signal_id"] if recent else ""
            gift_rows = []
            if latest_sid:
                gift_rows.append(
                    [
                        {
                            "text": f"🎁 Unlock Latest Signal ({latest_sid}) For Free",
                            "callback_data": f"credit_unlock:{latest_sid}",
                        }
                    ]
                )
            gift_rows.extend(self.main_menu_keyboard(user_id)["inline_keyboard"])
            await self.send_message(
                chat_id,
                self.welcome_text(first_name, user_id)
                + f"\n\n🎁 <b>WELCOME BONUS ACTIVE:</b> You have <b>{credits} Free Signal Unlock Credit</b> ready to use! Tap the button below to unlock our latest Whale Signal for free:",
                reply_markup={"inline_keyboard": gift_rows},
            )
            return

        # Standard /start
        await self.send_message(
            chat_id,
            self.welcome_text(first_name, user_id),
            reply_markup=self.main_menu_keyboard(user_id),
        )

    async def send_vip_offer(self, chat_id: int, user_id: int) -> None:
        user = self.db.get_user(user_id) or {}
        vip_until = int(user.get("vip_until") or 0)
        now = int(time.time())
        if vip_until > now:
            exp_str = datetime.fromtimestamp(vip_until, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
            status_line = f"✅ <b>Active VIP until:</b> <code>{exp_str}</code>\n\n"
        else:
            status_line = ""

        text = (
            f"👑 <b>WHALE RADAR VIP ALL-ACCESS (30 DAYS)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{status_line}"
            f"Upgrade to institutional-grade speed and unlock everything for 30 days:\n\n"
            f"✅ <b>Instant Access to Private VIP Channel</b> (0-second whale & arbitrage alerts)\n"
            f"✅ <b>100% of Locked Signals Unlocked Automatically</b> (No paying 50 ⭐ per signal)\n"
            f"✅ <b>Unlimited On-Chain Token Security & Whale Audits</b>\n"
            f"✅ <b>Entry, Take-Profit (TP1-TP3) & Stop-Loss Execution Zones</b>\n\n"
            f"💳 <b>Membership Price:</b> <b>{self.cfg.price_vip_monthly_stars} ⭐ Telegram Stars</b> (30 Days)"
        )
        await self.send_message(chat_id, text)
        await self.send_stars_invoice(
            chat_id=chat_id,
            title="VIP All-Access Pass (30 Days)",
            description="30-day access to Private VIP Channel + Unlimited Whale Signals & Token Security Audits.",
            payload_str="vip_30d:monthly",
            stars_amount=self.cfg.price_vip_monthly_stars,
            button_label="Activate 30-Day VIP",
        )

    async def handle_callback(self, cb: dict[str, Any]) -> None:
        cb_id = cb["id"]
        from_user = cb.get("from") or {}
        user_id = int(from_user.get("id"))
        username = str(from_user.get("username") or "")
        first_name = str(from_user.get("first_name") or "")
        msg = cb.get("message") or {}
        chat_id = int((msg.get("chat") or {}).get("id") or user_id)
        data = str(cb.get("data") or "")

        self.db.upsert_user(user_id, username, first_name)
        await self.api_call("answerCallbackQuery", {"callback_query_id": cb_id})

        if data == "menu:home":
            await self.send_message(
                chat_id,
                self.welcome_text(first_name, user_id),
                reply_markup=self.main_menu_keyboard(user_id),
            )
            return

        if data == "menu:signals":
            signals = self.db.get_recent_signals(limit=5)
            if not signals:
                await self.send_message(
                    chat_id,
                    "📡 <b>Scanning live DEX orderbooks for Whale Accumulation...</b>\nOne moment!",
                )
                sig = await self.generate_and_publish_signal(post_to_channels=False)
                if sig:
                    signals = [sig]

            if not signals:
                await self.send_message(
                    chat_id,
                    "⚠️ No high-conviction signals matched our strict liquidity filter right now. Try again shortly!",
                    reply_markup=self.main_menu_keyboard(user_id),
                )
                return

            kb_rows = []
            lines = [
                "🐋 <b>LATEST LIVE WHALE ACCUMULATION SIGNALS</b>",
                "<i>Select any signal below to inspect or unlock:</i>",
                "━━━━━━━━━━━━━━━━━━━━━━",
            ]
            for s in signals:
                sid = s["signal_id"]
                unlocked = self.db.is_signal_unlocked(user_id, sid)
                icon = "🔓" if unlocked else "🔒"
                sym_display = (
                    f"${s['symbol']}" if unlocked else f"#{s['chain']} Whale Alert"
                )
                lines.append(
                    f"{icon} <b>{sid}</b> • {sym_display} • Score: <b>{s['whale_score']}/100</b> "
                    f"(1H Buys: <b>{s['buy_ratio']:.0f}%</b> | Liq: <code>${s['liquidity_usd']:,.0f}</code>)"
                )
                kb_rows.append(
                    [
                        {
                            "text": f"{icon} {sid} ({s['chain']} • Score {s['whale_score']}/100)",
                            "callback_data": f"inspect:{sid}",
                        }
                    ]
                )
            kb_rows.append(
                [
                    {
                        "text": "🔄 Scan Fresh Live Market Signal",
                        "callback_data": "scan_fresh_signal",
                    }
                ]
            )
            kb_rows.append([{"text": "🔙 Main Menu", "callback_data": "menu:home"}])
            await self.send_message(
                chat_id, "\n".join(lines), reply_markup={"inline_keyboard": kb_rows}
            )
            return

        if data == "scan_fresh_signal":
            await self.send_message(
                chat_id, "🛰 <b>Scanning Solana, Base, Ethereum & BSC whale wallets...</b>"
            )
            sig = await self.generate_and_publish_signal(post_to_channels=False)
            if not sig:
                await self.send_message(
                    chat_id,
                    "⚠️ Could not reach DexScreener right now. Please try again in a few seconds.",
                )
                return
            sid = sig["signal_id"]
            if self.db.is_signal_unlocked(user_id, sid):
                await self.send_message(
                    chat_id,
                    sig["full_text"],
                    reply_markup=self.main_menu_keyboard(user_id),
                )
            else:
                await self.send_message(
                    chat_id,
                    sig["teaser_text"],
                    reply_markup=self.signal_bot_keyboard(user_id, sid),
                )
            return

        if data.startswith("inspect:"):
            sid = data.split(":", 1)[1]
            sig = self.db.get_signal(sid)
            if not sig:
                await self.send_message(chat_id, "⚠️ Signal not found.")
                return
            if self.db.is_signal_unlocked(user_id, sid):
                await self.send_message(
                    chat_id,
                    sig["full_text"],
                    reply_markup=self.main_menu_keyboard(user_id),
                )
            else:
                await self.send_message(
                    chat_id,
                    sig["teaser_text"],
                    reply_markup=self.signal_bot_keyboard(user_id, sid),
                )
            return

        if data.startswith("view_unlocked:"):
            sid = data.split(":", 1)[1]
            sig = self.db.get_signal(sid)
            if sig and self.db.is_signal_unlocked(user_id, sid):
                await self.send_message(
                    chat_id,
                    sig["full_text"],
                    reply_markup=self.main_menu_keyboard(user_id),
                )
            return

        if data.startswith("buy_signal:"):
            sid = data.split(":", 1)[1]
            sig = self.db.get_signal(sid)
            if not sig:
                await self.send_message(chat_id, "⚠️ Signal not found.")
                return
            await self.send_stars_invoice(
                chat_id=chat_id,
                title=f"Unlock Whale Signal {sid}",
                description=(
                    f"Full Contract Address, Token Ticker, Security Audit & "
                    f"Entry/Take-Profit Targets for {sid} ({sig['chain']})."
                ),
                payload_str=f"unlock_signal:{sid}",
                stars_amount=self.cfg.price_unlock_signal_stars,
                button_label=f"Unlock {sid}",
            )
            return

        if data.startswith("credit_unlock:"):
            sid = data.split(":", 1)[1]
            sig = self.db.get_signal(sid)
            if not sig:
                return
            if self.db.use_credit_for_signal(user_id, sid):
                await self.send_message(
                    chat_id,
                    "✅ <b>1 Credit Used! Here is your unlocked signal:</b>\n\n"
                    + sig["full_text"],
                    reply_markup=self.main_menu_keyboard(user_id),
                )
            else:
                await self.send_message(
                    chat_id,
                    "⚠️ You don't have enough credits. Unlock with Stars or invite friends!",
                )
            return

        if data == "menu:arb":
            await self.send_message(
                chat_id,
                "⚡ <b>Scanning live orderbooks on Binance, Bybit & KuCoin...</b>",
            )
            report = await self.scanner.scan_cex_arbitrage()
            await self.send_message(
                chat_id,
                report,
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "🔄 Refresh Spreads", "callback_data": "menu:arb"}],
                        [
                            {
                                "text": f"👑 Get Auto Arbitrage Alerts ({self.cfg.price_vip_monthly_stars} ⭐)",
                                "callback_data": "menu:vip",
                            }
                        ],
                        [{"text": "🔙 Main Menu", "callback_data": "menu:home"}],
                    ]
                },
            )
            return

        if data == "menu:scan_help":
            await self.send_message(
                chat_id,
                "🕵️‍♂️ <b>ON-CHAIN TOKEN & WHALE AUDITOR</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Simply <b>send any Token Contract Address or Ticker</b> right here in the chat "
                "(for example: <code>PEPE</code>, <code>BONK</code>, <code>WIF</code>, or any Solana / Base / Ethereum contract address).\n\n"
                f"🎁 You get <b>{self.cfg.free_daily_scans} Free Scan per day</b>.\n"
                f"⚡ Need more scans? Grab a <b>5-Credit Pack ({self.cfg.price_deep_scan_stars} ⭐)</b> or <b>Unlimited VIP ({self.cfg.price_vip_monthly_stars} ⭐)</b>!",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": f"⚡ Buy +5 Unlock/Scan Credits ({self.cfg.price_deep_scan_stars} ⭐)",
                                "callback_data": "buy_credits",
                            }
                        ],
                        [{"text": "🔙 Main Menu", "callback_data": "menu:home"}],
                    ]
                },
            )
            return

        if data == "buy_credits":
            await self.send_stars_invoice(
                chat_id=chat_id,
                title="5x Whale Unlock & Audit Credits",
                description="Add +5 Universal Credits to unlock signals or run deep token security audits.",
                payload_str="scan_pack:5",
                stars_amount=self.cfg.price_deep_scan_stars,
                button_label="Buy 5 Credits",
            )
            return

        if data == "menu:vip":
            await self.send_vip_offer(chat_id, user_id)
            return

        if data == "menu:referral":
            user = self.db.get_user(user_id) or {}
            ref_count = int(user.get("referral_count") or 0)
            credits = int(user.get("credits") or 0)
            ref_link = f"https://t.me/{self.cfg.bot_username}?start=ref_{user_id}"
            await self.send_message(
                chat_id,
                f"🎁 <b>INVITE FRIENDS & EARN FREE SIGNAL UNLOCKS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Share your personal referral link in crypto groups, X (Twitter), or with friends.\n"
                f"Every <b>{self.cfg.referrals_per_free_unlock} users</b> who start the bot via your link gives you "
                f"<b>+1 Free Signal Unlock Credit (worth {self.cfg.price_unlock_signal_stars} ⭐)!</b>\n\n"
                f"👥 <b>Your Referrals:</b> <code>{ref_count}</code>\n"
                f"🎁 <b>Available Credits:</b> <code>{credits}</code>\n\n"
                f"🔗 <b>Your Personal Referral Link (Tap to copy):</b>\n"
                f"<code>{ref_link}</code>",
                reply_markup=self.main_menu_keyboard(user_id),
            )
            return

        if data == "menu:profile":
            user = self.db.get_user(user_id) or {}
            vip_until = int(user.get("vip_until") or 0)
            now = int(time.time())
            if vip_until > now:
                days_left = (vip_until - now) / 86400
                vip_str = f"👑 Active ({days_left:.1f} days remaining)"
            else:
                vip_str = "🆓 Standard (Not VIP)"
            await self.send_message(
                chat_id,
                f"👤 <b>YOUR TRADER PROFILE</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                f"🎖 <b>Membership:</b> {vip_str}\n"
                f"🎁 <b>Unlock Credits:</b> <code>{user.get('credits', 0)}</code>\n"
                f"👥 <b>Referrals:</b> <code>{user.get('referral_count', 0)}</code>",
                reply_markup=self.main_menu_keyboard(user_id),
            )
            return

        # Admin callbacks
        if data.startswith("admin:") and user_id in self.cfg.admin_ids:
            await self.handle_admin_action(chat_id, user_id, data)

    async def handle_admin_action(
        self, chat_id: int, user_id: int, action: str
    ) -> None:
        if action == "admin:panel":
            stats = self.db.get_stats()
            recent_lines = []
            for p in stats["recent_payments"]:
                recent_lines.append(
                    f"• <code>{p['stars_amount']} ⭐</code> ({p['item_type']}) — Charge ID: <code>{p['telegram_payment_charge_id']}</code>"
                )
            payments_str = (
                "\n".join(recent_lines) if recent_lines else "<i>No payments yet</i>"
            )
            text = (
                f"🛠 <b>ADMIN CONTROL PANEL (REVENUE & AUTOMATION)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 <b>Total Users:</b> <code>{stats['total_users']}</code>\n"
                f"👑 <b>Active VIP Subscribers:</b> <code>{stats['active_vips']}</code>\n"
                f"📡 <b>Total Signals Generated:</b> <code>{stats['total_signals']}</code>\n"
                f"💰 <b>Total Revenue Earned:</b> <b>{stats['total_stars']} ⭐ Stars</b> ({stats['total_payments']} sales)\n\n"
                f"📢 <b>Public Channel:</b> <code>{self.cfg.public_channel_id or 'Not Set (.env)'}</code>\n"
                f"🔐 <b>VIP Channel:</b> <code>{self.cfg.vip_channel_id or 'Not Set (.env)'}</code>\n\n"
                f"🧾 <b>Recent Stars Payments:</b>\n{payments_str}\n\n"
                f"💡 <i>Tip: To refund a test payment to yourself, send:</i>\n"
                f"<code>/refund CHARGE_ID</code>"
            )
            kb = {
                "inline_keyboard": [
                    [
                        {
                            "text": "🚀 Scan & Post Signal to Channels Now",
                            "callback_data": "admin:post_now",
                        }
                    ],
                    [
                        {
                            "text": "📣 Viral $CASHTAG Traffic Kit (X / CMC / TG)",
                            "callback_data": "admin:promo",
                        }
                    ],
                    [
                        {
                            "text": "📌 Post & Pin Official Channel Guide",
                            "callback_data": "admin:pin_guide",
                        },
                        {
                            "text": "🧪 Test Signal + Invoice",
                            "callback_data": "admin:test_here",
                        },
                    ],
                    [{"text": "🔄 Refresh Stats", "callback_data": "admin:panel"}],
                    [{"text": "🔙 Main Menu", "callback_data": "menu:home"}],
                ]
            }
            await self.send_message(chat_id, text, reply_markup=kb)
            return

        if action == "admin:post_now":
            await self.send_message(
                chat_id, "🛰 <b>Scanning live market & posting to channels...</b>"
            )
            sig = await self.generate_and_publish_signal(post_to_channels=True)
            if not sig:
                await self.send_message(chat_id, "⚠️ Market scan returned no signal.")
                return
            promo = build_viral_promo_pack(
                sig,
                public_channel_url="https://t.me/WhaleRadarGlobal",
                bot_username=self.cfg.bot_username or "WhaleAlphaStars_bot",
            )
            await self.send_message(
                chat_id,
                f"✅ <b>Signal <code>{sig['signal_id']}</code> (${sig['symbol']} on {sig['chain']}) posted to Public & VIP Channels!</b>\n\n"
                + promo["admin_message"],
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": f"🐦 Post ${sig['symbol']} Alert on X (Twitter)",
                                "url": promo["x_intent_url"],
                            }
                        ],
                        [
                            {
                                "text": "📤 Share to Telegram Crypto Groups",
                                "url": promo["tg_share_url"],
                            }
                        ],
                        [{"text": "🔙 Admin Panel", "callback_data": "admin:panel"}],
                    ]
                },
            )
            return

        if action == "admin:promo":
            signals = self.db.get_recent_signals(limit=1)
            sig = (
                signals[0]
                if signals
                else await self.generate_and_publish_signal(post_to_channels=False)
            )
            if not sig:
                await self.send_message(chat_id, "⚠️ No signal available.")
                return
            promo = build_viral_promo_pack(
                sig,
                public_channel_url="https://t.me/WhaleRadarGlobal",
                bot_username=self.cfg.bot_username or "WhaleAlphaStars_bot",
            )
            await self.send_message(
                chat_id,
                promo["admin_message"],
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": f"🐦 Post ${sig['symbol']} Alert on X (Twitter)",
                                "url": promo["x_intent_url"],
                            }
                        ],
                        [
                            {
                                "text": "📤 Share to Telegram Crypto Groups",
                                "url": promo["tg_share_url"],
                            }
                        ],
                        [{"text": "🔙 Admin Panel", "callback_data": "admin:panel"}],
                    ]
                },
            )
            return

        if action == "admin:pin_guide":
            if not self.cfg.public_channel_id:
                await self.send_message(chat_id, "⚠️ Public Channel ID not set.")
                return
            guide_text, guide_kb = build_pinned_welcome_post(
                bot_username=self.cfg.bot_username or "WhaleAlphaStars_bot",
                unlock_stars=self.cfg.price_unlock_signal_stars,
                vip_stars=self.cfg.price_vip_monthly_stars,
            )
            sent = await self.send_message(
                self.cfg.public_channel_id, guide_text, reply_markup=guide_kb
            )
            if sent.get("ok"):
                msg_id = sent["result"]["message_id"]
                await self.api_call(
                    "pinChatMessage",
                    {
                        "chat_id": self.cfg.public_channel_id,
                        "message_id": msg_id,
                        "disable_notification": False,
                    },
                )
                await self.send_message(
                    chat_id,
                    "📌 <b>Official Welcome & Methodology Guide published and PINNED in your Public Channel!</b>",
                    reply_markup=self.main_menu_keyboard(user_id),
                )
            return

        if action == "admin:test_here":
            await self.send_message(
                chat_id,
                "🧪 <b>Generating a live market signal & Telegram Stars invoice preview...</b>",
            )
            sig = await self.generate_and_publish_signal(post_to_channels=False)
            if not sig:
                await self.send_message(chat_id, "⚠️ Could not fetch market data.")
                return
            sid = sig["signal_id"]
            await self.send_message(
                chat_id,
                "📢 <b>[PUBLIC CHANNEL TEASER PREVIEW]</b>\n\n" + sig["teaser_text"],
                reply_markup=self.public_channel_keyboard(sid),
            )
            await self.send_stars_invoice(
                chat_id=chat_id,
                title=f"Unlock Whale Signal {sid}",
                description=f"Test unlocking {sid} ({sig['chain']}) with Telegram Stars.",
                payload_str=f"unlock_signal:{sid}",
                stars_amount=self.cfg.price_unlock_signal_stars,
                button_label=f"Unlock {sid}",
            )
            return

        if action.startswith("admin:set_pub:"):
            chan_id = action.split(":", 2)[2]
            self.cfg.public_channel_id = chan_id
            self._persist_env_var("PUBLIC_CHANNEL_ID", chan_id)
            sig = await self.generate_and_publish_signal(post_to_channels=True)
            await self.send_message(
                chat_id,
                f"✅ <b>Public Teaser Channel connected (<code>{chan_id}</code>)!</b>\n"
                f"🚀 First live Whale Signal (<code>{sig['signal_id'] if sig else 'N/A'}</code>) has just been posted to your channel with 50 ⭐ Unlock & 300 ⭐ VIP buttons!",
                reply_markup=self.main_menu_keyboard(user_id),
            )
            return

        if action.startswith("admin:set_vip:"):
            chan_id = action.split(":", 2)[2]
            self.cfg.vip_channel_id = chan_id
            self._persist_env_var("VIP_CHANNEL_ID", chan_id)
            sig = await self.generate_and_publish_signal(post_to_channels=True)
            await self.send_message(
                chat_id,
                f"👑 <b>Private VIP Channel connected (<code>{chan_id}</code>)!</b>\n"
                f"🚀 Full unlocked Alpha Signal (<code>{sig['signal_id'] if sig else 'N/A'}</code>) has been posted to your VIP channel, and automatic 1-time invite links are now active!",
                reply_markup=self.main_menu_keyboard(user_id),
            )
            return

    def _persist_env_var(self, key: str, value: str) -> None:
        env_path = self.cfg.db_path.parent / ".env"
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
            updated = False
            new_lines = []
            for line in lines:
                if line.startswith(f"{key}="):
                    new_lines.append(f"{key}={value}")
                    updated = True
                else:
                    new_lines.append(line)
            if not updated:
                new_lines.append(f"{key}={value}")
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to update .env for %s: %s", key, exc)

    async def handle_my_chat_member(self, event: dict[str, Any]) -> None:
        chat = event.get("chat") or {}
        new_member = event.get("new_chat_member") or {}
        status = str(new_member.get("status") or "")
        if chat.get("type") == "channel" and status == "administrator":
            chan_id = str(chat.get("id"))
            title = str(chat.get("title") or "Channel")
            for admin_id in self.cfg.admin_ids:
                await self.send_message(
                    admin_id,
                    f"📢 <b>New Channel Connected!</b>\n"
                    f"• <b>Title:</b> {html.escape(title)}\n"
                    f"• <b>Channel ID:</b> <code>{chan_id}</code>\n\n"
                    f"👇 <b>How should I use this channel?</b>",
                    reply_markup={
                        "inline_keyboard": [
                            [
                                {
                                    "text": "📢 Set as Public Teaser Channel (Auto-Post Locked Signals)",
                                    "callback_data": f"admin:set_pub:{chan_id}",
                                }
                            ],
                            [
                                {
                                    "text": "👑 Set as Private VIP Channel (Full Signals + Auto Invite Links)",
                                    "callback_data": f"admin:set_vip:{chan_id}",
                                }
                            ],
                        ]
                    },
                )

    async def handle_pre_checkout(self, pre_checkout: dict[str, Any]) -> None:
        query_id = pre_checkout["id"]
        await self.api_call(
            "answerPreCheckoutQuery",
            {"pre_checkout_query_id": query_id, "ok": True},
        )

    async def handle_successful_payment(
        self, chat_id: int, user_id: int, payment: dict[str, Any]
    ) -> None:
        charge_id = str(payment.get("telegram_payment_charge_id") or "")
        provider_charge_id = str(payment.get("provider_payment_charge_id") or "")
        payload_str = str(payment.get("invoice_payload") or "")
        stars_amount = int(payment.get("total_amount") or 0)

        parts = payload_str.split(":", 1)
        item_type = parts[0]
        item_ref = parts[1] if len(parts) > 1 else ""

        self.db.record_payment(
            user_id=user_id,
            telegram_payment_charge_id=charge_id,
            provider_payment_charge_id=provider_charge_id,
            payload=payload_str,
            item_type=item_type,
            item_ref=item_ref,
            stars_amount=stars_amount,
        )

        # 1) Single Signal Unlock (50 ⭐)
        if item_type == "unlock_signal":
            signal_id = item_ref
            self.db.unlock_signal(user_id, signal_id)
            sig = self.db.get_signal(signal_id)
            if sig:
                await self.send_message(
                    chat_id,
                    f"🎉 <b>Payment Confirmed ({stars_amount} ⭐)!</b>\n\n"
                    + sig["full_text"],
                    reply_markup=self.main_menu_keyboard(user_id),
                )
            else:
                self.db.add_credits(user_id, 1)
                await self.send_message(
                    chat_id,
                    f"🎉 <b>Payment Confirmed ({stars_amount} ⭐)!</b>\n"
                    "We credited +1 Signal Unlock to your account.",
                    reply_markup=self.main_menu_keyboard(user_id),
                )

        # 2) 30-Day VIP Subscription (300 ⭐)
        elif item_type == "vip_30d":
            new_until = self.db.extend_vip(user_id, days=30)
            exp_date = datetime.fromtimestamp(new_until, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
            invite_line = ""
            if self.cfg.vip_channel_id:
                inv_res = await self.api_call(
                    "createChatInviteLink",
                    {
                        "chat_id": self.cfg.vip_channel_id,
                        "name": f"VIP_{user_id}",
                        "expire_date": new_until,
                        "member_limit": 1,
                    },
                )
                if inv_res.get("ok"):
                    invite_url = inv_res["result"]["invite_link"]
                    invite_line = (
                        f"\n🔐 <b>Your Personal 1-Time VIP Channel Link:</b>\n"
                        f"👉 <a href=\"{html.escape(invite_url)}\">Click Here to Join Private VIP Channel</a>\n"
                    )

            await self.send_message(
                chat_id,
                f"👑 <b>WELCOME TO VIP ALL-ACCESS! ({stars_amount} ⭐ Confirmed)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>VIP Valid Until:</b> <code>{exp_date}</code>\n"
                f"✅ All locked signals & token security audits inside this bot are now <b>100% UNLOCKED</b> for you!\n"
                f"{invite_line}",
                reply_markup=self.main_menu_keyboard(user_id),
            )

        # 3) 5x Credit Pack (25 ⭐)
        elif item_type == "scan_pack":
            new_total = self.db.add_credits(user_id, 5)
            await self.send_message(
                chat_id,
                f"⚡ <b>+5 Universal Credits Added! ({stars_amount} ⭐ Confirmed)</b>\n"
                f"🎁 Your Credit Balance: <code>{new_total}</code>",
                reply_markup=self.main_menu_keyboard(user_id),
            )

        # Notify Admins of the sale!
        for admin_id in self.cfg.admin_ids:
            await self.send_message(
                admin_id,
                f"💰 <b>NEW TELEGRAM STARS SALE! (+{stars_amount} ⭐)</b>\n"
                f"• <b>Buyer ID:</b> <code>{user_id}</code>\n"
                f"• <b>Item:</b> <code>{html.escape(payload_str)}</code>\n"
                f"• <b>Charge ID:</b> <code>{html.escape(charge_id)}</code>",
            )

    async def handle_text_message(self, msg: dict[str, Any]) -> None:
        chat_id = int(msg["chat"]["id"])
        from_user = msg.get("from") or {}
        user_id = int(from_user.get("id") or chat_id)
        username = str(from_user.get("username") or "")
        first_name = str(from_user.get("first_name") or "")
        text = str(msg.get("text") or "").strip()

        if not text:
            return

        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 else ""
            await self.handle_start(chat_id, user_id, username, first_name, arg)
            return

        self.db.upsert_user(user_id, username, first_name)

        if text.startswith("/admin") and user_id in self.cfg.admin_ids:
            await self.handle_admin_action(chat_id, user_id, "admin:panel")
            return

        if text.startswith("/post") and user_id in self.cfg.admin_ids:
            await self.handle_admin_action(chat_id, user_id, "admin:post_now")
            return

        if text.startswith("/refund") and user_id in self.cfg.admin_ids:
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await self.send_message(
                    chat_id, "Usage: <code>/refund CHARGE_ID [USER_ID]</code>"
                )
                return
            subparts = parts[1].split()
            charge_id = subparts[0].strip()
            target_uid = int(subparts[1]) if len(subparts) > 1 else user_id
            res = await self.api_call(
                "refundStarPayment",
                {
                    "user_id": target_uid,
                    "telegram_payment_charge_id": charge_id,
                },
            )
            if res.get("ok"):
                self.db.mark_payment_refunded(charge_id)
                await self.send_message(
                    chat_id,
                    f"✅ <b>Stars Payment Refunded Successfully!</b>\nCharge ID: <code>{html.escape(charge_id)}</code>",
                )
            else:
                await self.send_message(
                    chat_id,
                    f"⚠️ Refund failed: <code>{html.escape(str(res.get('description')))}</code>",
                )
            return

        chat_type = str((msg.get("chat") or {}).get("type") or "private")

        if text.startswith("/vip"):
            await self.send_vip_offer(chat_id, user_id)
            return

        if text.startswith("/arb"):
            report = await self.scanner.scan_cex_arbitrage()
            await self.send_message(
                chat_id,
                report,
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "🐋 Join @WhaleRadarGlobal (24/7 Feed)", "url": "https://t.me/WhaleRadarGlobal"}],
                        [{"text": "🎁 Claim 1 Free VIP Signal Unlock", "url": "https://t.me/WhaleAlphaStars_bot?start=welcome_gift"}],
                    ]
                },
            )
            return

        # Group Chat Viral Mode: in groups/supergroups, only respond to explicit /scan, /audit, /whale or @bot mentions
        if chat_type in ("group", "supergroup"):
            lower_text = text.lower()
            if lower_text.startswith(("/scan", "/audit", "/whale")):
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    await self.send_message(
                        chat_id,
                        "🔎 <b>Usage:</b> <code>/scan PEPE</code> or <code>/scan &lt;contract_address&gt;</code>",
                        reply_markup={
                            "inline_keyboard": [
                                [{"text": "🐋 Join @WhaleRadarGlobal", "url": "https://t.me/WhaleRadarGlobal"}]
                            ]
                        },
                    )
                    return
                text = parts[1].strip()
            elif f"@{(self.cfg.bot_username or 'WhaleAlphaStars_bot').lower()}" in lower_text:
                text = (
                    text.replace(f"@{self.cfg.bot_username}", "")
                    .replace("@WhaleAlphaStars_bot", "")
                    .strip()
                )
            else:
                return
        elif text.lower().startswith(("/scan", "/audit")):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await self.send_message(
                    chat_id,
                    "💡 Send a single <b>Token Symbol</b> (e.g. <code>PEPE</code>, <code>SOL</code>) or a <b>Contract Address</b> to run an On-Chain Whale & Security Audit.",
                    reply_markup=self.main_menu_keyboard(user_id),
                )
                return
            text = parts[1].strip()

        # Otherwise treat text as a token ticker or contract address scan request!
        if len(text) > 64 or " " in text or not text:
            if chat_type == "private":
                await self.send_message(
                    chat_id,
                    "💡 Send a single <b>Token Symbol</b> (e.g. <code>PEPE</code>, <code>SOL</code>) or a <b>Contract Address</b> to run an On-Chain Whale & Security Audit.",
                    reply_markup=self.main_menu_keyboard(user_id),
                )
            return

        if chat_type == "private":
            can_free = self.db.check_and_consume_free_scan(
                user_id, self.cfg.free_daily_scans
            )
            if not can_free:
                user = self.db.get_user(user_id) or {}
                credits = int(user.get("credits") or 0)
                if credits > 0:
                    self.db.add_credits(user_id, -1)
                else:
                    await self.send_message(
                        chat_id,
                        f"🔒 <b>Daily Free Scan Limit Reached ({self.cfg.free_daily_scans}/{self.cfg.free_daily_scans})</b>\n\n"
                        f"Unlock <b>5x Deep Scans & Signal Credits ({self.cfg.price_deep_scan_stars} ⭐)</b> or upgrade to <b>Unlimited VIP ({self.cfg.price_vip_monthly_stars} ⭐/mo)</b>:",
                    )
                    await self.send_stars_invoice(
                        chat_id=chat_id,
                        title="5x Whale Unlock & Audit Credits",
                        description="Run 5 on-demand Token Security & Whale Orderflow Audits or Signal Unlocks.",
                        payload_str="scan_pack:5",
                        stars_amount=self.cfg.price_deep_scan_stars,
                        button_label="Unlock 5 Credits",
                    )
                    return

        await self.send_message(
            chat_id,
            f"🔍 <b>Auditing <code>{html.escape(text.upper())}</code> across DEX pools & security registries...</b>",
        )
        res = await self.scanner.scan_custom_token(text)
        if not res:
            await self.send_message(
                chat_id,
                f"⚠️ No active DEX liquidity pool found for <code>{html.escape(text)}</code>.",
                reply_markup=self.main_menu_keyboard(user_id) if chat_type == "private" else None,
            )
            return

        group_kb = {
            "inline_keyboard": [
                [{"text": "🐋 Join @WhaleRadarGlobal (24/7 Whale Feed)", "url": "https://t.me/WhaleRadarGlobal"}],
                [{"text": "🎁 Claim 1 Free VIP Signal Unlock", "url": "https://t.me/WhaleAlphaStars_bot?start=welcome_gift"}],
            ]
        }
        await self.send_message(
            chat_id,
            res["report"],
            reply_markup=self.main_menu_keyboard(user_id) if chat_type == "private" else group_kb,
        )

    async def check_and_broadcast_winner_recap(self) -> bool:
        """
        Checks recent signals in SQLite against live DexScreener prices.
        When a signal gains +10% or more since our entry alert, broadcasts a verified
        On-Chain Performance Recap to the public channel to drive VIP conversions.
        """
        if not self.cfg.public_channel_id:
            return False
        if not hasattr(self, "_announced_winners"):
            self._announced_winners: set[str] = set()

        signals = self.db.get_recent_signals(limit=20)
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        session = self._session
        for s in signals:
            sid = s["signal_id"]
            if sid in self._announced_winners:
                continue
            addr = s.get("token_address") or ""
            try:
                entry = float(s.get("price_usd") or 0)
            except Exception:
                continue
            if not addr or entry <= 0:
                continue
            try:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{addr}"
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                pairs = data.get("pairs") or []
                if not pairs:
                    continue
                cur = float(pairs[0].get("priceUsd") or 0)
                if cur <= 0:
                    continue
                gain_pct = ((cur - entry) / entry) * 100.0
                if gain_pct >= 10.0:
                    self._announced_winners.add(sid)
                    sym = html.escape(str(s.get("symbol") or "TOKEN"))
                    chain = html.escape(str(s.get("chain") or "SOLANA"))
                    dex_url = str(s.get("dex_url") or f"https://dexscreener.com/{chain.lower()}/{addr}")
                    recap_text = (
                        f"🎯 <b>[VERIFIED DESK PERFORMANCE] +<code>{gain_pct:.1f}%</code> GAIN</b>\n"
                        f"Ref: <code>{sid}</code> ({chain})\n"
                        f"──────────────────────\n"
                        f"• <b>Asset Revealed:</b> <b>${sym}</b> (<code>{html.escape(addr)}</code>)\n"
                        f"• <b>Radar Entry Price:</b> <code>${entry:.6g}</code>\n"
                        f"• <b>Current DEX Price:</b> <code>${cur:.6g}</code> (<b>+{gain_pct:.1f}%</b>)\n"
                        f"• <b>Verification:</b> <a href=\"{html.escape(dex_url)}\">Live DexScreener Chart</a>\n"
                        f"──────────────────────\n"
                        f"<i>VIP members received the unmasked contract & entry levels at 0-second latency. Unlock our latest live signal or join VIP below:</i>"
                    )
                    kb = {
                        "inline_keyboard": [
                            [{"text": "🎁 Claim 1 Free Signal Unlock Credit", "url": "https://t.me/WhaleAlphaStars_bot?start=welcome_gift"}],
                            [{"text": f"👑 Join 24/7 VIP Instant Feed ({self.cfg.price_vip_monthly_stars} ⭐/mo)", "url": "https://t.me/WhaleAlphaStars_bot?start=vip"}],
                        ]
                    }
                    await self.send_message(self.cfg.public_channel_id, recap_text, reply_markup=kb)
                    return True
            except Exception:
                continue
        return False

    async def auto_poster_loop(self) -> None:
        interval_sec = max(300, self.cfg.auto_post_interval_minutes * 60)
        logger.info(
            "24/7 Channel Auto-Poster active (interval: %d min)",
            self.cfg.auto_post_interval_minutes,
        )
        # Check when the last signal was created so restarts don't double-post immediately
        recent = self.db.get_recent_signals(limit=1)
        if recent:
            elapsed = int(time.time()) - int(recent[0]["created_at"])
            if 0 <= elapsed < interval_sec:
                wait_initial = interval_sec - elapsed
                logger.info(
                    "Last signal was %ds ago; waiting %ds before next auto-post",
                    elapsed,
                    wait_initial,
                )
                await asyncio.sleep(wait_initial)

        while True:
            try:
                if self.cfg.public_channel_id or self.cfg.vip_channel_id:
                    try:
                        await self.check_and_broadcast_winner_recap()
                    except Exception as rexc:
                        logger.error("Winner recap error: %s", rexc)
                    sig = await self.generate_and_publish_signal(post_to_channels=True)
                    if sig:
                        logger.info(
                            "Auto-posted Whale Signal %s ($%s on %s)",
                            sig["signal_id"],
                            sig["symbol"],
                            sig["chain"],
                        )
            except Exception as exc:
                logger.error("Auto-poster error: %s", exc)
            await asyncio.sleep(interval_sec)

    async def run(self) -> None:
        if not self.cfg.bot_token:
            logger.error(
                "BOT_TOKEN is empty! Please set BOT_TOKEN in .env or environment."
            )
            return

        me = await self.api_call("getMe")
        if not me.get("ok"):
            logger.error("Invalid BOT_TOKEN! getMe failed: %s", me)
            return

        bot_info = me["result"]
        if not self.cfg.bot_username:
            self.cfg.bot_username = bot_info.get("username", "")

        max_runtime = int(os.getenv("MAX_RUNTIME_SECONDS", "0"))
        start_ts = time.time()

        logger.info(
            "✅ WhaleRadarBot (@%s) is LIVE and accepting Telegram Stars (XTR)! (max_runtime=%ds)",
            self.cfg.bot_username,
            max_runtime,
        )

        # Warm up with 1 initial live signal in DB
        if not self.db.get_recent_signals(limit=1):
            logger.info("Fetching initial live Whale Accumulation signal...")
            await self.generate_and_publish_signal(post_to_channels=False)

        poster_task = asyncio.create_task(self.auto_poster_loop())

        try:
            while True:
                if max_runtime > 0 and (time.time() - start_ts) >= max_runtime:
                    logger.info(
                        "Reached MAX_RUNTIME_SECONDS (%ds). Saving state & exiting cleanly for cloud handoff.",
                        max_runtime,
                    )
                    break

                try:
                    res = await self.api_call(
                        "getUpdates",
                        {
                            "offset": self._offset,
                            "timeout": 20,
                            "allowed_updates": [
                                "message",
                                "callback_query",
                                "pre_checkout_query",
                                "my_chat_member",
                            ],
                        },
                    )
                    if not res.get("ok"):
                        await asyncio.sleep(3)
                        continue

                    for upd in res.get("result", []):
                        self._offset = int(upd["update_id"]) + 1

                        if "my_chat_member" in upd:
                            await self.handle_my_chat_member(upd["my_chat_member"])
                            continue

                        if "pre_checkout_query" in upd:
                            await self.handle_pre_checkout(upd["pre_checkout_query"])
                            continue

                        if "callback_query" in upd:
                            await self.handle_callback(upd["callback_query"])
                            continue

                        if "message" in upd:
                            msg = upd["message"]
                            if "successful_payment" in msg:
                                chat_id = int(msg["chat"]["id"])
                                user_id = int(
                                    (msg.get("from") or {}).get("id") or chat_id
                                )
                                await self.handle_successful_payment(
                                    chat_id, user_id, msg["successful_payment"]
                                )
                            elif "text" in msg:
                                await self.handle_text_message(msg)
                except Exception as exc:
                    logger.error("Polling loop error: %s", exc)
                    await asyncio.sleep(3)
        finally:
            poster_task.cancel()
            if self._session and not self._session.closed:
                await self._session.close()


if __name__ == "__main__":
    cfg = load_config()
    database = Database(cfg.db_path)
    market_scanner = MarketScanner()
    bot = WhaleRadarBot(cfg, database, market_scanner)
    asyncio.run(bot.run())
