# 🌊 Pacifica Volume Bot

Перед использованием зарегистрируйтесь на сайте PACIFICA: https://app.pacifica.fi?referral=bluedepp

В трейдинг окне (Join Closed Beta) используйте код:

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

### Логика работы:

1. Открыть позицию (весь баланс с плечом)
2. Удержать `hold_time` минут
3. Проверять `max_check_price` (закрыть раньше если убыток превышает лимит)
4. Закрыть позицию
5. Повторить до достижения `target_volume`

## 🚀 Установка

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Создание accounts.csv

Создайте файл `accounts.csv` по образцу `accounts_sample.csv`:

```csv
account_name,api_key,api_secret,walletaddress
main,YOUR_WALLET_PUBLIC_KEY,YOUR_WALLET_PRIVATE_KEY,YOUR_WALLET_ADDRESS
```

**Поля:**
- `api_key` - публичный ключ(адресс) Solana кошелька (base58)
- `api_secret` - приватный ключ Solana кошелька (base58)
- `walletaddress` - адрес основного аккаунта (для API Agent)

### 3. Запуск

```bash
python pacifica_bot.py
```

## ⚙️ Конфигурация (config.json)

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

### Параметры:

| Параметр | Описание | Пример |
|----------|----------|--------|
| `hold_time_min/max` | Время удержания позиции в минутах (диапазон) | 3-5 |
| `target_volume` | Целевой объём торгов в USD | 10000 |
| `leverage` | Кредитное плечо | 5 |
| `markets` | Рынки для торговли | ["BTC", "ETH", "SOL"] |
| `min_position_size` | Минимальный размер позиции (% от баланса, БЕЗ плеча) | 0.7 (70%) |
| `max_position_size` | Максимальный размер позиции (% от баланса, БЕЗ плеча) | 0.9 (90%) |
| `delay_between_trades_min/max` | Задержка между сделками в секундах (диапазон) | 30-60 |
| `use_maker_orders` | Использовать лимитные ордера (maker) вместо рыночных | true |
| `take_profit_percent_min/max` | Take Profit в процентах (диапазон) | 0.002-0.004 (0.2%-0.4%) |
| `stop_loss_percent_min/max` | Stop Loss в процентах (диапазон) | 0.002-0.004 (0.2%-0.4%) |
| `slippage_min/max` | Slippage для лимитных ордеров в процентах (диапазон) | 0.0003-0.0005 (0.03%-0.05%) |

**Важно:** 
- `min_position_size` и `max_position_size` указываются в процентах от баланса (0.0-1.0), **БЕЗ учета плеча**
- Софт автоматически умножает на `leverage` при расчете размера позиции на бирже
- Например: баланс $100, `min_position_size: 0.8`, `leverage: 5` → позиция $80 без плеча → $400 с плечом 5x

## 📊 Как это работает

```
┌─────────────────────────────────────┐
│  1. Выбор случайного рынка          │
│     (BTC, ETH или SOL)              │
├─────────────────────────────────────┤
│  2. Выбор случайного направления    │
│     (LONG или SHORT)                │
├─────────────────────────────────────┤
│  3. Открытие позиции                │
│     • Весь баланс × leverage        │
│     • Лимитный ордер со slippage    │
├─────────────────────────────────────┤
│  4. Удержание позиции               │
│     • hold_time минут               │
│     • Проверка max_check_price      │
├─────────────────────────────────────┤
│  5. Закрытие позиции                │
│     • Лимитный ордер                │
├─────────────────────────────────────┤
│  6. Повторить до target_volume      │
└─────────────────────────────────────┘
```

## ⚠️ Важно

- Бот использует **весь баланс** с плечом
- Направление сделки выбирается **случайно** (LONG/SHORT)
- `max_check_price` защищает от больших убытков
- Тестируйте на небольших суммах!

## 📁 Структура проекта

```
pacificavolumebot/
├── pacifica_bot.py       # Основной код бота
├── config.json           # Конфигурация
├── accounts.csv          # Аккаунты (создать самому)
├── accounts_sample.csv   # Пример аккаунтов
├── requirements.txt      # Зависимости
├── README.md             # Документация
└── logs/                 # Логи (создаётся автоматически)
```

## 📞 Контакты

**Telegram:** https://t.me/suzuich или напрямую https://t.me/suzumsky

⚠️ **Disclaimer:** Торговля криптовалютой сопряжена с рисками. Бот не гарантирует прибыль. Автор не несёт ответственности за убытки.

**Support**

TRC-20: TSCaQcRcoVM2tEtusXEDF87VQdjTdPr8dv

EVM: 0x30eb5840e0Dfdc75C1B6E1977cc529C832cBF3a1

SOL: 2NKmeCMxdEaTXxKw3jhUYoJSmEixm7YdH5P1drPvZQmy

Thank you for your support!
