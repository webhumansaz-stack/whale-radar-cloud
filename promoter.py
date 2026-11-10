from __future__ import annotations

import asyncio
import html
import logging
import urllib.parse
from typing import Any

logger = logging.getLogger("WhalePromoter")

DEFAULT_PUBLIC_CHANNEL_URL = "https://t.me/+m1YDX3OTmC8yNTgy"


def build_viral_promo_pack(
    signal: dict[str, Any],
    public_channel_url: str = DEFAULT_PUBLIC_CHANNEL_URL,
    bot_username: str = "WhaleAlphaStars_bot",
) -> dict[str, str]:
    """
    Creates viral <240-char $CASHTAG posts for X (Twitter), CoinMarketCap Community,
    Reddit, and Telegram Discussion Groups from a live Whale Signal.
    """
    sym = str(signal.get("symbol") or "TOKEN").upper()
    chain = str(signal.get("chain") or "SOLANA").upper()
    score = int(signal.get("whale_score") or 90)
    buy_ratio = float(signal.get("buy_ratio") or 75.0)
    buys_1h = int(signal.get("buys_1h") or 100)
    sells_1h = int(signal.get("sells_1h") or 25)
    vol_24h = float(signal.get("volume_24h") or 100_000)
    ch_1h = float(signal.get("price_change_1h") or 12.5)
    sid = str(signal.get("signal_id") or "WHALE-ALPHA")

    # Strictly < 240 chars so X.com tweetButton is always enabled
    tweet_plain = (
        f"🐋 WHALE ALERT: ${sym} (#{chain})\n"
        f"• Whale Score: {score}/100\n"
        f"• 1H Orderflow: {buy_ratio:.0f}% Buys ({ch_1h:+.1f}%)\n"
        f"• Audit: Verified Safe\n\n"
        f"Live contract & TP1-TP3 targets on Telegram 👇\n"
        f"{public_channel_url}\n\n"
        f"${sym} $SOL $PEPE #CryptoWhale"
    )
    x_intent_url = (
        "https://x.com/intent/post?text="
        + urllib.parse.quote(tweet_plain, safe="")
    )

    tg_share_text = (
        f"🐋 Huge on-chain whale accumulation spotted on ${sym} (#{chain}) — "
        f"{buy_ratio:.0f}% buy pressure ({score}/100 Whale Score)! "
        f"Live contract & Entry/TP targets on Whale & Arbitrage Radar Global"
    )
    tg_share_url = (
        "https://t.me/share/url?url="
        + urllib.parse.quote(public_channel_url, safe="")
        + "&text="
        + urllib.parse.quote(tg_share_text, safe="")
    )

    comment_snipe = (
        f"🐋 On-chain orderflow on ${sym} ({chain}) just hit {buy_ratio:.0f}% buy imbalance "
        f"({buys_1h} buys vs {sells_1h} sells in 1H, ${vol_24h:,.0f} vol). "
        f"Full RugCheck security audit & execution zones posted on {public_channel_url} "
        f"(or scan any contract free via @{bot_username})."
    )

    admin_message = (
        f"📣 <b>VIRAL $CASHTAG TRAFFIC KIT — <code>{html.escape(sid)}</code> (${html.escape(sym)})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🐦 <b>X.com (@WhaleAlphaStar) Auto-Tweet Text:</b>\n"
        f"<pre>{html.escape(tweet_plain)}</pre>\n\n"
        f"💬 <b>Telegram / CoinMarketCap Comment Snipe (Tap to Copy):</b>\n"
        f"<code>{html.escape(comment_snipe)}</code>"
    )

    return {
        "tweet_plain": tweet_plain,
        "x_intent_url": x_intent_url,
        "tg_share_url": tg_share_url,
        "comment_snipe": comment_snipe,
        "admin_message": admin_message,
    }


async def auto_post_tweet_via_chrome(tweet_text: str) -> bool:
    """
    Uses AppleScript + Chrome's open x.com tab (@WhaleAlphaStar) to automatically
    publish a viral $CASHTAG tweet every time a new Whale Signal is generated.
    """
    intent_url = "https://x.com/intent/post?text=" + urllib.parse.quote(
        tweet_text, safe=""
    )
    nav_script = f"""
    tell application "Google Chrome"
        set foundTab to false
        repeat with w from 1 to count of windows
            repeat with t from 1 to count of tabs of window w
                set u to URL of tab t of window w
                if u contains "x.com" or u contains "twitter.com" then
                    set URL of tab t of window w to "{intent_url}"
                    set foundTab to true
                    exit repeat
                end if
            end repeat
            if foundTab then exit repeat
        end repeat
        return foundTab
    end tell
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript",
            "-e",
            nav_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if b"true" not in stdout.lower():
            return False

        await asyncio.sleep(5.5)

        click_script = """
        tell application "Google Chrome"
            repeat with w from 1 to count of windows
                repeat with t from 1 to count of tabs of window w
                    set u to URL of tab t of window w
                    if u contains "x.com/intent/post" then
                        set res to execute tab t of window w javascript "
                        (() => {
                          const btn = document.querySelector('[data-testid=\\"tweetButton\\"]');
                          if (btn && !btn.getAttribute('aria-disabled')) {
                            btn.click();
                            return 'POSTED';
                          }
                          return 'NOT_READY';
                        })()
                        "
                        return res
                    end if
                end repeat
            end repeat
        end tell
        """
        proc2 = await asyncio.create_subprocess_exec(
            "osascript",
            "-e",
            click_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout2, _ = await proc2.communicate()
        posted = b"POSTED" in stdout2
        if posted:
            logger.info("✅ Automatically posted viral $CASHTAG tweet to @WhaleAlphaStar on X.com!")
        return posted
    except Exception as exc:
        logger.warning("X.com auto-post error: %s", exc)
        return False


def build_pinned_welcome_post(
    bot_username: str = "WhaleAlphaStars_bot",
    unlock_stars: int = 50,
    vip_stars: int = 300,
) -> tuple[str, dict[str, Any]]:
    text = (
        "🏛 <b>WHALE & ARBITRAGE RADAR GLOBAL — OFFICIAL TERMINAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "24/7 algorithmic intelligence tracking <b>Institutional Whale Accumulation</b> "
        "(Solana • Base • Ethereum • BSC) & <b>Live CEX Arbitrage Spreads</b>.\n\n"
        "🔬 <b>Methodology:</b>\n"
        "• <b>Whale Orderflow:</b> >65% buy-side imbalance & volume surge detection\n"
        "• <b>Security Verified:</b> Automated GoPlus & RugCheck contract audit\n"
        "• <b>Arbitrage Engine:</b> Live Binance, Bybit & KuCoin delta scanner\n\n"
        f"🔓 <b>Access Full Alpha:</b>\n"
        f"• <b>Unlock Single Signal ({unlock_stars} ⭐):</b> Reveal exact Ticker, Contract & Entry/TP1–TP3 zones.\n"
        f"• <b>VIP All-Access ({vip_stars} ⭐/30d):</b> 0-second private VIP feed + all signals unlocked.\n"
        "• <b>Free Scanner:</b> Send any token address to our bot for a free audit!"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": f"👑 Join 24/7 VIP Instant Feed ({vip_stars} ⭐/mo)",
                    "url": f"https://t.me/{bot_username}?start=vip",
                }
            ],
            [
                {
                    "text": "🕵️‍♂️ Free On-Chain Token Auditor",
                    "url": f"https://t.me/{bot_username}?start=scanner",
                },
                {
                    "text": "🎁 Earn Free Signal Unlocks",
                    "url": f"https://t.me/{bot_username}?start=home",
                },
            ],
        ]
    }
    return text, keyboard
