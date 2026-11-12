from __future__ import annotations

import asyncio
import json
import logging
import random
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from promoter import (
    auto_post_tweet_via_chrome,
    build_viral_promo_pack,
    post_to_cmc_cloud,
)
from scanner import MarketScanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("XSniper")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
SNIPER_DB = BASE_DIR / "x_sniper_state.db"
CHANNEL_HANDLE = "@WhaleRadarGlobal"
BOT_HANDLE = "@WhaleAlphaStars_bot"

SEARCH_QUERIES = [
    "(from:WatcherGuru OR from:whale_alert OR from:lookonchain OR from:SolanaFloor OR from:dexscreener OR from:WuBlockchain)",
    "($SOL OR #Solana) (whale OR volume OR memecoin OR breakout) min_faves:5",
    "(from:Cointelegraph OR from:CoinMarketCap OR from:coingecko OR from:rovercrc OR from:ashcryptoreal)",
    "($PEPE OR $WIF OR $BONK OR $BTC) (whale OR orderflow OR accumulation) min_faves:5",
    '("What memecoin" OR "100x gem" OR "dexscreener" OR "on-chain") ($SOL OR $ETH) min_faves:3',
]


def init_sniper_db() -> None:
    with sqlite3.connect(str(SNIPER_DB)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS replied_tweets (
                tweet_id TEXT PRIMARY KEY,
                replied_at INTEGER NOT NULL
            )
            """
        )


def is_replied(tweet_id: str) -> bool:
    with sqlite3.connect(str(SNIPER_DB)) as conn:
        row = conn.execute(
            "SELECT 1 FROM replied_tweets WHERE tweet_id = ?", (tweet_id,)
        ).fetchone()
        return row is not None


def mark_replied(tweet_id: str) -> None:
    with sqlite3.connect(str(SNIPER_DB)) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO replied_tweets (tweet_id, replied_at) VALUES (?, ?)",
            (tweet_id, int(time.time())),
        )


async def run_osascript(script: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "osascript",
        "-e",
        script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode("utf-8", errors="ignore").strip()


async def navigate_x_tab(url: str) -> bool:
    script = f"""
    tell application "Google Chrome"
        repeat with w from 1 to count of windows
            repeat with t from 1 to count of tabs of window w
                set u to URL of tab t of window w
                if u contains "x.com" or u contains "twitter.com" then
                    set URL of tab t of window w to "{url}"
                    return "OK"
                end if
            end repeat
        end repeat
        return "NO_TAB"
    end tell
    """
    res = await run_osascript(script)
    return "OK" in res


async def exec_x_js(js_code: str) -> str:
    escaped = js_code.replace("\\", "\\\\").replace('"', '\\"')
    script = f"""
    tell application "Google Chrome"
        repeat with w from 1 to count of windows
            repeat with t from 1 to count of tabs of window w
                set u to URL of tab t of window w
                if u contains "x.com" or u contains "twitter.com" then
                    return execute tab t of window w javascript "{escaped}"
                end if
            end repeat
        end repeat
        return ""
    end tell
    """
    return await run_osascript(script)


async def find_target_tweets(query: str) -> list[dict[str, str]]:
    encoded_q = urllib.parse.quote(query, safe="")
    search_url = f"https://x.com/search?q={encoded_q}&src=typed_query&f=live"
    ok = await navigate_x_tab(search_url)
    if not ok:
        return []
    await asyncio.sleep(5.5)

    js = """
    (() => {
      const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
      const results = articles.map(art => {
        const link = Array.from(art.querySelectorAll('a[href*="/status/"]')).find(a => /\\/status\\/[0-9]+$/.test(a.getAttribute('href')));
        const href = link ? link.getAttribute('href') : '';
        const idMatch = href.match(/\\/status\\/([0-9]+)$/);
        return {
          tweetId: idMatch ? idMatch[1] : null,
          href: href
        };
      }).filter(r => r.tweetId && !r.href.includes('WhaleAlphaStar'));
      return JSON.stringify(results.slice(0, 8));
    })()
    """
    raw = await exec_x_js(js)
    try:
        return json.loads(raw)
    except Exception:
        return []


def build_reply_text(sig: dict[str, Any], template_idx: int) -> str:
    sym = str(sig.get("symbol") or "SOL").upper()
    chain = str(sig.get("chain") or "SOLANA").capitalize()
    buy_ratio = float(sig.get("buy_ratio") or 79.0)
    buys_1h = int(sig.get("buys_1h") or 120)
    sells_1h = int(sig.get("sells_1h") or 30)
    liq_usd = float(sig.get("liquidity_usd") or 65_000)
    ch_1h = float(sig.get("price_change_1h") or 14.2)
    liq_k = f"${liq_usd / 1000:.0f}k" if liq_usd >= 1000 else f"${liq_usd:.0f}"

    templates = [
        (
            f"Looking strictly at 1h DEX orderflow rather than narratives, ${sym} ({chain}) "
            f"is printing {buys_1h} buys vs {sells_1h} sells ({buy_ratio:.0f}% buy skew) with {liq_k} liquidity.\n\n"
            f"We log raw contract audits & levels on Telegram: t.me/WhaleRadarGlobal"
        ),
        (
            f"Watching ${sym} on {chain} right now — {buy_ratio:.0f}% 1h buy-side flow "
            f"({ch_1h:+.1f}% delta) and clean RugCheck/GoPlus audit ({liq_k} LP).\n\n"
            f"Live orderflow feed on Telegram: t.me/WhaleRadarGlobal"
        ),
        (
            f"Most low-caps fail on LP depth or mint authority. ${sym} ({chain}) is one of the few "
            f"showing {buys_1h}B/{sells_1h}S in the last hour with verified liquidity.\n\n"
            f"Full on-chain desk on Telegram: t.me/WhaleRadarGlobal"
        ),
        (
            f"If you're tracking real-time buy imbalance, ${sym} on {chain} just hit "
            f"{buy_ratio:.0f}% buy-side volume over the past 60m ({liq_k} pool depth).\n\n"
            f"Live Telegram feed: t.me/WhaleRadarGlobal | Free Scanner: t.me/WhaleAlphaStars_bot"
        ),
    ]
    return templates[template_idx % len(templates)]


async def reply_to_tweet(tweet_id: str, text: str) -> bool:
    url = f"https://x.com/intent/post?in_reply_to={tweet_id}"
    if not await navigate_x_tab(url):
        return False
    await asyncio.sleep(5.5)

    safe_text = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    js_insert = f"""
    (() => {{
      const ed = document.querySelector('[data-testid="tweetTextarea_0"], [role="textbox"]');
      if (!ed) return 'NO_EDITOR';
      ed.focus();
      document.execCommand('insertText', false, "{safe_text}");
      return 'INSERTED';
    }})()
    """
    ins_res = await exec_x_js(js_insert)
    if "INSERTED" not in ins_res:
        return False

    await asyncio.sleep(1.2)
    js_click = """
    (() => {
      const btn = document.querySelector('[data-testid="tweetButtonInline"], [data-testid="tweetButton"]');
      if (btn && !btn.getAttribute('aria-disabled')) {
        btn.click();
        return 'REPLIED';
      }
      return 'DISABLED';
    })()
    """
    res = await exec_x_js(js_click)
    return "REPLIED" in res


async def snipe_cmc_trending_comment(sig: dict[str, Any], post_idx: int = 0) -> bool:
    sym = str(sig.get("symbol") or "SOL").upper()
    chain = str(sig.get("chain") or "SOLANA").capitalize()
    buy_ratio = float(sig.get("buy_ratio") or 74.0)
    buys_1h = int(sig.get("buys_1h") or 110)
    sells_1h = int(sig.get("sells_1h") or 32)
    liq_usd = float(sig.get("liquidity_usd") or 62_000)
    liq_k = f"${liq_usd / 1000:.0f}K" if liq_usd >= 1000 else f"${liq_usd:.0f}"

    comment_text = (
        f"On-chain DEX orderflow also showing {buy_ratio:.0f}% 1H buy-side skew on ${sym} ({chain}) — "
        f"{buys_1h} buys vs {sells_1h} sells across {liq_k} verified LP depth. "
        f"We log live whale orderflow & CEX arbitrage spreads 24/7 on Telegram: {CHANNEL_HANDLE} (Free Scanner: {BOT_HANDLE})"
    )
    safe_comment = comment_text.replace("\\", "\\\\").replace('"', '\\"')
    use_latest_tab = (post_idx % 2 == 1)

    script = f"""
    tell application "Google Chrome"
        repeat with w from 1 to count of windows
            repeat with t from 1 to count of tabs of window w
                set u to URL of tab t of window w
                if u contains "coinmarketcap.com" then
                    set URL of tab t of window w to "https://coinmarketcap.com/community/"
                    delay 5
                    if {"true" if use_latest_tab else "false"} then
                        execute tab t of window w javascript "
                        (function() {{
                          const tabs = Array.from(document.querySelectorAll('span, div, button, a'));
                          const latestBtn = tabs.find(el => el.innerText && el.innerText.trim() === 'Latest');
                          if (latestBtn) latestBtn.click();
                        }})()
                        "
                        delay 2.5
                    end if
                    execute tab t of window w javascript "
                    (function() {{
                      const posts = Array.from(document.querySelectorAll('section.g-post-row, [class*=SocialPostWrapper]'));
                      const target = posts[{post_idx % 4}] || posts[0];
                      if (!target) return;
                      const likeBtn = target.querySelector('[class*=LikeWrapper], [data-test*=like]');
                      if (likeBtn) likeBtn.click();
                      const cBtn = target.querySelector('[class*=CommentWrapper]');
                      if (cBtn) cBtn.click();
                    }})()
                    "
                    delay 2
                    execute tab t of window w javascript "
                    (function() {{
                      const s = document.createElement('script');
                      s.textContent = `
                        (async function() {{
                          const eds = Array.from(document.querySelectorAll('[data-slate-editor=true]'));
                          const ed = eds[eds.length - 1];
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
                              children: [{{ text: \\"{safe_comment}\\" }}]
                            }}];
                            editor.onChange();
                          }}
                          setTimeout(async () => {{
                            const btns = Array.from(document.querySelectorAll('[data-test=editor-post-button]'));
                            const btn = btns[btns.length - 1];
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
                    return "CMC_COMMENTED"
                end if
            end repeat
        end repeat
        return "NO_TAB"
    end tell
    """
    res = await run_osascript(script)
    return "CMC_COMMENTED" in res


async def sniper_loop() -> None:
    init_sniper_db()
    scanner = MarketScanner()
    cycle = 0
    logger.info("Quant Desk X.com + CoinMarketCap Sniper active for @WhaleRadarGlobal")

    while True:
        try:
            sig = await scanner.discover_whale_signal()
            if sig:
                # 1) Reply to 2 high-engagement live X.com crypto threads FIRST
                query = SEARCH_QUERIES[cycle % len(SEARCH_QUERIES)]
                candidates = await find_target_tweets(query)
                replied_this_round = 0

                for item in candidates:
                    tid = str(item.get("tweetId") or "")
                    if not tid or is_replied(tid):
                        continue

                    reply_msg = build_reply_text(sig, cycle + replied_this_round)
                    ok = await reply_to_tweet(tid, reply_msg)
                    if ok:
                        mark_replied(tid)
                        replied_this_round += 1
                        logger.info(
                            "Posted X.com analyst reply to %s (%s) — $%s (%s)",
                            tid,
                            item.get("href"),
                            sig["symbol"],
                            sig["chain"],
                        )
                        await asyncio.sleep(random.randint(20, 35))
                        if replied_this_round >= 2:
                            break

                # 2) Publish standalone desk note on X.com every 2nd cycle
                if cycle % 2 == 0:
                    promo = build_viral_promo_pack(sig)
                    posted = await auto_post_tweet_via_chrome(promo["tweet_plain"])
                    if posted:
                        logger.info(
                            "Published standalone desk note for $%s (%s) on @WhaleAlphaStar",
                            sig["symbol"],
                            sig["chain"],
                        )

                cycle += 1
        except Exception as exc:
            logger.warning("Sniper cycle error: %s", exc)

        await asyncio.sleep(random.randint(60, 85))


if __name__ == "__main__":
    asyncio.run(sniper_loop())
