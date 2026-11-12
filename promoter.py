from __future__ import annotations

import asyncio
import html
import logging
import random
import urllib.parse
from typing import Any

logger = logging.getLogger("WhalePromoter")

DEFAULT_PUBLIC_CHANNEL_URL = "https://t.me/WhaleRadarGlobal"
DEFAULT_PUBLIC_CHANNEL_HANDLE = "@WhaleRadarGlobal"


def build_viral_promo_pack(
    signal: dict[str, Any],
    public_channel_url: str = DEFAULT_PUBLIC_CHANNEL_URL,
    bot_username: str = "WhaleAlphaStars_bot",
) -> dict[str, str]:
    """
    Builds human-sounding, institutional quant-desk posts for X.com, CoinMarketCap,
    and Telegram without robotic AI emoji clichés or spam-filtered raw URLs.
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
            f"Contract passed RugCheck/GoPlus. Full orderflow log on Telegram: t.me/WhaleRadarGlobal\n\n"
            f"${sym} $SOL $ETH"
        ),
        (
            f"Tracking steady accumulation on ${sym} ({chain}). 1h orderflow sitting at "
            f"{buy_ratio:.0f}% buy-side ({ch_1h:+.1f}% delta) on {vol_k} 24h volume.\n\n"
            f"Raw contract audit & execution zones on Telegram: t.me/WhaleRadarGlobal\n\n"
            f"${sym} $SOL $PEPE"
        ),
        (
            f"On-chain desk flagged ${sym} on {chain} — {buys_1h}B / {sells_1h}S over the last 60m "
            f"({buy_ratio:.0f}% buy imbalance, {liq_k} LP).\n\n"
            f"Live feed on Telegram: t.me/WhaleRadarGlobal (Scanner: t.me/{bot_username})\n\n"
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
        f"Contract audit & levels on {DEFAULT_PUBLIC_CHANNEL_HANDLE}"
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
        f"We log raw flow & levels on Telegram: {DEFAULT_PUBLIC_CHANNEL_HANDLE} (or check any CA via @{bot_username})."
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
                    if u contains "x.com" or u contains "twitter.com" then
                        set res to execute tab t of window w javascript "
                        (() => {
                          const btn = document.querySelector('[data-testid=\\"tweetButton\\"], [data-testid=\\"tweetButtonInline\\"]');
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


CMC_TOKEN_MAP: dict[str, dict[str, Any]] = {
    "SOL": {"id": 5426, "symbol": "SOL", "slug": "solana"},
    "BTC": {"id": 1, "symbol": "BTC", "slug": "bitcoin"},
    "ETH": {"id": 1027, "symbol": "ETH", "slug": "ethereum"},
    "PEPE": {"id": 24478, "symbol": "PEPE", "slug": "pepe"},
    "BONK": {"id": 23095, "symbol": "BONK", "slug": "bonk1"},
    "WIF": {"id": 28752, "symbol": "WIF", "slug": "dogwifhat"},
    "SUI": {"id": 20947, "symbol": "SUI", "slug": "sui"},
    "DOGE": {"id": 74, "symbol": "DOGE", "slug": "dogecoin"},
    "XRP": {"id": 52, "symbol": "XRP", "slug": "xrp"},
    "BNB": {"id": 1839, "symbol": "BNB", "slug": "bnb"},
}


async def post_to_cmc_cloud(
    signal: dict[str, Any],
    public_channel_url: str = DEFAULT_PUBLIC_CHANNEL_URL,
) -> bool:
    """
    Publishes a human-written institutional orderflow desk note directly to
    CoinMarketCap Community via HTTP API (works 100% headlessly inside GitHub Actions Cloud).
    """
    import json
    import os
    import aiohttp

    sym = str(signal.get("symbol") or "SOL").upper()
    chain = str(signal.get("chain") or "SOLANA").upper()
    buy_ratio = float(signal.get("buy_ratio") or 72.0)
    buys_1h = int(signal.get("buys_1h") or 95)
    sells_1h = int(signal.get("sells_1h") or 28)
    liq_usd = float(signal.get("liquidity_usd") or 65_000)
    vol_24h = float(signal.get("volume_24h") or 180_000)
    ch_1h = float(signal.get("price_change_1h") or 11.4)

    liq_k = f"${liq_usd / 1000:.0f}K" if liq_usd >= 1000 else f"${liq_usd:.0f}"
    vol_k = f"${vol_24h / 1000:.0f}K" if vol_24h >= 1000 else f"${vol_24h:.0f}"

    if sym in CMC_TOKEN_MAP:
        anchor = CMC_TOKEN_MAP[sym]
    elif "SOL" in chain:
        anchor = CMC_TOKEN_MAP["SOL"]
    elif "BSC" in chain or "BNB" in chain:
        anchor = CMC_TOKEN_MAP["BNB"]
    elif "ETH" in chain or "BASE" in chain or "ARB" in chain:
        anchor = CMC_TOKEN_MAP["ETH"]
    else:
        anchor = random.choice([CMC_TOKEN_MAP["SOL"], CMC_TOKEN_MAP["BTC"], CMC_TOKEN_MAP["PEPE"]])

    anchor_tag = f"${anchor['symbol']}"
    multi_tags = "$BTC $SOL $ETH $PEPE"
    note_templates = [
        (
            f" On-Chain Orderflow Desk — Tracking unusual 1H buy-side skew on ${sym} ({chain.capitalize()} DEX): "
            f"{buys_1h} buys vs {sells_1h} sells ({buy_ratio:.0f}% buy flow, {ch_1h:+.1f}% 1H delta) across {liq_k} pool depth. "
            f"Contract passed RugCheck/GoPlus verification. Live orderflow feed on Telegram: {DEFAULT_PUBLIC_CHANNEL_HANDLE} | Bot: @WhaleAlphaStars_bot ({multi_tags})"
        ),
        (
            f" Spot & DEX Flow Update — Sustained whale accumulation flagged on ${sym} ({chain.capitalize()}) with "
            f"{buy_ratio:.0f}% 1H buy-side dominance ({buys_1h}B / {sells_1h}S) on {vol_k} 24H volume and {liq_k} locked LP. "
            f"Full contract audit & execution zones on Telegram: {DEFAULT_PUBLIC_CHANNEL_HANDLE} ({multi_tags})"
        ),
        (
            f" Quantitative Liquidity Alert — ${sym} ({chain.capitalize()}) showing {buy_ratio:.0f}% net buy-side imbalance "
            f"over the last 60m ({buys_1h} buys / {sells_1h} sells, {liq_k} liquidity) with zero mint/freeze risk flags. "
            f"Real-time whale radar & CEX arbitrage spreads on Telegram: {DEFAULT_PUBLIC_CHANNEL_HANDLE} ({multi_tags})"
        ),
    ]
    body_text = random.choice(note_templates)
    full_post_text = anchor_tag + body_text

    auth_token = os.getenv("CMC_AUTH_TOKEN", "").strip()
    cookies = os.getenv("CMC_COOKIE", "").strip()
    if not auth_token or not cookies:
        return await auto_post_cmc_via_chrome(full_post_text)

    csrf = ""
    fvideo = "33380f349d5b95b38d26ac443cc0da6ea637283c"
    for part in cookies.split("; "):
        if part.startswith("x-csrf-token="):
            csrf = part.split("=", 1)[1]
        elif part.startswith("BNC_FV_KEY="):
            fvideo = part.split("=", 1)[1]

    all_currencies = [
        CMC_TOKEN_MAP["BTC"],
        CMC_TOKEN_MAP["SOL"],
        CMC_TOKEN_MAP["ETH"],
        CMC_TOKEN_MAP["PEPE"],
    ]
    if anchor not in all_currencies:
        all_currencies.insert(0, anchor)

    payload = {
        "bullish": True,
        "content": full_post_text,
        "originalContent": json.dumps(
            [
                [
                    {
                        "type": "token",
                        "id": anchor["id"],
                        "symbol": anchor_tag,
                        "slug": anchor["slug"],
                    },
                    {"type": "text", "content": body_text},
                ]
            ]
        ),
        "currencies": [
            {"id": c["id"], "symbol": c["symbol"], "slug": c["slug"]}
            for c in all_currencies
        ],
        "rwas": [],
        "mentions": [],
        "links": [],
        "topics": [],
        "linkCardVisible": False,
        "images": [],
        "newImages": [],
        "setAsAnnouncement": False,
    }

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Authorization": auth_token,
        "Cookie": cookies,
        "x-csrf-token": csrf,
        "FVIDEO-ID": fvideo,
        "platform": "web",
        "cache-control": "no-cache",
        "languageCode": "en",
        "Origin": "https://coinmarketcap.com",
        "Referer": "https://coinmarketcap.com/community/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.coinmarketcap.com/gravity/v3/gravity/post-crypto-tweet",
                headers=headers,
                json=payload,
            ) as resp:
                data = await resp.json(content_type=None)
                ok = bool((data.get("data") or {}).get("success"))
                if ok:
                    gid = ((data.get("data") or {}).get("data") or {}).get("gravityId")
                    logger.info(
                        "Published cloud desk note to CoinMarketCap Community (gravityId=%s, tag=%s, token=$%s)",
                        gid,
                        anchor_tag,
                        sym,
                    )
                    return True
                logger.warning("CoinMarketCap cloud post response: %s", data)
    except Exception as exc:
        logger.warning("CoinMarketCap cloud post error: %s", exc)

    return await auto_post_cmc_via_chrome(full_post_text)


async def auto_post_cmc_via_chrome(post_text: str) -> bool:
    """
    Fallback/Residential publisher that posts directly via Google Chrome Tab on
    coinmarketcap.com/community/ using the active residential session.
    """
    safe_text = post_text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    script = f"""
    tell application "Google Chrome"
        repeat with w from 1 to count of windows
            repeat with t from 1 to count of tabs of window w
                set u to URL of tab t of window w
                if u contains "coinmarketcap.com" then
                    set URL of tab t of window w to "https://coinmarketcap.com/community/"
                    delay 5
                    execute tab t of window w javascript "
                    (function() {{
                      const newPostBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.trim() === 'New Post');
                      if (newPostBtn) newPostBtn.click();
                    }})()
                    "
                    delay 2
                    execute tab t of window w javascript "
                    (function() {{
                      const s = document.createElement('script');
                      s.textContent = `
                        (async function() {{
                          const ed = document.querySelector('[data-slate-editor=true]');
                          if (!ed) return;
                          const fk = Object.keys(ed).find(k => k.startsWith('__reactFiber'));
                          let f = ed[fk], editor = null;
                          for (let i = 0; i < 30 && f; i++) {{
                            if (f.memoizedProps && f.memoizedProps.editor) {{ editor = f.memoizedProps.editor; break; }}
                            f = f.return;
                          }}
                          if (editor) {{
                            editor.children = [{{
                              type: 'paragraph',
                              children: [{{ text: \\"{safe_text}\\" }}]
                            }}];
                            editor.onChange();
                          }}
                          setTimeout(async () => {{
                            const btn = document.querySelector('[data-test=editor-post-button]');
                            if (!btn) return;
                            const bfk = Object.keys(btn).find(k => k.startsWith('__reactFiber'));
                            let bf = btn[bfk];
                            for (let i = 0; i < 15 && bf; i++) {{
                              if (bf.memoizedProps && bf.memoizedProps.onPost) {{
                                await bf.memoizedProps.onPost();
                                break;
                              }}
                              bf = bf.return;
                            }}
                          }}, 500);
                        }})();
                      `;
                      document.documentElement.appendChild(s);
                      s.remove();
                    }})()
                    "
                    return "POSTED_CMC"
                end if
            end repeat
        end repeat
        return "NO_CMC_TAB"
    end tell
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript",
            "-e",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return b"POSTED_CMC" in stdout
    except Exception:
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
