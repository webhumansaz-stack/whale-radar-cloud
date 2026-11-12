# 🐋 On-Chain Whale Orderflow & CEX Arbitrage Desk (`whale-radar-cloud`)

[![Live Telegram Feed](https://img.shields.io/badge/Telegram_Desk-@WhaleRadarGlobal-0088cc?style=for-the-badge&logo=telegram)](https://t.me/WhaleRadarGlobal)
[![Telegram Bot Terminal](https://img.shields.io/badge/Bot_Terminal-@WhaleAlphaStars__bot-2CA5E0?style=for-the-badge&logo=telegram)](https://t.me/WhaleAlphaStars_bot)
[![24/7 Cloud Engine](https://img.shields.io/badge/Cloud_Execution-24%2F7_Active-10b981?style=for-the-badge&logo=githubactions)](https://github.com/webhumansaz-stack/whale-radar-cloud/actions)
[![Chains](https://img.shields.io/badge/Coverage-Solana_%7C_Ethereum_%7C_Base_%7C_BSC-6366f1?style=for-the-badge)](#architecture--methodology)

An institutional-grade **On-Chain Whale Orderflow Scanner**, **Automated Smart Contract Security Auditor**, and **Cross-Exchange Spot Arbitrage Monitor** operating 24/7 in the cloud.

Built for quantitative traders, liquidity providers, and active on-chain participants looking to track unusual DEX volume anomalies and verified CEX price discrepancies without noise.

---

## 🔗 Live Access & Real-Time Feeds

* **📡 Public Orderflow Channel (Free Delay Feed & Market Recaps):**  
  👉 **[Join `@WhaleRadarGlobal` (`t.me/WhaleRadarGlobal`)](https://t.me/WhaleRadarGlobal)**
* **⚡ Interactive Bot Terminal (Instant Contract Audits, CA Unlocks & VIP Pass):**  
  👉 **[Launch `@WhaleAlphaStars_bot` (`t.me/WhaleAlphaStars_bot`)](https://t.me/WhaleAlphaStars_bot)**
* **📊 X (Twitter) & CoinMarketCap Desk Notes:**  
  👉 **[`@WhaleAlphaStar` (X)](https://x.com/WhaleAlphaStar)** · **[`@WhaleRadarGlobal` (CMC)](https://coinmarketcap.com/community/profile/WhaleRadarGlobal/)**

---

## 🧠 Architecture & Methodology

Unlike retail signal groups that repost promoted tokens, this engine filters raw DEX & CEX market data through a strict multi-stage pipeline every cycle:

### 1. DEX Liquidity & Orderflow Anomaly Detection (`Solana`, `Base`, `Ethereum`, `BSC`, `Arbitrum`)
* Continuously polls live pool telemetry via **DexScreener API** across Raydium, Orca, Meteora, Uniswap v3, Aerodrome, and PancakeSwap.
* Computes **1H Volume-to-Liquidity Velocity (`Vol/Liq Ratio`)** and **Buy/Sell Transaction Imbalance** (`buys_1h / total_tx_1h`) to isolate genuine whale accumulation from wash trading.
* Enforces a hard minimum liquidity floor (`>$12,000 USD` locked pool depth) and ASCII ticker validation to discard spoofed contracts.

### 2. Automated Smart Contract Security Audit (`RugCheck` & `GoPlus`)
Every candidate pair undergoes an automated pre-broadcast contract inspection:
* **Solana SPL Tokens (`RugCheck.xyz` API):** Verifies Mint Authority status, Freeze Authority status, LP lock/burn percentage, and top-holder concentration risk.
* **EVM Tokens (`GoPlus Security` API):** Checks for honeypot logic, dynamic buy/sell tax traps (`>10%`), hidden owner mint functions, and proxy upgrade risks.

### 3. Cross-Exchange Spot Arbitrage Engine (`Binance` vs `Bybit` vs `KuCoin`)
* Simultaneously queries orderbook best-bid / best-ask (`bookTicker`) across **Binance**, **Bybit V5**, and **KuCoin** for high-liquidity spot pairs (`BTC`, `ETH`, `SOL`, `XRP`, `DOGE`, `SUI`, `PEPE`, `LINK`, `AVAX`, `TON`).
* Calculates net executable spread after standard taker fees (`~0.20%` round-trip) and estimates capital efficiency on `$1,000–$10,000` clip sizes.

---

## 📋 Sample Terminal Output

```text
[ON-CHAIN ORDERFLOW] SOLANA — Desk Alert

Asset: $SOL / USDC (SOLANA)
Spot Price: $184.20 (+14.8% 1h | +28.4% 24h)

Liquidity & Flow Metrics
• 1H Volume: $1,420,500
• Pool Liquidity: $385,000 (Vol/Liq: 3.7x)
• 1H Orderflow: 412 Buys / 168 Sells (71% buy-side)
• Composite Score: 92/100 (HIGH CONVICTION)
• Contract Audit: Verified Clean (No Mint/Freeze Risk)
```

---

## 🛠️ Repository Structure

| File | Description |
| :--- | :--- |
| [`scanner.py`](scanner.py) | Asynchronous DEX whale orderflow detector, GoPlus/RugCheck security auditor & CEX spot arbitrage calculator |
| [`bot.py`](bot.py) | Telegram Bot API & native Telegram Stars (`XTR`) settlement engine with automated VIP invite generation |
| [`promoter.py`](promoter.py) | Multi-platform quantitative desk note formatter for Telegram, CoinMarketCap Community & X |
| [`database.py`](database.py) | SQLite persistence layer for signals, audit logs, user credits & VIP subscriptions |
| [`.github/workflows/whale_radar_24_7.yml`](.github/workflows/whale_radar_24_7.yml) | Self-chaining 24/7 GitHub Actions cloud execution workflow |

---

## 🚀 Live Telegram Terminal Commands

Open **[@WhaleAlphaStars_bot](https://t.me/WhaleAlphaStars_bot)** on Telegram and use:
* `/start` — Open the main institutional terminal & check account status
* `/latest` — Inspect the most recent high-conviction whale accumulation alert
* `/arb` — Fetch the latest live Binance / Bybit / KuCoin spot arbitrage matrix
* `/vip` — Activate instant zero-delay VIP feed access (includes full contract addresses, direct DexScreener execution links & stop-loss levels)

---

## 🔍 Topics & Keywords
`solana-whale-tracker` · `on-chain-orderflow` · `dexscreener-bot` · `crypto-arbitrage-scanner` · `smart-money-tracker` · `rugcheck-scanner` · `raydium-sniper-analytics` · `evm-whale-alerts` · `quantitative-crypto-trading` · `telegram-trading-terminal`
