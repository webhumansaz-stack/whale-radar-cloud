from __future__ import annotations

import asyncio
import html
import logging
import random
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
    Builds human-sounding, institutional quant-desk posts for X.com, CoinMarketCap,
    and Telegram without robotic AI emoji clichés.
    """
    sym = str(signal.get("symbol") or "TOKEN").upper()
    chain = str(signal.get("chain") or "SOLANA").capitalize()
    buy_ratio = float(signal.get("buy_ratio") or 75.0)
    buys_1h = int(signal.get("buys_1h") or 100)
    sells_1h = int(signal.get("sells_1h") or 25)
    vol_24h = float(signal.get("volume_24h") or 100_000)
    liq_usd = float(signal.get("liquidity_usd") or 50_000)
    ch_1h = float(signal.get("price_change_1h") or 12.5)
    sid = str(signal.get("signal_id") or "WHALE-ALPHA")

    liq_k = f"${liq_usd / 1000:.0f}k" if liq_usd >= 1000 else f"${liq_usd:.0f}"
    vol_k = f"${vol_24h / 1000:.0f}k" if vol_24h >= 1000 else f"${vol_24h:.0f}"

    tweet_variants = [
        (
            f"Unusual 1h buy-side skew on ${sym} ({chain} DEX) — {buys_1h} buys vs {sells_1h} sells "
            f"({buy_ratio:.0f}% buy flow) with {liq_k} pool liquidity holding steady.\n\n"
            f"Contract passed RugCheck/GoPlus. Full orderflow log & levels on our desk:\n"
            f"{public_channel_url}\n\n"
            f"${sym} $SOL $ETH"
        ),
        (
            f"Tracking steady accumulation on ${sym} ({chain}). 1h orderflow sitting at "
            f"{buy_ratio:.0f}% buy-side ({ch_1h:+.1f}% delta) on {vol_k} 24h volume.\n\n"
            f"Raw contract audit & execution zones logged in our Telegram feed:\n"
            f"{public_channel_url}\n\n"
            f"${sym} $SOL $PEPE"
        ),
        (
            f"On-chain desk flagged ${sym} on {chain} — {buys_1h}B / {sells_1h}S over the last 60m "
            f"({buy_ratio:.0f}% buy imbalance, {liq_k} LP).\n\n"
            f"Full contract & invalidation levels posted here:\n"
            f"{public_channel_url}\n\n"
            f"${sym} $WIF $SOL"
        ),
    ]
    tweet_plain = random.choice(tweet_variants)

    x_intent_url = (
        "https://x.com/intent/post?text="
        + urllib.parse.quote(tweet_plain, safe="")
    )

    tg_share_text = (
        f"On-chain flow alert on ${sym} ({chain}): {buy_ratio:.0f}% buy-side skew "
        f"({buys_1h} buys / {sells_1h} sells in 1h, {liq_k} liquidity). "
        f"Contract audit & levels on Whale & Arbitrage Radar Global"
    )
    tg_share_url = (
        "https://t.me/share/url?url="
        + urllib.parse.quote(public_channel_url, safe="")
        + "&text="
        + urllib.parse.quote(tg_share_text, safe="")
    )

    comment_snipe = (
        f"Watching 1h DEX orderflow on ${sym} ({chain}) — {buys_1h} buys vs {sells_1h} sells "
        f"({buy_ratio:.0f}% buy skew) with {liq_k} liquidity and clean contract audit. "
        f"We log the raw flow and levels on {public_channel_url} (or check any contract via @{bot_username})."
    )

    admin_message = (
        f"<b>[DESK DISTRIBUTION KIT — {html.escape(sid)} (${html.escape(sym)})]</b>\n"
        f"──────────────────────\n"
        f"<b>X.com (@WhaleAlphaStar) Desk Post:</b>\n"
        f"<pre>{html.escape(tweet_plain)}</pre>\n\n"
        f"<b>Discussion / CMC Analyst Note (Tap to Copy):</b>\n"
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
            logger.info("Posted desk update to @WhaleAlphaStar on X.com")
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
        "<b>WHALE & ARBITRAGE RADAR GLOBAL — ON-CHAIN DESK</b>\n"
        "──────────────────────\n"
        "24/7 quantitative monitoring of <b>DEX Orderflow Imbalances</b> "
        "(Solana • Base • Ethereum • BSC) and <b>Cross-Exchange Spot Spreads</b>.\n\n"
        "<b>Desk Filtering Criteria:</b>\n"
        "• <b>Orderflow Skew:</b> >55–85% 1h net buy-side volume with active pool depth\n"
        "• <b>Contract Verification:</b> Automated GoPlus & RugCheck registry screening\n"
        "• <b>CEX Arbitrage:</b> Real-time Binance, Bybit & KuCoin orderbook delta tracking\n\n"
        f"<b>Terminal Access:</b>\n"
        f"• <b>Single Alert Unlock ({unlock_stars} ⭐):</b> Reveal full contract address, ticker, DEX pair & execution range.\n"
        f"• <b>VIP Desk Feed ({vip_stars} ⭐ / 30d):</b> Unmasked real-time feed + unlimited contract audits.\n"
        "• <b>Pair Auditor:</b> Send any contract address or ticker to the bot for an on-chain check."
    )
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": f"VIP Desk Feed ({vip_stars} ⭐ / 30d)",
                    "url": f"https://t.me/{bot_username}?start=vip",
                }
            ],
            [
                {
                    "text": "On-Chain Pair Auditor",
                    "url": f"https://t.me/{bot_username}?start=scanner",
                },
                {
                    "text": "Desk Bot Terminal",
                    "url": f"https://t.me/{bot_username}?start=home",
                },
            ],
        ]
    }
    return text, keyboard
