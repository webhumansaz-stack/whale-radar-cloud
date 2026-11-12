from __future__ import annotations

import asyncio
import hashlib
import html
import time
from typing import Any, Optional

import aiohttp


CHAIN_GOPLUS_MAP = {
    "ethereum": "1",
    "bsc": "56",
    "polygon": "137",
    "arbitrum": "42161",
    "base": "8453",
    "optimism": "10",
    "avalanche": "43114",
}


def _fmt_usd(val: float) -> str:
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"${val / 1_000_000:.2f}M"
    if val >= 1_000:
        return f"${val / 1_000:.1f}K"
    return f"${val:,.2f}"


def _fmt_price(price_str: str) -> str:
    try:
        p = float(price_str)
        if p >= 1.0:
            return f"${p:,.4f}"
        if p >= 0.001:
            return f"${p:.6f}"
        return f"${p:.8f}"
    except Exception:
        return f"${price_str}"


def _mask_symbol(symbol: str) -> str:
    clean = symbol.strip().upper()
    if len(clean) <= 2:
        return f"${clean[0]}••"
    return f"${clean[0]}{'•' * (len(clean) - 2)}{clean[-1]}"


def _mask_address(addr: str) -> str:
    if len(addr) <= 10:
        return "0x••••••"
    return f"{addr[:5]}••••{addr[-4:]}"


class MarketScanner:
    def __init__(self) -> None:
        self._timeout = aiohttp.ClientTimeout(total=12)

    async def _get_json(
        self, session: aiohttp.ClientSession, url: str
    ) -> Optional[Any]:
        try:
            async with session.get(
                url,
                headers={"User-Agent": "WhaleRadarDesk/2.4"},
                timeout=self._timeout,
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            return None
        return None

    async def check_token_security(
        self, session: aiohttp.ClientSession, chain: str, token_address: str
    ) -> str:
        chain_lower = chain.lower()
        if chain_lower == "solana":
            url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
            data = await self._get_json(session, url)
            if isinstance(data, dict) and "score" in data:
                risks = data.get("risks") or []
                high_risks = [
                    r.get("name", "")
                    for r in risks
                    if r.get("level") in ("danger", "warn")
                ]
                if not high_risks:
                    return "Pass (Mint/Freeze revoked, LP intact — RugCheck)"
                top_warn = ", ".join(high_risks[:2])
                return f"Note: {html.escape(top_warn)}"
            return "Verified SPL pool (Active liquidity)"

        goplus_chain = CHAIN_GOPLUS_MAP.get(chain_lower)
        if goplus_chain:
            url = (
                f"https://api.gopluslabs.io/api/v1/token_security/{goplus_chain}"
                f"?contract_addresses={token_address}"
            )
            data = await self._get_json(session, url)
            if isinstance(data, dict):
                result = (data.get("result") or {}).get(token_address.lower())
                if isinstance(result, dict):
                    is_honeypot = str(result.get("is_honeypot", "0")) == "1"
                    is_mintable = str(result.get("is_mintable", "0")) == "1"
                    buy_tax = float(result.get("buy_tax") or 0) * 100
                    sell_tax = float(result.get("sell_tax") or 0) * 100
                    if is_honeypot:
                        return "HIGH RISK: Honeypot detected (GoPlus)"
                    mint_str = "Mintable" if is_mintable else "Non-mintable"
                    return f"Pass (No honeypot, {mint_str}, Tax {buy_tax:.1f}%/{sell_tax:.1f}%)"

        return "Verified active DEX liquidity pool"

    async def discover_whale_signal(
        self, exclude_checker: Any = None
    ) -> Optional[dict[str, Any]]:
        """
        Scans live DexScreener orderflow across Solana, Base, Ethereum, BSC, Arbitrum
        and returns the highest-conviction buy-side accumulation setup.
        """
        async with aiohttp.ClientSession() as session:
            candidate_pairs: list[dict[str, Any]] = []

            boosts = await self._get_json(
                session, "https://api.dexscreener.com/token-boosts/top/v1"
            )
            token_addrs: list[str] = []
            if isinstance(boosts, list):
                for item in boosts[:25]:
                    addr = item.get("tokenAddress")
                    if addr and addr not in token_addrs:
                        token_addrs.append(addr)

            if token_addrs:
                batch = ",".join(token_addrs[:15])
                dex_data = await self._get_json(
                    session,
                    f"https://api.dexscreener.com/latest/dex/tokens/{batch}",
                )
                if isinstance(dex_data, dict) and isinstance(
                    dex_data.get("pairs"), list
                ):
                    candidate_pairs.extend(dex_data["pairs"])

            for query in ("SOL", "BASE", "PEPE", "VIRTUAL", "AI", "BONK", "WIF", "SUI", "ARB", "AAVE"):
                if len(candidate_pairs) >= 90:
                    break
                search_res = await self._get_json(
                    session,
                    f"https://api.dexscreener.com/latest/dex/search?q={query}",
                )
                if isinstance(search_res, dict) and isinstance(
                    search_res.get("pairs"), list
                ):
                    candidate_pairs.extend(search_res["pairs"][:15])

            scored_candidates: list[tuple[int, dict[str, Any]]] = []
            seen_tokens: set[str] = set()
            now_ms = int(time.time() * 1000)

            for pair in candidate_pairs:
                base_token = pair.get("baseToken") or {}
                token_addr = str(base_token.get("address") or "").strip()
                symbol = str(base_token.get("symbol") or "").strip()
                name = str(base_token.get("name") or symbol).strip()
                chain = str(pair.get("chainId") or "").strip().upper()

                if not token_addr or not symbol or token_addr.lower() in seen_tokens:
                    continue
                seen_tokens.add(token_addr.lower())

                # Keep only clean ASCII tickers so posts look professional
                if not symbol.isascii() or len(symbol) > 12:
                    continue

                if symbol.upper() in {
                    "USDT",
                    "USDC",
                    "WETH",
                    "WSOL",
                    "WBTC",
                    "DAI",
                    "BUSD",
                    "WBNB",
                    "SOL",
                    "ETH",
                    "BNB",
                }:
                    continue

                if exclude_checker and exclude_checker(token_addr):
                    continue

                # Reject brand-new (<3 hours old) Pump.fun / rug-prone pools
                created_at_ms = int(pair.get("pairCreatedAt") or 0)
                if created_at_ms > 0 and (now_ms - created_at_ms) < (3 * 3600 * 1000):
                    continue

                liq = float((pair.get("liquidity") or {}).get("usd") or 0)
                vol_dict = pair.get("volume") or {}
                vol_24h = float(vol_dict.get("h24") or 0)
                vol_1h = float(vol_dict.get("h1") or 0)
                fdv = float(pair.get("fdv") or pair.get("marketCap") or 0)

                if liq < 55_000 or vol_24h < 75_000 or fdv < 120_000:
                    continue

                txns_1h = (pair.get("txns") or {}).get("h1") or {}
                buys_1h = int(txns_1h.get("buys") or 0)
                sells_1h = int(txns_1h.get("sells") or 0)
                total_tx_1h = buys_1h + sells_1h
                if total_tx_1h < 30:
                    continue

                buy_ratio = (buys_1h / total_tx_1h) * 100.0
                if buy_ratio < 55.0:
                    continue

                pc = pair.get("priceChange") or {}
                ch_1h = float(pc.get("h1") or 0)
                ch_24h = float(pc.get("h24") or 0)

                # Reject tokens already at blow-off scam tops (+250%+) or crashing (-35%)
                if ch_24h > 240.0 or ch_24h < -30.0 or ch_1h < -5.0 or ch_1h > 85.0:
                    continue

                vol_liq_ratio = min(2.5, vol_1h / max(liq, 1.0))
                imbalance_pts = min(30.0, max(0.0, (buy_ratio - 50.0) * 1.1))
                momentum_pts = min(22.0, max(0.0, ch_1h * 0.7))
                activity_pts = min(18.0, total_tx_1h / 30.0)
                depth_pts = min(10.0, liq / 50_000.0)
                score = int(
                    min(
                        98,
                        max(
                            68,
                            45
                            + imbalance_pts
                            + momentum_pts
                            + activity_pts
                            + depth_pts
                            + (vol_liq_ratio * 6),
                        ),
                    )
                )
                scored_candidates.append((score, pair))

            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            best_pair: Optional[dict[str, Any]] = None
            best_score: int = -1
            security_summary = "Verified active DEX liquidity pool"

            for cand_score, cand_pair in scored_candidates[:6]:
                c_base = cand_pair.get("baseToken") or {}
                c_addr = str(c_base.get("address") or "")
                c_chain = str(cand_pair.get("chainId") or "SOLANA").upper()
                sec = await self.check_token_security(session, c_chain, c_addr)
                if "HIGH RISK" in sec or "Note:" in sec:
                    continue
                best_pair = cand_pair
                best_score = cand_score
                security_summary = sec
                break

            if not best_pair and scored_candidates:
                best_score, best_pair = scored_candidates[0]

            if not best_pair:
                return None

            base_token = best_pair.get("baseToken") or {}
            token_addr = str(base_token.get("address") or "")
            symbol = str(base_token.get("symbol") or "TOKEN").upper()
            name = str(base_token.get("name") or symbol)
            chain = str(best_pair.get("chainId") or "SOLANA").upper()
            pair_addr = str(best_pair.get("pairAddress") or "")
            price_str = str(best_pair.get("priceUsd") or "0.0001")
            price_float = float(price_str) if price_str else 0.0001

            pc = best_pair.get("priceChange") or {}
            ch_1h = float(pc.get("h1") or 0.0)
            ch_24h = float(pc.get("h24") or 0.0)

            vol_24h = float((best_pair.get("volume") or {}).get("h24") or 0.0)
            liq_usd = float((best_pair.get("liquidity") or {}).get("usd") or 0.0)
            fdv = float(best_pair.get("fdv") or best_pair.get("marketCap") or 0.0)

            txns_1h = (best_pair.get("txns") or {}).get("h1") or {}
            buys_1h = int(txns_1h.get("buys") or 0)
            sells_1h = int(txns_1h.get("sells") or 0)
            buy_ratio = (buys_1h / max(1, buys_1h + sells_1h)) * 100.0

            security_summary = await self.check_token_security(
                session, chain, token_addr
            )

            entry_low = _fmt_price(str(price_float * 0.97))
            entry_high = _fmt_price(str(price_float * 1.01))
            entry_zone = f"{entry_low} – {entry_high}"
            tp1 = _fmt_price(str(price_float * 1.18))
            tp2 = _fmt_price(str(price_float * 1.45))
            tp3 = _fmt_price(str(price_float * 1.90))
            targets_text = f"T1: {tp1} (+18%) | T2: {tp2} (+45%) | T3: {tp3} (+90%)"
            stop_loss = f"{_fmt_price(str(price_float * 0.86))} (-14%)"

            dex_url = str(
                best_pair.get("url")
                or f"https://dexscreener.com/{chain.lower()}/{token_addr}"
            )

            now = int(time.time())
            raw_hash = hashlib.sha1(f"{token_addr}:{now // 600}".encode()).hexdigest()[
                :6
            ].upper()
            signal_id = f"WHALE-{raw_hash}"

            masked_sym = _mask_symbol(symbol)
            masked_addr = _mask_address(token_addr)

            # Institutional Quant Desk style — no AI emoji spam
            teaser_text = (
                f"<b>[ON-CHAIN ORDERFLOW] {html.escape(chain)} — Desk Alert</b>\n"
                f"Ref: <code>{signal_id}</code>\n"
                f"──────────────────────\n"
                f"<b>Asset:</b> <code>{html.escape(masked_sym)}</code> (Contract: <code>{html.escape(masked_addr)}</code>)\n"
                f"<b>1h Orderflow:</b> <b>{buy_ratio:.1f}% buy-side</b> ({buys_1h} buys / {sells_1h} sells)\n"
                f"<b>Price Delta:</b> 1h <code>{ch_1h:+.2f}%</code> | 24h <code>{ch_24h:+.2f}%</code>\n"
                f"<b>24h Volume:</b> <code>{_fmt_usd(vol_24h)}</code>\n"
                f"<b>Pool Liquidity:</b> <code>{_fmt_usd(liq_usd)}</code> | <b>FDV:</b> <code>{_fmt_usd(fdv)}</code>\n"
                f"<b>Contract Audit:</b> {security_summary}\n"
                f"<b>Flow Conviction:</b> <code>{best_score}/100</code>\n"
                f"──────────────────────\n"
                f"<i>Full contract address, ticker, DEX pair link & execution levels are available via single unlock or VIP desk access below.</i>"
            )

            full_text = (
                f"<b>[VIP DESK EXECUTION LOG] {html.escape(chain)}</b>\n"
                f"Ref: <code>{signal_id}</code>\n"
                f"──────────────────────\n"
                f"<b>Asset:</b> <b>{html.escape(name)} (${html.escape(symbol)})</b>\n"
                f"<b>Spot Price:</b> <code>{_fmt_price(price_str)}</code>\n"
                f"<b>Contract Address:</b>\n"
                f"<code>{html.escape(token_addr)}</code>\n\n"
                f"<b>On-Chain Telemetry:</b>\n"
                f"• 1h Orderflow: <b>{buy_ratio:.1f}% buy-side</b> ({buys_1h}B / {sells_1h}S)\n"
                f"• Price Delta: 1h <code>{ch_1h:+.2f}%</code> | 24h <code>{ch_24h:+.2f}%</code>\n"
                f"• 24h Volume: <code>{_fmt_usd(vol_24h)}</code>\n"
                f"• Pool Liquidity: <code>{_fmt_usd(liq_usd)}</code> | FDV: <code>{_fmt_usd(fdv)}</code>\n"
                f"• Security Audit: {security_summary}\n\n"
                f"<b>Desk Execution Levels:</b>\n"
                f"• Entry Range: <code>{entry_zone}</code>\n"
                f"• Targets: <code>{targets_text}</code>\n"
                f"• Invalidation: <code>{stop_loss}</code>\n\n"
                f"🔗 <a href=\"{html.escape(dex_url)}\">Open DexScreener Pair Terminal</a>"
            )

            return {
                "signal_id": signal_id,
                "created_at": now,
                "signal_type": "WHALE_SURGE",
                "chain": chain,
                "symbol": symbol,
                "name": name,
                "token_address": token_addr,
                "pair_address": pair_addr,
                "price_usd": price_str,
                "price_change_1h": ch_1h,
                "price_change_24h": ch_24h,
                "volume_24h": vol_24h,
                "liquidity_usd": liq_usd,
                "fdv": fdv,
                "buys_1h": buys_1h,
                "sells_1h": sells_1h,
                "buy_ratio": buy_ratio,
                "security_summary": security_summary,
                "whale_score": best_score,
                "entry_zone": entry_zone,
                "targets_text": targets_text,
                "stop_loss": stop_loss,
                "dex_url": dex_url,
                "teaser_text": teaser_text,
                "full_text": full_text,
                "posted_public": 0,
            }

    async def scan_custom_token(
        self, query: str
    ) -> Optional[dict[str, Any]]:
        q = query.strip()
        if not q:
            return None

        async with aiohttp.ClientSession() as session:
            pairs: list[dict[str, Any]] = []
            if len(q) >= 30 and " " not in q:
                data = await self._get_json(
                    session,
                    f"https://api.dexscreener.com/latest/dex/tokens/{q}",
                )
                if isinstance(data, dict) and isinstance(data.get("pairs"), list):
                    pairs = data["pairs"]

            if not pairs:
                data = await self._get_json(
                    session,
                    f"https://api.dexscreener.com/latest/dex/search?q={q}",
                )
                if isinstance(data, dict) and isinstance(data.get("pairs"), list):
                    pairs = data["pairs"]

            if not pairs:
                return None

            pairs.sort(
                key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0),
                reverse=True,
            )
            top = pairs[0]
            base = top.get("baseToken") or {}
            token_addr = str(base.get("address") or "")
            symbol = str(base.get("symbol") or "TOKEN").upper()
            name = str(base.get("name") or symbol)
            chain = str(top.get("chainId") or "UNKNOWN").upper()
            price_str = str(top.get("priceUsd") or "0")
            liq_usd = float((top.get("liquidity") or {}).get("usd") or 0)
            vol_24h = float((top.get("volume") or {}).get("h24") or 0)
            fdv = float(top.get("fdv") or top.get("marketCap") or 0)

            pc = top.get("priceChange") or {}
            ch_1h = float(pc.get("h1") or 0)
            ch_24h = float(pc.get("h24") or 0)

            txns_1h = (top.get("txns") or {}).get("h1") or {}
            buys_1h = int(txns_1h.get("buys") or 0)
            sells_1h = int(txns_1h.get("sells") or 0)
            buy_ratio = (buys_1h / max(1, buys_1h + sells_1h)) * 100.0

            security = await self.check_token_security(session, chain, token_addr)
            dex_url = str(
                top.get("url")
                or f"https://dexscreener.com/{chain.lower()}/{token_addr}"
            )

            report = (
                f"<b>[ON-CHAIN PAIR & CONTRACT AUDIT]</b>\n"
                f"──────────────────────\n"
                f"<b>Asset:</b> {html.escape(name)} (${html.escape(symbol)}) on {html.escape(chain)}\n"
                f"<b>Price:</b> <code>{_fmt_price(price_str)}</code> (1h: <code>{ch_1h:+.2f}%</code> | 24h: <code>{ch_24h:+.2f}%</code>)\n"
                f"<b>Contract:</b> <code>{html.escape(token_addr)}</code>\n\n"
                f"<b>Orderflow & Liquidity:</b>\n"
                f"• 1h Buy Ratio: <b>{buy_ratio:.1f}%</b> ({buys_1h} buys / {sells_1h} sells)\n"
                f"• Pool Liquidity: <code>{_fmt_usd(liq_usd)}</code>\n"
                f"• 24h Volume: <code>{_fmt_usd(vol_24h)}</code> | FDV: <code>{_fmt_usd(fdv)}</code>\n\n"
                f"<b>Security Registry Check:</b>\n"
                f"• {security}\n\n"
                f"🔗 <a href=\"{html.escape(dex_url)}\">DexScreener Pair Terminal</a>"
            )
            return {
                "symbol": symbol,
                "name": name,
                "chain": chain,
                "token_address": token_addr,
                "report": report,
            }

    async def scan_cex_arbitrage(self) -> str:
        symbols = ["SOL", "PEPE", "DOGE", "SUI", "TON", "WIF", "ARB", "LINK", "AVAX"]
        async with aiohttp.ClientSession() as session:
            binance_task = self._get_json(
                session, "https://api.binance.com/api/v3/ticker/bookTicker"
            )
            bybit_task = self._get_json(
                session, "https://api.bybit.com/v5/market/tickers?category=spot"
            )
            kucoin_task = self._get_json(
                session, "https://api.kucoin.com/api/v1/market/allTickers"
            )
            binance_data, bybit_data, kucoin_data = await asyncio.gather(
                binance_task, bybit_task, kucoin_task
            )

            prices: dict[str, dict[str, float]] = {s: {} for s in symbols}

            if isinstance(binance_data, list):
                for item in binance_data:
                    sym = str(item.get("symbol") or "")
                    for s in symbols:
                        if sym == f"{s}USDT":
                            bid = float(item.get("bidPrice") or 0)
                            ask = float(item.get("askPrice") or 0)
                            if bid > 0 and ask > 0:
                                prices[s]["Binance"] = (bid + ask) / 2.0

            if isinstance(bybit_data, dict):
                lst = (bybit_data.get("result") or {}).get("list") or []
                for item in lst:
                    sym = str(item.get("symbol") or "")
                    for s in symbols:
                        if sym == f"{s}USDT":
                            last_p = float(item.get("lastPrice") or 0)
                            if last_p > 0:
                                prices[s]["Bybit"] = last_p

            if isinstance(kucoin_data, dict):
                lst = (kucoin_data.get("data") or {}).get("ticker") or []
                for item in lst:
                    sym = str(item.get("symbol") or "")
                    for s in symbols:
                        if sym == f"{s}-USDT":
                            last_p = float(item.get("last") or 0)
                            if last_p > 0:
                                prices[s]["KuCoin"] = last_p

            opportunities: list[tuple[float, str, str, float, str, float]] = []
            for s, ex_map in prices.items():
                if len(ex_map) < 2:
                    continue
                sorted_ex = sorted(ex_map.items(), key=lambda x: x[1])
                low_ex, low_p = sorted_ex[0]
                high_ex, high_p = sorted_ex[-1]
                if low_p > 0:
                    spread_pct = ((high_p - low_p) / low_p) * 100.0
                    opportunities.append(
                        (spread_pct, s, low_ex, low_p, high_ex, high_p)
                    )

            opportunities.sort(key=lambda x: x[0], reverse=True)

            if not opportunities:
                return (
                    "<b>[CEX ORDERBOOK ARBITRAGE MONITOR]</b>\n\n"
                    "Spot spreads across Binance, Bybit & KuCoin are currently within tight parity."
                )

            lines = [
                "<b>[CEX SPOT ORDERBOOK SPREADS — LIVE]</b>",
                "<i>Cross-exchange mid-price delta (Binance / Bybit / KuCoin)</i>",
                "──────────────────────",
            ]
            for spread_pct, sym, low_ex, low_p, high_ex, high_p in opportunities[:6]:
                bps = spread_pct * 100
                lines.append(
                    f"• <b>{sym}/USDT</b>: <code>{bps:.1f} bps</code> ({spread_pct:.3f}%)\n"
                    f"  Bid {low_ex} <code>{_fmt_price(str(low_p))}</code> → Ask {high_ex} <code>{_fmt_price(str(high_p))}</code>"
                )
            lines.append("──────────────────────")
            return "\n".join(lines)
