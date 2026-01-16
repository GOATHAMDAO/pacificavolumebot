# 🌊 Pacifica Volume Bot

Before using, register on the PACIFICA website: https://app.pacifica.fi?referral=bluedepp

In the trading window (Join Closed Beta) use the code:

B8EFAKQAYZTX0TKB
1QPGJB7PX11CZB1H
ZBGCJ5NM7TXYTKCS
JJSW6CP14NGWBFQT
V6SHN3PDRNP07KPZ
SBWF2BN0ZYD60STR
7766CB3F5W348E82
TV0RR2MR1MCJ7V61
3J9E9FQ14GJY18FB
VJRJAH2S68SG6NPS
H6H200KGF5875HQB
9VCGMZ8M3VNES9FX
4JRH9N13Z6SX5JP8
KX1BTZVXSG4B641F
YM59RHEK6Y0TB90G
CYJ1M2186FB24BPG

### How it works:

1. Open position (entire balance with leverage)
2. Hold for `hold_time` minutes
3. Check `max_check_price` (close earlier if loss exceeds limit)
4. Close position
5. Repeat until `target_volume` is reached

## 🚀 Installation

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create accounts.csv

Create an `accounts.csv` file based on the `accounts_sample.csv` template:

```csv
account_name,api_key,api_secret,walletaddress
main,YOUR_WALLET_PUBLIC_KEY,YOUR_WALLET_PRIVATE_KEY,YOUR_WALLET_ADDRESS
```

**Fields:**
- `api_key` - Solana wallet public key (address) (base58)
- `api_secret` - Solana wallet private key (base58)
- `walletaddress` - Main account address (for API Agent)

### 3. Run

```bash
python pacifica_bot.py
```

## ⚙️ Configuration (config.json)

```json
{
    "hold_time_min": 3,
    "hold_time_max": 5,
    "target_volume": 10000,
    "leverage": 5,
    "markets": ["BTC", "ETH", "SOL"],
    "min_position_size": 0.7,
    "max_position_size": 0.9,
    "delay_between_trades_min": 30,
    "delay_between_trades_max": 60,
    "use_maker_orders": true,
    "take_profit_percent_min": 0.002,
    "take_profit_percent_max": 0.004,
    "stop_loss_percent_min": 0.002,
    "stop_loss_percent_max": 0.004,
    "slippage_min": 0.0003,
    "slippage_max": 0.0005
}
```

### Parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `hold_time_min/max` | Position hold time in minutes (range) | 3-5 |
| `target_volume` | Target trading volume in USD | 10000 |
| `leverage` | Leverage | 5 |
| `markets` | Markets for trading | ["BTC", "ETH", "SOL"] |
| `min_position_size` | Minimum position size (% of balance, WITHOUT leverage) | 0.7 (70%) |
| `max_position_size` | Maximum position size (% of balance, WITHOUT leverage) | 0.9 (90%) |
| `delay_between_trades_min/max` | Delay between trades in seconds (range) | 30-60 |
| `use_maker_orders` | Use limit orders (maker) instead of market orders | true |
| `take_profit_percent_min/max` | Take Profit in percentages (range) | 0.002-0.004 (0.2%-0.4%) |
| `stop_loss_percent_min/max` | Stop Loss in percentages (range) | 0.002-0.004 (0.2%-0.4%) |
| `slippage_min/max` | Slippage for limit orders in percentages (range) | 0.0003-0.0005 (0.03%-0.05%) |

**Important:** 
- `min_position_size` and `max_position_size` are specified as percentages of balance (0.0-1.0), **WITHOUT leverage**
- The software automatically multiplies by `leverage` when calculating position size on the exchange
- Example: balance $100, `min_position_size: 0.8`, `leverage: 5` → position $80 without leverage → $400 with 5x leverage

## 📊 How it works

```
┌─────────────────────────────────────┐
│  1. Select random market            │
│     (BTC, ETH or SOL)               │
├─────────────────────────────────────┤
│  2. Select random direction         │
│     (LONG or SHORT)                 │
├─────────────────────────────────────┤
│  3. Open position                   │
│     • Entire balance × leverage     │
│     • Limit order with slippage     │
├─────────────────────────────────────┤
│  4. Hold position                   │
│     • hold_time minutes              │
│     • Check max_check_price          │
├─────────────────────────────────────┤
│  5. Close position                  │
│     • Limit order                   │
├─────────────────────────────────────┤
│  6. Repeat until target_volume      │
└─────────────────────────────────────┘
```

## ⚠️ Important

- The bot uses **entire balance** with leverage
- Trade direction is selected **randomly** (LONG/SHORT)
- `max_check_price` protects against large losses
- Test with small amounts!

## 📁 Project Structure

```
pacificavolumebot/
├── pacifica_bot.py       # Main bot code
├── config.json           # Configuration
├── accounts.csv          # Accounts (create yourself)
├── accounts_sample.csv   # Account template
├── requirements.txt      # Dependencies
├── README.md             # Documentation
└── logs/                 # Logs (created automatically)
```

## 📞 Contacts

**Telegram:** https://t.me/suzuich or directly https://t.me/suzumsky

⚠️ **Disclaimer:** Cryptocurrency trading involves risks. The bot does not guarantee profit. The author is not responsible for losses.

**Support**

TRC-20: TSCaQcRcoVM2tEtusXEDF87VQdjTdPr8dv

EVM: 0x30eb5840e0Dfdc75C1B6E1977cc529C832cBF3a1

SOL: 2NKmeCMxdEaTXxKw3jhUYoJSmEixm7YdH5P1drPvZQmy

Thank you for your support!
