#!/usr/bin/env python3
"""
Pacifica Volume Bot v2.0
========================

Разработано: GOATHAM DAO

Чистая реализация согласно официальной документации Pacifica:
https://docs.pacifica.fi/api-documentation/api

Использует официальный Python SDK:
https://github.com/pacifica-fi/python-sdk
"""

import asyncio
import json
import random
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

from loguru import logger
from colorama import init, Fore, Style

from pacifica_sdk.async_.exchange import Exchange
from pacifica_sdk.async_.info import Info
from pacifica_sdk.constants import MAINNET_API_URL
from pacifica_sdk.enums import Side, TIF
from pacifica_sdk.utils.error import ApiError, ServerError
from pacifica_sdk.models.requests import (
    CancelAllOrders,
    CancelOrder,
    CreateLimitOrder,
    CreateMarketOrder,
    CreateTPSLOrder,
    GetAccountInfo,
    GetAccountPositions,
    GetOpenOrders,
    GetOrderHistoryById,
    StopOrderInfo,
    UpdateLeverage,
)
from pacifica_sdk.models.responses import OpenOrderInfo
from pacifica_sdk.models.responses import AccountInfo, MarketInfo, PositionInfo, PriceInfo

init(autoreset=True)


@dataclass
class Config:
    """Конфигурация бота с поддержкой рандомизации"""
    # Время удержания позиции (минуты)
    hold_time_min: int = 6
    hold_time_max: int = 12
    
    target_volume: float = 10000  # USD
    
    # Плечо (фиксированное значение)
    leverage: int = 5
    
    markets: List[str] = None
    
    # Размер позиции (% от баланса, БЕЗ учета плеча)
    # Например: 0.8 = 80% от баланса, плечо применяется автоматически
    min_position_size: float = 0.7  # 70% от баланса
    max_position_size: float = 0.9  # 90% от баланса
    
    # Задержка между сделками (секунды)
    delay_between_trades_min: int = 30
    delay_between_trades_max: int = 60
    
    use_maker_orders: bool = True
    
    # Take profit (проценты)
    take_profit_percent_min: float = 0.0005  # 0.05%
    take_profit_percent_max: float = 0.0012  # 0.12%
    
    # Stop loss (проценты)
    stop_loss_percent_min: float = 0.002  # 0.2%
    stop_loss_percent_max: float = 0.004  # 0.4%
    
    # Slippage для лимитных ордеров (проценты)
    slippage_min: float = 0.0003  # 0.03%
    slippage_max: float = 0.0007  # 0.07%
    
    def __post_init__(self):
        if self.markets is None:
            self.markets = ["BTC", "ETH", "SOL"]
    
    def get_random_hold_time(self) -> int:
        """Случайное время удержания позиции"""
        return random.randint(self.hold_time_min, self.hold_time_max)
    
    def get_random_position_size(self) -> float:
        """Случайный размер позиции в процентах от баланса (0.0-1.0)"""
        return random.uniform(self.min_position_size, self.max_position_size)
    
    def get_random_delay(self) -> int:
        """Случайная задержка между сделками"""
        return random.randint(self.delay_between_trades_min, self.delay_between_trades_max)
    
    def get_random_take_profit(self) -> float:
        """Случайный take profit"""
        return random.uniform(self.take_profit_percent_min, self.take_profit_percent_max)
    
    def get_random_stop_loss(self) -> float:
        """Случайный stop loss"""
        return random.uniform(self.stop_loss_percent_min, self.stop_loss_percent_max)
    
    def get_random_slippage(self) -> float:
        """Случайный slippage"""
        return random.uniform(self.slippage_min, self.slippage_max)


class PacificaBot:
    """
    Volume Bot для Pacifica DEX
    
    Согласно официальной документации:
    https://docs.pacifica.fi/api-documentation/api
    """
    
    def __init__(
        self,
        private_key: str,
        public_key: str,
        agent_wallet: Optional[str] = None,
        config: Optional[Config] = None
    ):
        """
        Args:
            private_key: Приватный ключ Solana кошелька или API Agent (base58)
            public_key: Публичный ключ основного аккаунта (base58)
            agent_wallet: Публичный ключ API Agent (если используется)
            config: Конфигурация бота
        """
        self.private_key = private_key
        self.public_key = public_key
        self.agent_wallet = agent_wallet
        self.config = config or Config()
        
        self.exchange: Optional[Exchange] = None
        self.info: Optional[Info] = None
        self.current_slippage = self.config.get_random_slippage()
        self.current_take_profit = self.config.get_random_take_profit()
        self.current_stop_loss = self.config.get_random_stop_loss()
        
        # Плечо (фиксированное значение из конфига)
        self.current_leverage = self.config.leverage
        
        # Статистика
        self.total_volume = 0.0
        self.total_pnl = 0.0
        self.trades_count = 0
        
    async def __aenter__(self):
        await self.init()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def init(self):
        """Инициализация клиентов"""
        logger.info(f"{Fore.GREEN}Инициализация Pacifica клиентов...")
        
        self.exchange = Exchange(
            private_key=self.private_key,
            public_key=self.public_key,
            agent_wallet=self.agent_wallet,
            base_url=MAINNET_API_URL,
            expiry_window=30_000
        )
        
        if hasattr(self.exchange, 'keypair') and self.exchange.keypair:
            self.exchange.info.keypair = self.exchange.keypair
            self.exchange.info.public_key = self.exchange.public_key
            self.exchange.info.agent_wallet = self.exchange.agent_wallet
            self.exchange.info.expiry_window = self.exchange.expiry_window
            logger.info(f"{Fore.GREEN}✓ Info настроен с подписью для авторизованных GET запросов")
            logger.debug(f"  Public key: {self.exchange.info.public_key}")
            if self.exchange.info.agent_wallet:
                logger.debug(f"  Agent wallet: {self.exchange.info.agent_wallet}")
        else:
            logger.warning(f"{Fore.YELLOW}⚠ Exchange не имеет keypair - GET запросы к приватным эндпоинтам могут не работать")
        
        logger.info(f"{Fore.GREEN}✓ Клиенты инициализированы")
        
    async def close(self):
        """Закрытие соединений"""
        if self.exchange:
            await self.exchange.close()
            
    async def get_account_info(self) -> Optional[AccountInfo]:
        """Получение информации об аккаунте"""
        try:
            from pacifica_sdk.utils.tools import build_signer_request
            from pacifica_sdk.enums import OperationType
            import time
            from pacifica_sdk.utils.signing import sign_message
            
            params = GetAccountInfo(account=self.public_key)
            try:
                account = await self.exchange.info.get_account_info(params)
                return account
            except Exception as e1:
                logger.debug(f"Попытка через Info не удалась: {e1}")
                
                timestamp = int(time.time() * 1000)
                expiry_window = self.exchange.expiry_window
                request_data = {"account": self.public_key}
                
                signature = sign_message(
                    keypair=self.exchange.keypair,
                    timestamp=timestamp,
                    operation_type=OperationType.UPDATE_LEVERAGE,
                    operation_data=request_data,
                    expiry_window=expiry_window
                )
                
                headers = {
                    "Content-Type": "application/json",
                    "account": self.public_key,
                    "signature": signature,
                    "timestamp": str(timestamp),
                    "expiry_window": str(expiry_window)
                }
                if self.agent_wallet:
                    headers["agent_wallet"] = self.agent_wallet
                
                url = f"{self.exchange.base_url}/account"
                async with self.exchange.session.get(
                    url,
                    headers=headers,
                    params=request_data
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and "data" in data:
                            return AccountInfo.model_validate(data["data"])
                    else:
                        text = await response.text()
                        logger.error(f"Ошибка HTTP {response.status}: {text[:200]}")
                        return None
                        
        except Exception as e:
            logger.error(f"Ошибка получения аккаунта: {e}")
            return None
            
    async def get_balance(self) -> Optional[float]:
        """Получение доступного баланса"""
        account = await self.get_account_info()
        if account:
            if hasattr(account, 'available_to_spend'):
                return float(account.available_to_spend)
            for field in ['balance', 'account_equity']:
                if hasattr(account, field):
                    value = getattr(account, field)
                    if value:
                        return float(value)
        return None
        
    async def get_markets(self) -> List[MarketInfo]:
        """Получение списка рынков"""
        try:
            markets = await self.exchange.info.get_market_info()
            return markets
        except Exception as e:
            logger.error(f"Ошибка получения рынков: {e}")
            return []
            
    async def get_prices(self, retries: int = 3) -> List[PriceInfo]:
        """Получение текущих цен с таймаутом и повторными попытками"""
        for attempt in range(retries):
            try:
                logger.debug(f"Запрос цен через API (попытка {attempt + 1}/{retries})...")
                # Добавляем таймаут для запроса (30 секунд)
                prices = await asyncio.wait_for(
                    self.exchange.info.get_prices(),
                    timeout=30.0
                )
                if prices:
                    logger.debug(f"✓ Получено цен: {len(prices)}")
                    return prices
                else:
                    logger.warning(f"Пустой ответ от API (попытка {attempt + 1}/{retries})")
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут получения цен (попытка {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))  # Экспоненциальная задержка
                    continue
            except Exception as e:
                error_str = str(e)
                logger.error(f"Ошибка получения цен (попытка {attempt + 1}/{retries}): {error_str}")
                if "CloudFront" in error_str or "403" in error_str:
                    # CloudFront блокирует - пробуем ещё раз с задержкой
                    if attempt < retries - 1:
                        wait_time = 5 * (attempt + 1)
                        logger.info(f"CloudFront блокирует, ждём {wait_time}с...")
                        await asyncio.sleep(wait_time)
                        continue
                elif attempt < retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")
        
        logger.error("Не удалось получить цены после всех попыток")
        return []
            
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Получение текущей цены для символа"""
        # Пробуем получить через get_prices
        prices = await self.get_prices()
        if prices:
            for price_info in prices:
                if price_info.symbol == symbol:
                    # Согласно SDK: PriceInfo имеет поле 'mark', а не 'mark_price'
                    price = float(price_info.mark)
                    logger.debug(f"Цена {symbol}: ${price:.2f}")
                    return price
        
        # Fallback: пробуем получить через markets (если есть mark_price)
        logger.warning(f"Цена {symbol} не найдена в prices, пробуем через markets...")
        try:
            markets = await self.get_markets()
            for market in markets:
                if market.symbol == symbol:
                    # Проверяем разные поля для цены
                    for price_field in ['mark_price', 'index_price', 'last_price', 'price']:
                        if hasattr(market, price_field):
                            price_value = getattr(market, price_field)
                            if price_value:
                                try:
                                    price = float(price_value)
                                    logger.info(f"Цена {symbol} из markets: ${price:.2f}")
                                    return price
                                except (ValueError, TypeError):
                                    continue
        except Exception as e:
            logger.debug(f"Ошибка получения цены через markets: {e}")
        
        logger.error(f"Не удалось получить цену для {symbol}")
        return None
        
    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Получение funding rate для символа"""
        markets = await self.get_markets()
        for market in markets:
            if market.symbol == symbol:
                # Проверяем оба поля: funding_rate и next_funding_rate
                current_funding = float(market.funding_rate)
                next_funding = float(market.next_funding_rate)
                
                # Логируем для отладки
                logger.debug(f"{symbol} - Current funding: {current_funding}, Next funding: {next_funding}")
                
                # Используем next_funding_rate (следующий funding rate)
                # так как он более актуален для принятия решений
                return next_funding
        return None
        
    async def get_tick_size(self, symbol: str) -> Optional[float]:
        """Получение tick size для символа"""
        markets = await self.get_markets()
        for market in markets:
            if market.symbol == symbol:
                return float(market.tick_size)
        return None
        
    async def get_lot_size(self, symbol: str) -> Optional[float]:
        """Получение lot size (минимальный размер ордера) для символа"""
        markets = await self.get_markets()
        for market in markets:
            if market.symbol == symbol:
                return float(market.lot_size)
        return None
        
    def round_to_lot(self, amount: float, lot_size: float) -> str:
        """Округление количества до кратного lot size"""
        if lot_size <= 0:
            return str(amount)
        # Округляем вниз до ближайшего кратного lot_size
        rounded = (amount // lot_size) * lot_size
        # Убираем лишние нули
        return f"{rounded:.{len(str(lot_size).split('.')[-1])}f}".rstrip('0').rstrip('.')
        
    def round_to_tick(self, price: float, tick_size: float) -> str:
        """Округление цены до кратного tick size"""
        if tick_size <= 0:
            return str(price)
        # Округляем до ближайшего кратного tick_size
        rounded = round(price / tick_size) * tick_size
        
        # Определяем количество знаков после запятой из tick_size
        tick_str = str(tick_size)
        if '.' in tick_str:
            decimals = len(tick_str.split('.')[-1].rstrip('0'))
        else:
            decimals = 0
            
        # Форматируем с правильным количеством знаков
        if decimals > 0:
            formatted = f"{rounded:.{decimals}f}"
        else:
            formatted = f"{int(rounded)}"
            
        return formatted
        
    async def get_max_leverage(self, symbol: str) -> Optional[int]:
        """Получение максимального плеча для рынка"""
        try:
            markets = await self.get_markets()
            for market in markets:
                if market.symbol == symbol:
                    max_leverage = int(market.max_leverage) if hasattr(market, 'max_leverage') else None
                    logger.debug(f"Максимальное плечо для {symbol}: {max_leverage}x")
                    return max_leverage
            return None
        except Exception as e:
            logger.debug(f"Ошибка получения максимального плеча для {symbol}: {e}")
            return None
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Установка плеча для рынка
        
        Для открытых позиций можно только увеличивать плечо
        """
        try:
            # Проверяем, есть ли открытая позиция для этого символа
            positions = await self.get_positions(fast_mode=True)
            current_position_leverage = None
            
            for pos in positions:
                if pos.symbol == symbol and abs(float(pos.amount)) > 0.000001:
                    # Есть открытая позиция - получаем текущее плечо
                    if hasattr(pos, 'leverage') and pos.leverage:
                        current_position_leverage = int(pos.leverage)
                        logger.debug(f"Найдена открытая позиция {symbol} с плечом {current_position_leverage}x")
                    break
            
            # Если есть открытая позиция, проверяем правило: можно только увеличивать
            if current_position_leverage is not None:
                if leverage < current_position_leverage:
                    logger.warning(
                        f"{Fore.YELLOW}⚠ Для открытой позиции {symbol} можно только УВЕЛИЧИВАТЬ плечо. "
                        f"Текущее: {current_position_leverage}x, запрошенное: {leverage}x. "
                        f"Используем текущее {current_position_leverage}x"
                    )
                    leverage = current_position_leverage
                elif leverage == current_position_leverage:
                    logger.info(f"Плечо {symbol} уже установлено на {leverage}x")
                    return True
            
            # Проверяем максимальное плечо для рынка
            max_leverage = await self.get_max_leverage(symbol)
            if max_leverage:
                if leverage > max_leverage:
                    logger.warning(
                        f"{Fore.YELLOW}Плечо {leverage}x превышает максимальное для {symbol} "
                        f"({max_leverage}x). Используем {max_leverage}x"
                    )
                    leverage = max_leverage
                elif leverage < 1:
                    logger.warning(
                        f"{Fore.YELLOW}Плечо {leverage}x слишком мало для {symbol}. "
                        f"Используем минимальное 1x"
                    )
                    leverage = 1
            else:
                logger.debug(f"Не удалось получить максимальное плечо для {symbol}, используем запрошенное {leverage}x")
            
            update = UpdateLeverage(symbol=symbol, leverage=leverage)
            await self.exchange.update_leverage(update)
            logger.info(f"{Fore.GREEN}✓ Плечо {leverage}x установлено для {symbol}")
            return True
            
        except ApiError as e:
            error_str = str(e)
            error_msg = e.error_message if hasattr(e, 'error_message') else str(e)
            error_code = e.code if hasattr(e, 'code') else None
            
            # Проверяем, есть ли открытая позиция
            positions = await self.get_positions(fast_mode=True)
            has_open_position = False
            current_pos_leverage = None
            
            for pos in positions:
                if pos.symbol == symbol and abs(float(pos.amount)) > 0.000001:
                    has_open_position = True
                    if hasattr(pos, 'leverage') and pos.leverage:
                        current_pos_leverage = int(pos.leverage)
                    break
            
            # Если ошибка о недопустимом плече
            if "InvalidLeverage" in error_str or "invalid leverage" in error_msg.lower() or (error_code and error_code == 400):
                if has_open_position and current_pos_leverage:
                    # Для открытых позиций можно только увеличивать плечо
                    if leverage < current_pos_leverage:
                        logger.error(
                            f"{Fore.RED}✗ Нельзя уменьшить плечо для открытой позиции {symbol}. "
                            f"Текущее: {current_pos_leverage}x, запрошенное: {leverage}x"
                        )
                        return False
                    else:
                        # Пробуем увеличить плечо
                        logger.warning(
                            f"{Fore.YELLOW}Плечо {leverage}x недопустимо для {symbol} с открытой позицией. "
                            f"Текущее: {current_pos_leverage}x. Пробуем увеличить..."
                        )
                        # Пробуем увеличить плечо, начиная с leverage + 1 до max_leverage
                        max_leverage = await self.get_max_leverage(symbol)
                        if max_leverage:
                            for test_leverage in range(leverage + 1, max_leverage + 1):
                                try:
                                    logger.debug(f"Пробуем установить плечо {test_leverage}x для {symbol}...")
                                    update = UpdateLeverage(symbol=symbol, leverage=test_leverage)
                                    await self.exchange.update_leverage(update)
                                    logger.info(
                                        f"{Fore.GREEN}✓ Плечо {test_leverage}x установлено для {symbol} "
                                        f"(вместо запрошенного {leverage}x)"
                                    )
                                    self.current_leverage = test_leverage
                                    return True
                                except Exception:
                                    continue
                        logger.error(
                            f"{Fore.RED}✗ Не удалось установить допустимое плечо для {symbol} с открытой позицией"
                        )
                        return False
                else:
                    # Нет открытой позиции - пробуем уменьшить плечо
                    logger.warning(
                        f"{Fore.YELLOW}Плечо {leverage}x недопустимо для {symbol} "
                        f"(ошибка: {error_msg}), пробуем уменьшить..."
                    )
                    # Пробуем уменьшить плечо, начиная с leverage - 1 до 1
                    for test_leverage in range(leverage - 1, 0, -1):
                        try:
                            logger.debug(f"Пробуем установить плечо {test_leverage}x для {symbol}...")
                            update = UpdateLeverage(symbol=symbol, leverage=test_leverage)
                            await self.exchange.update_leverage(update)
                            logger.info(
                                f"{Fore.GREEN}✓ Плечо {test_leverage}x установлено для {symbol} "
                                f"(вместо запрошенного {leverage}x)"
                            )
                            self.current_leverage = test_leverage
                            return True
                        except Exception as e2:
                            if test_leverage == 1:
                                logger.error(
                                    f"{Fore.RED}✗ Не удалось установить допустимое плечо для {symbol}. "
                                    f"Последняя ошибка: {e2}"
                                )
                                return False
                            continue
            else:
                logger.error(
                    f"{Fore.RED}Ошибка установки плеча для {symbol}: "
                    f"[{e.status_code}] code={error_code} message='{error_msg}'"
                )
                return False
                
        except Exception as e:
            error_str = str(e)
            # Если ошибка о недопустимом плече - пробуем уменьшить
            if "InvalidLeverage" in error_str or "invalid leverage" in error_str.lower():
                logger.warning(f"{Fore.YELLOW}Плечо {leverage}x недопустимо для {symbol}, пробуем уменьшить...")
                # Пробуем уменьшить плечо, начиная с leverage - 1 до 1
                for test_leverage in range(leverage - 1, 0, -1):
                    try:
                        logger.debug(f"Пробуем установить плечо {test_leverage}x для {symbol}...")
                        update = UpdateLeverage(symbol=symbol, leverage=test_leverage)
                        await self.exchange.update_leverage(update)
                        logger.info(
                            f"{Fore.GREEN}✓ Плечо {test_leverage}x установлено для {symbol} "
                            f"(вместо запрошенного {leverage}x)"
                        )
                        # Обновляем текущее плечо для этого рынка
                        self.current_leverage = test_leverage
                        return True
                    except Exception as e2:
                        if test_leverage == 1:
                            logger.error(
                                f"{Fore.RED}✗ Не удалось установить допустимое плечо для {symbol}: {e2}"
                            )
                            return False
                        continue
            else:
                logger.error(f"{Fore.RED}Ошибка установки плеча для {symbol}: {e}")
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")
                return False
            
    async def get_positions(self, retries: int = 3, fast_mode: bool = False) -> List[PositionInfo]:
        """Получение открытых позиций с повторными попытками"""
        from pacifica_sdk.utils.tools import build_signer_request, get_timestamp_ms
        from pacifica_sdk.enums import OperationType
        from pacifica_sdk.models.responses import ApiResponse
        
        params = GetAccountPositions(account=self.public_key)
        
        for attempt in range(retries):
            try:
                if hasattr(self.exchange.info, 'keypair') and self.exchange.info.keypair:
                    signed_request = build_signer_request(
                        keypair=self.exchange.info.keypair,
                        operation_type=OperationType.UPDATE_LEVERAGE,
                        params=params.model_dump(exclude_none=True),
                        expiry_window=self.exchange.info.expiry_window,
                        public_key=self.exchange.info.public_key,
                        agent_wallet=self.exchange.info.agent_wallet,
                    )
                    
                    headers = {
                        "Content-Type": "application/json",
                        "account": signed_request.get("account"),
                        "signature": signed_request.get("signature"),
                        "timestamp": str(signed_request.get("timestamp")),
                        "expiry_window": str(signed_request.get("expiry_window")),
                    }
                    if signed_request.get("agent_wallet"):
                        headers["agent_wallet"] = signed_request.get("agent_wallet")
                    
                    url = f"{self.exchange.info.base_url}/positions"
                    async with self.exchange.info.session.get(
                        url,
                        headers=headers,
                        params={"account": self.public_key},
                    ) as response:
                        if response.status == 200:
                            raw = await response.json()
                            if raw.get("success"):
                                data = raw.get("data", [])
                                positions = [PositionInfo(**item) for item in data]
                                logger.debug(f"✓ Получено позиций: {len(positions)}")
                                for pos in positions:
                                    logger.debug(f"  Позиция: {pos.symbol}, amount={pos.amount}, entry_price={pos.entry_price if hasattr(pos, 'entry_price') else 'N/A'}")
                                return positions
                            else:
                                raise Exception(f"API error: {raw.get('error')}")
                        else:
                            text = await response.text()
                            raise Exception(f"HTTP {response.status}: {text}")
                else:
                    positions = await self.exchange.info.get_account_positions(params)
                    logger.debug(f"✓ Получено позиций: {len(positions)}")
                    for pos in positions:
                        logger.debug(f"  Позиция: {pos.symbol}, amount={pos.amount}, entry_price={pos.entry_price if hasattr(pos, 'entry_price') else 'N/A'}")
                    return positions
            except Exception as e:
                error_str = str(e)
                if "CloudFront" in error_str or "403" in error_str or "Failed to decode JSON" in error_str:
                    if attempt < retries - 1:
                        if fast_mode:
                            # В быстром режиме используем короткие задержки: 2, 4, 8 секунд
                            base_delay = 2 * (2 ** attempt)
                            jitter = random.uniform(0, base_delay * 0.3)
                            wait_time = min(base_delay + jitter, 10)  # Максимум 10 секунд
                        else:
                            # В обычном режиме: 3, 6, 12 секунд (меньше, чем было)
                            base_delay = 3 * (2 ** attempt)
                            jitter = random.uniform(0, base_delay * 0.3)
                            wait_time = min(base_delay + jitter, 15)  # Максимум 15 секунд
                        
                        logger.debug(f"CloudFront блокирует (попытка {attempt + 1}/{retries}), ждём {wait_time:.1f}с...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.debug(f"CloudFront блокирует после {retries} попыток, возвращаем пустой список")
                        return []
                else:
                    logger.error(f"Ошибка получения позиций: {e}")
                    # Для других ошибок не делаем повторные попытки
                    return []
        
        return []
            
    async def place_order(
        self,
        symbol: str,
        side: Side,
        size_usd: float,
        price: Optional[float] = None,
        reduce_only: bool = False
    ) -> Optional[Dict]:
        """
        Размещение ордера
        
        Args:
            symbol: Торговый символ (например, "BTC")
            side: Side.BID (buy) или Side.ASK (sell)
            size_usd: Размер позиции в USD
            price: Цена для limit ордера (если None - market ордер)
            reduce_only: Только для закрытия позиции
        """
        try:
            # Конвертируем размер из USD в количество базовой валюты
            if not price:
                price = await self.get_current_price(symbol)
                if not price:
                    logger.error(f"Не удалось получить цену для {symbol}")
                    return None
            
            # Размер в базовой валюте = размер в USD / цена
            amount_base = size_usd / price
            
            # Округляем до lot size
            lot_size = await self.get_lot_size(symbol)
            if lot_size:
                amount_str = self.round_to_lot(amount_base, lot_size)
                amount_base = float(amount_str)
                logger.debug(f"Размер округлён до lot size {lot_size}: {amount_base} {symbol}")
            else:
                amount_str = str(amount_base)
                
            if amount_base <= 0:
                logger.error(f"Размер ордера слишком мал: {amount_base}")
                return None
            
            if price and self.config.use_maker_orders:
                # Limit ордер (maker) - округляем цену до tick size
                tick_size = await self.get_tick_size(symbol)
                if tick_size:
                    price_str = self.round_to_tick(price, tick_size)
                else:
                    price_str = str(price)
                    
                order = CreateLimitOrder(
                    symbol=symbol,
                    side=side,
                    price=price_str,
                    amount=amount_str,
                    tif=TIF.GTC,
                    reduce_only=reduce_only
                )
            else:
                # Market ордер
                order = CreateMarketOrder(
                    symbol=symbol,
                    side=side,
                    price=str(price),
                    amount=amount_str,
                    slippage=self.current_slippage,
                    reduce_only=reduce_only
                )
                
            result = await self.exchange.create_order(order)
            
            if result and result.data:
                logger.info(f"✓ Ордер размещен: {side.value} {amount_base:.4f} {symbol} (${size_usd:.2f})")
                return result.data.model_dump() if hasattr(result.data, 'model_dump') else result.data
            return None
            
        except Exception as e:
            logger.error(f"Ошибка размещения ордера: {e}")
            return None
            
    async def cancel_order(self, order_id: int, symbol: str) -> bool:
        """Отмена ордера"""
        try:
            cancel = CancelOrder(order_id=order_id, symbol=symbol)
            result = await self.exchange.cancel_order(cancel)
            if result:
                logger.info(f"✓ Ордер #{order_id} отменён")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка отмены ордера #{order_id}: {e}")
            return False
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OpenOrderInfo]:
        """Получение открытых ордеров"""
        try:
            params = GetOpenOrders(account=self.public_key)
            if symbol:
                # SDK может не поддерживать фильтрацию по symbol в GetOpenOrders
                # Получаем все и фильтруем вручную
                orders = await self.exchange.info.get_open_orders(params)
                return [o for o in orders if o.symbol == symbol]
            else:
                orders = await self.exchange.info.get_open_orders(params)
                return orders
        except Exception as e:
            logger.debug(f"Ошибка получения открытых ордеров: {e}")
            return []
    
    async def cancel_all_orders(self, symbol: Optional[str] = None, exclude_reduce_only: bool = False) -> bool:
        """Отмена всех ордеров"""
        try:
            if symbol:
                # Отменяем ордера для конкретного символа
                cancel_request = CancelAllOrders(
                    all_symbols=False,
                    exclude_reduce_only=exclude_reduce_only,
                    symbol=symbol
                )
                logger.info(f"{Fore.YELLOW}Отмена всех ордеров для {symbol}...")
            else:
                # Отменяем все ордера для всех символов
                cancel_request = CancelAllOrders(
                    all_symbols=True,
                    exclude_reduce_only=exclude_reduce_only,
                    symbol=None
                )
                logger.info(f"{Fore.YELLOW}Отмена всех ордеров для всех символов...")
            
            result = await self.exchange.cancel_all_orders(cancel_request)
            
            if result and result.data:
                cancelled_count = result.data.cancelled_count if hasattr(result.data, 'cancelled_count') else 0
                logger.info(f"{Fore.GREEN}✓ Отменено ордеров: {cancelled_count}")
                return True
            else:
                logger.warning("Не удалось получить информацию об отменённых ордерах")
                return True  # Считаем успешным, если нет ошибки
                
        except ApiError as e:
            logger.error(
                f"{Fore.RED}Ошибка отмены всех ордеров: "
                f"[{e.status_code}] code={e.code} message='{e.error_message}'"
            )
            return False
        except Exception as e:
            logger.error(f"{Fore.RED}Ошибка отмены всех ордеров: {e}")
            return False
    
    async def close_all_positions(self) -> bool:
        """
        Закрытие всех открытых позиций
        
        Returns:
            True если все позиции закрыты или их не было, False если ошибка
        """
        try:
            positions = await self.get_positions()
            if not positions:
                logger.debug("Нет открытых позиций для закрытия")
                return True
            
            closed_count = 0
            for pos in positions:
                if abs(float(pos.amount)) > 0.000001:
                    logger.info(f"{Fore.YELLOW}Закрытие позиции {pos.symbol}...")
                    if await self.close_position(pos.symbol):
                        closed_count += 1
                        await asyncio.sleep(1)  # Задержка между закрытиями
            
            if closed_count > 0:
                logger.info(f"{Fore.GREEN}✓ Закрыто позиций: {closed_count}")
                # Ждём, чтобы позиции точно закрылись
                await asyncio.sleep(2)
            
            return True
        except Exception as e:
            logger.error(f"{Fore.RED}Ошибка закрытия всех позиций: {e}")
            return False
    
    async def cleanup_before_trade(self):
        """
        Очистка перед новой сделкой:
        - Отменяет все открытые ордера
        - Закрывает все открытые позиции
        """
        logger.info(f"{Fore.CYAN}🧹 Очистка перед новой сделкой...")
        
        # Сначала закрываем все позиции
        await self.close_all_positions()
        
        # Ждём немного, чтобы позиции закрылись
        await asyncio.sleep(2)
        
        # Затем отменяем все оставшиеся ордера (включая reduce-only)
        await self.cancel_all_orders(exclude_reduce_only=False)
        
        # Ещё одна небольшая задержка для завершения операций
        await asyncio.sleep(1)
        
        logger.info(f"{Fore.GREEN}✓ Очистка завершена")
    
    async def close_position(self, symbol: str) -> bool:
        """Закрытие позиции"""
        positions = await self.get_positions()
        position_found = False
        
        for pos in positions:
            if pos.symbol == symbol and abs(float(pos.amount)) > 0.000001:
                position_found = True
                amount_base = abs(float(pos.amount))
                current_price = await self.get_current_price(symbol)
                if not current_price:
                    logger.error(f"Не удалось получить цену для закрытия позиции {symbol}")
                    return False
                    
                size_usd = amount_base * current_price
                
                if pos.side == Side.BID:
                    close_side = Side.ASK
                else:
                    close_side = Side.BID
                
                logger.info(
                    f"{Fore.YELLOW}Закрытие позиции {symbol}: "
                    f"позиция {pos.side.value}, закрываем через {close_side.value}, "
                    f"размер: {amount_base:.6f} ({size_usd:.2f} USD)"
                )
                
                result = await self.place_order(
                    symbol=symbol,
                    side=close_side,
                    size_usd=size_usd,
                    reduce_only=True
                )
                
                if result:
                    # Ждём немного, чтобы ордер исполнился
                    await asyncio.sleep(2)
                    
                    # Проверяем, закрылась ли позиция
                    positions_after = await self.get_positions(fast_mode=True)
                    position_closed = True
                    for pos_after in positions_after:
                        if pos_after.symbol == symbol and abs(float(pos_after.amount)) > 0.000001:
                            position_closed = False
                            break
                    
                    # Если позиция закрыта, отменяем все открытые ордера для этого символа
                    if position_closed:
                        logger.debug(f"Позиция {symbol} закрыта, проверяем открытые ордера...")
                        open_orders = await self.get_open_orders(symbol)
                        if open_orders:
                            logger.info(f"{Fore.YELLOW}Найдено {len(open_orders)} открытых ордеров для {symbol}, отменяем...")
                            for order in open_orders:
                                try:
                                    await self.cancel_order(order.order_id, symbol)
                                    logger.debug(f"✓ Ордер #{order.order_id} отменён")
                                except Exception as e:
                                    logger.warning(f"Не удалось отменить ордер #{order.order_id}: {e}")
                        else:
                            logger.debug(f"Нет открытых ордеров для {symbol}")
                    
                    return True
                else:
                    return False
        
        if not position_found:
            # Позиции нет, но проверим, нет ли открытых ордеров для этого символа
            open_orders = await self.get_open_orders(symbol)
            if open_orders:
                logger.info(f"{Fore.YELLOW}Позиции {symbol} нет, но найдено {len(open_orders)} открытых ордеров, отменяем...")
                for order in open_orders:
                    try:
                        await self.cancel_order(order.order_id, symbol)
                        logger.debug(f"✓ Ордер #{order.order_id} отменён")
                    except Exception as e:
                        logger.warning(f"Не удалось отменить ордер #{order.order_id}: {e}")
        
        return False
    
    async def set_position_tpsl(
        self,
        symbol: str,
        side: Side,
        entry_price: float,
        take_profit_percent: float,
        stop_loss_percent: float
    ) -> bool:
        """Установка Take Profit и Stop Loss для позиции через API"""
        try:
            # Сначала проверяем, что позиция действительно открыта
            positions = await self.get_positions(fast_mode=True)
            position_exists = False
            for pos in positions:
                if pos.symbol == symbol and abs(float(pos.amount)) > 0.000001:
                    position_exists = True
                    # Проверяем, что сторона позиции совпадает
                    if pos.side != side:
                        logger.warning(
                            f"Сторона позиции не совпадает: ожидали {side.value}, "
                            f"получили {pos.side.value}"
                        )
                    break
            
            if not position_exists:
                logger.warning(f"Позиция {symbol} не найдена, не можем установить TP/SL")
                return False
            
            tick_size = await self.get_tick_size(symbol)
            if not tick_size:
                logger.warning(f"Не удалось получить tick_size для {symbol}, используем округление до 2 знаков")
                tick_size = 0.01
            
            if side == Side.BID:
                tp_price = entry_price * (1 + take_profit_percent)
                sl_price = entry_price * (1 - stop_loss_percent)
            else:
                tp_price = entry_price * (1 - take_profit_percent)
                sl_price = entry_price * (1 + stop_loss_percent)
            
            tp_price_str = self.round_to_tick(tp_price, tick_size)
            sl_price_str = self.round_to_tick(sl_price, tick_size)
            
            tp_price_rounded = float(tp_price_str)
            sl_price_rounded = float(sl_price_str)
            
            logger.debug(
                f"Расчёт TP/SL для {symbol} ({side.value}): "
                f"Entry={entry_price:.4f}, TP={tp_price_rounded:.4f}, SL={sl_price_rounded:.4f}"
            )
            
            tp_order = StopOrderInfo(
                stop_price=tp_price_str,
                limit_price=tp_price_str
            )
            
            sl_order = StopOrderInfo(
                stop_price=sl_price_str,
                limit_price=sl_price_str
            )
            
            stop_order_side = Side.ASK if side == Side.BID else Side.BID
            
            tpsl_request = CreateTPSLOrder(
                symbol=symbol,
                side=stop_order_side,  # Сторона для стоп-ордеров (противоположная позиции)
                take_profit=tp_order,
                stop_loss=sl_order
            )
            
            logger.debug(
                f"Отправка запроса TP/SL: symbol={symbol}, "
                f"позиция={side.value}, стоп-ордера={stop_order_side.value}"
            )
            
            from pacifica_sdk.utils.tools import build_signer_request
            from pacifica_sdk.enums import OperationType
            
            request_params = tpsl_request.model_dump(exclude_none=True)
            
            signed_request = build_signer_request(
                keypair=self.exchange.keypair,
                operation_type=OperationType.SET_POSITION_TPSL,
                params=request_params,
                expiry_window=self.exchange.expiry_window,
                public_key=self.exchange.public_key,
                agent_wallet=self.exchange.agent_wallet,
            )
            
            url = f"{self.exchange.base_url}/positions/tpsl"
            async with self.exchange.session.post(
                url,
                headers={"Content-Type": "application/json"},
                json=signed_request
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and data.get("success"):
                        result = type('Result', (), {'success': True})()
                    else:
                        result = type('Result', (), {
                            'success': False,
                            'error': data.get('error', 'Unknown error'),
                            'code': data.get('code')
                        })()
                else:
                    text = await response.text()
                    try:
                        error_data = await response.json()
                        result = type('Result', (), {
                            'success': False,
                            'error': error_data.get('error', text),
                            'code': error_data.get('code', response.status)
                        })()
                    except:
                        result = type('Result', (), {
                            'success': False,
                            'error': text,
                            'code': response.status
                        })()
            
            if result:
                if hasattr(result, 'success') and result.success:
                    logger.info(
                        f"{Fore.GREEN}✓ TP/SL установлены для {symbol} ({side.value}): "
                        f"TP @ {tp_price_rounded:.4f} (+{take_profit_percent*100:.3f}%), "
                        f"SL @ {sl_price_rounded:.4f} (-{stop_loss_percent*100:.3f}%)"
                    )
                    return True
                else:
                    error_msg = "Unknown error"
                    error_code = None
                    if hasattr(result, 'error'):
                        error_msg = result.error
                    if hasattr(result, 'code'):
                        error_code = result.code
                    if hasattr(result, 'data'):
                        logger.debug(f"Response data: {result.data}")
                    
                    logger.warning(
                        f"{Fore.YELLOW}⚠ Не удалось установить TP/SL для {symbol}: "
                        f"{error_msg}" + (f" (code: {error_code})" if error_code else "")
                    )
                    return False
            else:
                logger.warning(f"Пустой ответ от API при установке TP/SL для {symbol}")
                return False
                
        except ApiError as e:
            logger.error(
                f"{Fore.RED}API ошибка при установке TP/SL для {symbol}: "
                f"[{e.status_code}] code={e.code} message='{e.error_message}' data={e.data}"
            )
            if e.raw_body:
                logger.debug(f"Raw response: {e.raw_body}")
            return False
        except ServerError as e:
            logger.error(f"{Fore.RED}Server ошибка при установке TP/SL для {symbol}: {e}")
            return False
        except Exception as e:
            logger.error(f"{Fore.RED}Ошибка установки TP/SL для {symbol}: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return False
        
    async def select_best_market(self) -> Optional[str]:
        """Выбор лучшего рынка на основе funding rate"""
        best_market = None
        best_score = -float('inf')
        
        for symbol in self.config.markets:
            try:
                funding = await self.get_funding_rate(symbol)
                if funding is not None:
                    score = abs(funding) * 10000  # Чем больше funding, тем лучше
                    if score > best_score:
                        best_score = score
                        best_market = symbol
            except Exception as e:
                logger.debug(f"Ошибка анализа {symbol}: {e}")
                
        return best_market or self.config.markets[0]
        
    async def determine_side(self, symbol: str) -> Optional[Side]:
        """Определение направления на основе funding rate"""
        funding = await self.get_funding_rate(symbol)
        
        if funding is None:
            logger.warning(f"Не удалось получить funding rate для {symbol}")
            return None
            
        # Funding rate может быть в разных форматах:
        # - Как десятичная дробь: -0.0003 = -0.03%
        # - Как процент: -0.000003 = -0.0003%
        # Проверяем значение
        
        # Логируем в процентах для удобства
        funding_percent = funding * 100
        logger.info(f"Funding rate для {symbol}: {funding:.8f} ({funding_percent:.6f}%)")
        
        if funding > 0:
            logger.info(f"Funding rate положительный, открываем SHORT (получаем funding)")
            return Side.ASK  # SHORT - получаем funding
        else:
            logger.info(f"Funding rate отрицательный, открываем LONG (получаем funding)")
            return Side.BID  # LONG - получаем funding
            
    async def trading_cycle(self) -> bool:
        """
        Один цикл торговли
        
        Returns:
            True если целевой объем достигнут, False иначе
        """
        # Очистка перед новой сделкой: закрываем все позиции и отменяем все ордера
        await self.cleanup_before_trade()
        
        # Проверяем объем перед началом цикла
        if self.total_volume >= self.config.target_volume:
            return True
        
        # Выбор рынка
        market = await self.select_best_market()
        if not market:
            logger.warning("Нет доступных рынков")
            return False
            
        logger.info(f"{Fore.CYAN}Выбран рынок: {market}")
        
        # Определение направления
        side = await self.determine_side(market)
        if side is None:
            logger.error(f"Не удалось определить направление для {market}")
            return False
        
        # Используем кешированный баланс или получаем новый
        balance = getattr(self, 'cached_balance', None)
        if not balance:
            balance = await self.get_balance()
            if balance:
                self.cached_balance = balance
                
        if not balance or balance <= 0:
            logger.warning("Недостаточно средств или баланс не получен")
            return False
            
        # Расчет размера позиции
        current_price = await self.get_current_price(market)
        if not current_price:
            logger.error(f"Не удалось получить цену для {market}")
            return False
            
        # Получаем процент от баланса для позиции (БЕЗ учета плеча)
        position_percent = self.config.get_random_position_size()
        
        # Рассчитываем размер позиции в USD (БЕЗ плеча)
        # position_percent - это процент от баланса, который мы используем
        position_size_base = balance * position_percent
        
        # Комиссии (maker ~0.02%, taker ~0.05%)
        fee_rate = 0.0002 if self.config.use_maker_orders else 0.0005
        safety_buffer = 0.05  # 5% запас для безопасности
        
        # Учитываем комиссии и запас безопасности
        # Комиссия берётся дважды (открытие + закрытие)
        # Вычитаем комиссии из доступного баланса
        available_balance = balance * (1 - safety_buffer)
        max_position_base = available_balance / (1 + fee_rate * 2)
        
        # Ограничиваем размер позиции (БЕЗ плеча)
        position_size_base = min(position_size_base, max_position_base)
        
        # Применяем плечо для расчета реального размера позиции на бирже
        # position_size_base - это сколько USD мы используем из баланса
        # position_size_usd - это размер позиции на бирже (с плечом)
        position_size_usd = position_size_base * self.current_leverage
        
        # Проверяем, что у нас достаточно баланса
        required_balance = position_size_base + position_size_base * fee_rate * 2
        if required_balance > balance:
            # Уменьшаем процент позиции, если не хватает баланса
            max_percent = (balance * 0.95) / (balance * (1 + fee_rate * 2))
            position_percent = min(position_percent, max_percent)
            position_size_base = balance * position_percent
            position_size_usd = position_size_base * self.current_leverage
            logger.warning(
                f"{Fore.YELLOW}Размер позиции уменьшен до {position_percent*100:.1f}% "
                f"(${position_size_base:.2f} без плеча, ${position_size_usd:.2f} с плечом {self.current_leverage}x)"
            )
        
        logger.info(
            f"{Fore.GREEN}Размер позиции: {position_percent*100:.1f}% от баланса "
            f"(${position_size_base:.2f} без плеча → ${position_size_usd:.2f} с плечом {self.current_leverage}x)"
        )
        
        if self.config.use_maker_orders:
            if side == Side.BID:
                limit_price = current_price * (1 - self.current_slippage)
            else:
                limit_price = current_price * (1 + self.current_slippage)
                
            logger.info(f"Лимитная цена: {limit_price:.4f} (текущая: {current_price:.4f}, отступ: {self.current_slippage*100:.3f}%)")
        else:
            limit_price = None
            
        entry_result = await self.place_order(
            symbol=market,
            side=side,
            size_usd=position_size_usd,
            price=limit_price,
            reduce_only=False
        )
        
        if not entry_result:
            logger.error("Не удалось открыть позицию")
            return False
        
        logger.info(f"{Fore.YELLOW}Ожидание исполнения ордера...")
        entry_price = await self._wait_for_order_fill(
            market=market,
            order_result=entry_result,
            limit_price=limit_price,
            side=side,
            size_usd=position_size_usd,
            current_price=current_price
        )
        
        if not entry_price:
            logger.error("❌ Ордер не был исполнен - позиция НЕ открыта")
            logger.error("Бот пропустит эту сделку и перейдёт к следующей")
            return False
            
        logger.info(f"{Fore.GREEN}✓ Позиция открыта @ {entry_price:.4f}")
        
        # Небольшая задержка, чтобы позиция точно появилась в системе
        await asyncio.sleep(2)
        
        # Устанавливаем TP/SL через API
        logger.info(f"{Fore.CYAN}Установка Take Profit и Stop Loss через API...")
        tp_sl_set = await self.set_position_tpsl(
            symbol=market,
            side=side,  # Сторона позиции (bid для LONG, ask для SHORT)
            entry_price=entry_price,
            take_profit_percent=self.current_take_profit,
            stop_loss_percent=self.current_stop_loss
        )
        
        if not tp_sl_set:
            logger.warning(f"{Fore.YELLOW}⚠ Не удалось установить TP/SL через API, бот будет мониторить вручную")
        
        # Удержание позиции (рандомизированное время)
        hold_time = self.config.get_random_hold_time() * 60
        logger.info(f"{Fore.CYAN}Удержание позиции {hold_time // 60} минут ({hold_time} секунд)...")
        await self._hold_position(market, entry_price, side, hold_time)
        
        # Закрытие позиции
        logger.info(f"{Fore.YELLOW}Закрытие позиции {market}...")
        close_result = await self.close_position(market)
        if close_result:
            # Ждём закрытия и получаем цену закрытия
            await asyncio.sleep(2)  # Небольшая задержка для обновления позиций
            exit_price = await self.get_current_price(market)
            if exit_price:
                pnl = self._calculate_pnl(entry_price, exit_price, position_size_usd, side)
                self.total_pnl += pnl
                self.total_volume += position_size_usd * 2
                self.trades_count += 1
                pnl_color = Fore.GREEN if pnl >= 0 else Fore.RED
                logger.info(f"{pnl_color}✓ Сделка #{self.trades_count} закрыта | Exit: {exit_price:.4f} | PnL: ${pnl:.4f}")
                logger.info(f"  Объём сделки: ${position_size_usd * 2:.2f} | Общий объём: ${self.total_volume:.2f} | Общий PnL: ${self.total_pnl:.2f}")
                
                if self.total_volume >= self.config.target_volume:
                    return True
            else:
                logger.warning("Не удалось получить цену закрытия")
        else:
            logger.error("Не удалось закрыть позицию")
        
        return False
                
    async def _wait_for_order_fill(
        self,
        market: str,
        order_result: Dict,
        limit_price: Optional[float],
        side: Side,
        size_usd: float,
        current_price: float,
        max_wait: int = 300,
        reposition_timeout: int = 90
    ) -> Optional[float]:
        """
        Ожидание исполнения ордера и получение реальной цены
        
        Строго по документации Pacifica:
        https://docs.pacifica.fi/api-documentation/api/rest-api/orders
        
        Проверяет:
        1. Get open orders - открытые ордера
        2. Get account positions - открытые позиции
        3. Get order history by ID - история ордера
        """
        # Получаем order_id из ответа
        order_id = order_result.get('order_id') or order_result.get('id') or order_result.get('orderId')
        
        if not order_id:
            logger.warning("Не удалось получить order_id из ответа")
            return None
        
        logger.info(f"{Fore.CYAN}=== Ожидание исполнения ордера #{order_id} ===")
        logger.info(f"Рынок: {market}, Сторона: {side.value}, Лимитная цена: {limit_price}")
        
        # Для рыночных ордеров - они исполняются сразу
        if not limit_price:
            logger.info("Market ордер - проверяем исполнение...")
            await asyncio.sleep(2)  # Небольшая задержка для обработки
            for price_field in ['avg_price', 'avgPrice', 'price', 'executed_price', 'fill_price']:
                if price_field in order_result and order_result[price_field]:
                    try:
                        price = float(order_result[price_field])
                        if price > 0:
                            logger.info(f"{Fore.GREEN}✓ Market ордер исполнен @ {price:.4f}")
                            return price
                    except (ValueError, TypeError):
                        continue
            
            # Проверяем позиции для market ордера
            positions = await self.get_positions()
            for pos in positions:
                if pos.symbol == market:
                    amount = float(pos.amount)
                    if abs(amount) > 0.000001:
                        entry_price = float(pos.entry_price)
                        logger.info(f"{Fore.GREEN}✓ Market ордер исполнен! Позиция: {abs(amount):.6f} {market} @ {entry_price:.4f}")
                        return entry_price
            return None
        
        # Для лимитных ордеров - проверяем регулярно
        check_interval = 5  # Проверяем каждые 5 секунд
        elapsed = 0
        last_log_time = 0
        repositioned = False
        total_elapsed = 0
        
        logger.info(f"Максимум ожидания: {max_wait}с, перестановка через: {reposition_timeout}с")
        logger.info(f"Интервал проверки: {check_interval}с")
        
        while total_elapsed < max_wait:
            try:
                if total_elapsed > 0:
                    jitter_delay = random.uniform(0.5, 1.5)
                    await asyncio.sleep(jitter_delay)
                
                logger.info(f"{Fore.CYAN}[{total_elapsed}с] Проверка позиций для {market}...")
                positions = await self.get_positions(retries=2, fast_mode=True)
                
                logger.info(f"Получено позиций: {len(positions)}")
                
                for pos in positions:
                    logger.info(f"  Позиция: symbol={pos.symbol}, amount={pos.amount}")
                    
                    if pos.symbol == market:
                        amount = float(pos.amount)
                        logger.info(f"{Fore.GREEN}  ✓ Найдена позиция по {market}: amount={amount}")
                        
                        if abs(amount) > 0.000001:
                            entry_price = float(pos.entry_price)
                            side_str = "SHORT" if amount < 0 else "LONG"
                            logger.info(f"{Fore.GREEN}✓✓✓ ОРДЕР #{order_id} ИСПОЛНЕН! ✓✓✓")
                            return entry_price
                        else:
                            logger.warning(f"  ⚠ Позиция найдена, но amount слишком мал: {amount}")
                
                try:
                    params = GetOpenOrders(account=self.public_key)
                    open_orders = await self.exchange.info.get_open_orders(params)
                    
                    logger.info(f"Открытых ордеров: {len(open_orders)}")
                    
                    order_found = False
                    for order in open_orders:
                        if order.order_id == order_id:
                            order_found = True
                            logger.info(f"{Fore.YELLOW}  Ордер #{order_id} найден в открытых ордерах")
                            
                            filled = float(order.filled_amount) if hasattr(order, 'filled_amount') else 0
                            initial = float(order.initial_amount) if hasattr(order, 'initial_amount') else 0
                            cancelled = float(order.cancelled_amount) if hasattr(order, 'cancelled_amount') else 0
                            
                            logger.info(f"  Заполнение: filled={filled:.6f}, initial={initial:.6f}, cancelled={cancelled:.6f}")
                            
                            if initial > 0:
                                remaining = initial - filled - cancelled
                                filled_percent = (filled / initial * 100) if initial > 0 else 0
                                
                                logger.info(f"  Осталось: {remaining:.6f} ({100 - filled_percent:.1f}%)")
                                
                                if remaining <= initial * 0.01 or filled_percent >= 99:
                                    price = float(order.price)
                                    logger.info(f"{Fore.GREEN}✓ Ордер #{order_id} почти исполнен! @ {price:.4f}")
                                    await asyncio.sleep(2)
                                    positions = await self.get_positions()
                                    for pos in positions:
                                        if pos.symbol == market:
                                            amount = float(pos.amount)
                                            if abs(amount) > 0.000001:
                                                entry_price = float(pos.entry_price)
                                                logger.info(f"{Fore.GREEN}✓ Позиция подтверждена: {abs(amount):.6f} {market} @ {entry_price:.4f}")
                                                return entry_price
                                    return price
                                elif filled > 0:
                                    logger.info(f"  Ордер частично заполнен: {filled_percent:.1f}%")
                            break
                    
                    if not order_found:
                        logger.info(f"{Fore.YELLOW}  Ордер #{order_id} не найден в открытых ордерах")
                        
                        try:
                            params_history = GetOrderHistoryById(order_id=order_id)
                            history_items = await self.exchange.info.get_order_history_by_id(params_history)
                            
                            if history_items and len(history_items) > 0:
                                history_order = history_items[0]
                                logger.info(f"{Fore.GREEN}  Ордер найден в истории")
                                
                                if hasattr(history_order, 'filled_amount') and hasattr(history_order, 'initial_amount'):
                                    filled = float(history_order.filled_amount)
                                    initial = float(history_order.initial_amount)
                                    
                                    if initial > 0 and filled >= initial * 0.99:
                                        price = float(history_order.price) if hasattr(history_order, 'price') and history_order.price else limit_price
                                        if not price and limit_price:
                                            price = limit_price
                                        logger.info(f"{Fore.GREEN}✓ Ордер #{order_id} исполнен (из истории) @ {price:.4f}")
                                        return price
                        except Exception as e:
                            logger.debug(f"Ошибка проверки order history: {e}")
                            
                except Exception as e:
                    error_str = str(e)
                    if "CloudFront" in error_str or "403" in error_str or "Failed to decode JSON" in error_str:
                        logger.debug(f"CloudFront блокирует открытые ордера (это нормально при rate limiting), продолжаем проверку позиций...")
                    else:
                        logger.warning(f"Ошибка проверки открытых ордеров: {e}")
                
                # Логируем прогресс каждые 15 секунд
                if total_elapsed - last_log_time >= 15:
                    remaining = max(0, max_wait - total_elapsed)
                    minutes = remaining // 60
                    seconds = remaining % 60
                    if minutes > 0:
                        remaining_str = f"{minutes}м {seconds}с"
                    else:
                        remaining_str = f"{seconds}с"
                    logger.info(f"{Fore.YELLOW}⏳ Ожидание... (прошло: {total_elapsed}с, осталось: {remaining_str}, лимитная цена: {limit_price:.4f})")
                    last_log_time = total_elapsed
                
                if elapsed >= reposition_timeout and not repositioned and total_elapsed < max_wait - 60:
                    logger.info(f"{Fore.YELLOW}Ордер #{order_id} не исполнен за {reposition_timeout}с ({elapsed}с) - переставляем ближе к текущей цене...")
                    
                    await self.cancel_order(order_id, market)
                    await asyncio.sleep(1)
                    
                    new_current_price = await self.get_current_price(market)
                    if not new_current_price:
                        new_current_price = current_price
                    
                    aggressive_slippage = 0.0001
                    if side == Side.BID:
                        new_limit_price = new_current_price * (1 - aggressive_slippage)
                    else:
                        new_limit_price = new_current_price * (1 + aggressive_slippage)
                    
                    tick_size = await self.get_tick_size(market)
                    if tick_size:
                        new_limit_price_str = self.round_to_tick(new_limit_price, tick_size)
                        new_limit_price = float(new_limit_price_str)
                    
                    logger.info(f"{Fore.CYAN}Новая лимитная цена: {new_limit_price:.4f} (текущая: {new_current_price:.4f}, отступ: {aggressive_slippage*100:.2f}%)")
                    
                    new_order_result = await self.place_order(
                        symbol=market,
                        side=side,
                        size_usd=size_usd,
                        price=new_limit_price,
                        reduce_only=False
                    )
                    
                    if new_order_result:
                        new_order_id = new_order_result.get('order_id') or new_order_result.get('id') or new_order_result.get('orderId')
                        logger.info(f"{Fore.GREEN}✓ Новый ордер #{new_order_id} размещён ближе к текущей цене")
                        order_id = new_order_id
                        limit_price = new_limit_price
                        repositioned = True
                        elapsed = 0
                        last_log_time = total_elapsed
                    else:
                        logger.error("Не удалось разместить новый ордер")
                        return None
                
                if total_elapsed - last_log_time >= 15:
                    remaining = max(0, max_wait - total_elapsed)  # Не показываем отрицательные значения
                    minutes = remaining // 60
                    seconds = remaining % 60
                    if minutes > 0:
                        remaining_str = f"{minutes}м {seconds}с"
                    else:
                        remaining_str = f"{seconds}с"
                    logger.info(f"{Fore.YELLOW}Ожидание исполнения ордера #{order_id}... (лимитная цена: {limit_price:.4f}, прошло: {total_elapsed}с, осталось: {remaining_str})")
                    last_log_time = total_elapsed
                    
            except Exception as e:
                error_str = str(e)
                if "CloudFront" in error_str or "403" in error_str or "Failed to decode JSON" in error_str:
                    if total_elapsed - last_log_time >= 15:
                        logger.info(f"{Fore.YELLOW}CloudFront блокирует запросы (попытка {total_elapsed // check_interval + 1}), продолжаем проверку...")
                        remaining = max(0, max_wait - total_elapsed)
                        minutes = remaining // 60
                        seconds = remaining % 60
                        if minutes > 0:
                            remaining_str = f"{minutes}м {seconds}с"
                        else:
                            remaining_str = f"{seconds}с"
                        logger.info(f"Ожидание исполнения ордера #{order_id}... (прошло: {total_elapsed}с, осталось: {remaining_str})")
                        last_log_time = total_elapsed
                else:
                    if total_elapsed - last_log_time >= 15:
                        logger.warning(f"Ошибка проверки позиций: {e}")
                        last_log_time = total_elapsed
            
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            total_elapsed += check_interval
        
        # Если не исполнился за отведённое время - отменяем ордер
        logger.warning(f"⚠ Ордер #{order_id} не исполнился за {total_elapsed} секунд ({total_elapsed // 60} минут)")
        logger.info(f"{Fore.YELLOW}Отменяем неисполненный ордер #{order_id}...")
        
        try:
            await self.cancel_order(order_id, market)
            logger.info(f"{Fore.GREEN}✓ Ордер #{order_id} отменён")
        except Exception as e:
            logger.error(f"Ошибка отмены ордера #{order_id}: {e}")
        
        logger.warning("Позиция НЕ открыта - ордер отменён из-за таймаута")
        return None
    
    async def _hold_position(self, market: str, entry_price: float, side: Side, hold_time: int):
        """Удержание позиции с мониторингом"""
        check_interval = 10
        elapsed = 0
        last_log_time = 0
        
        logger.info(f"{Fore.CYAN}Мониторинг позиции: Entry @ {entry_price:.4f}, Side: {side.value}")
        logger.info(f"Take Profit: {self.current_take_profit*100:.3f}%, Stop Loss: {self.current_stop_loss*100:.3f}%")
        logger.info(f"{Fore.YELLOW}Примечание: Если TP/SL установлены на бирже, они сработают автоматически")
        
        while elapsed < hold_time:
            positions = await self.get_positions(fast_mode=True)
            position_exists = False
            for pos in positions:
                if pos.symbol == market and abs(float(pos.amount)) > 0.000001:
                    position_exists = True
                    break
            
            if not position_exists:
                logger.info(f"{Fore.GREEN}✓ Позиция закрыта автоматически (вероятно, через TP/SL на бирже)")
                return
            
            current_price = await self.get_current_price(market)
            if current_price:
                if side == Side.BID:
                    price_change = (current_price - entry_price) / entry_price
                    pnl_percent = price_change
                else:
                    price_change = (entry_price - current_price) / entry_price
                    pnl_percent = price_change
                
                if elapsed - last_log_time >= 30:
                    remaining = hold_time - elapsed
                    pnl_color = Fore.GREEN if pnl_percent >= 0 else Fore.RED
                    logger.info(
                        f"{pnl_color}Позиция активна | "
                        f"Цена: {current_price:.4f} | "
                        f"PnL: {pnl_percent*100:+.3f}% | "
                        f"Осталось: {remaining // 60}м {remaining % 60}с"
                    )
                    last_log_time = elapsed
                    
                if price_change >= self.current_take_profit:
                    logger.info(f"{Fore.GREEN}✓ Take profit достигнут программно! +{price_change*100:.3f}% (цель: {self.current_take_profit*100:.3f}%)")
                    logger.info(f"{Fore.YELLOW}Закрываем позицию вручную...")
                    break
                    
                if price_change <= -self.current_stop_loss:
                    logger.warning(f"{Fore.RED}✗ Stop loss достигнут программно! {price_change*100:.3f}% (лимит: {self.current_stop_loss*100:.3f}%)")
                    logger.info(f"{Fore.YELLOW}Закрываем позицию вручную...")
                    break
            else:
                logger.warning("Не удалось получить текущую цену для мониторинга")
                    
            await asyncio.sleep(check_interval)
            elapsed += check_interval
        
        if elapsed >= hold_time:
            logger.info(f"{Fore.CYAN}Время удержания истекло ({hold_time // 60} минут)")
            
    def _calculate_pnl(self, entry: float, exit: float, size: float, side: Side) -> float:
        """Расчет PnL"""
        if side == Side.BID:
            price_diff = exit - entry
        else:
            price_diff = entry - exit
            
        pnl = (price_diff / entry) * size if entry > 0 else 0
        
        # Комиссии
        fee_rate = 0.0002 if self.config.use_maker_orders else 0.0005
        fees = size * fee_rate * 2
        
        return pnl - fees
        
    async def run(self):
        """Запуск бота"""
        goatham_art = [
            " _____ _____ _____ _____ _____ _____ _____    ____  _____ _____ ",
            "|   __|     |  _  |_   _|  |  |  _  |     |  |    \\|  _  |     |",
            "|  |  |  |  |     | | | |     |     | | | |  |  |  |     |  |  |",
            "|_____|_____|__|__| |_| |__|__|__|__|_|_|_|  |____/|__|__|_____|"
        ]
        
        # Вычисляем максимальную ширину ASCII-арта и нормализуем все строки до этой ширины
        max_width = max(len(line.rstrip()) for line in goatham_art)
        inner_width = max_width + 2  # Отступы по 1 символу с каждой стороны
        box_width = inner_width + 2  # +2 для границ ║
        
        # Функция для создания строки с правильным выравниванием
        def make_box_line(content, color=Fore.WHITE):
            content = content.rstrip()  # Убираем лишние пробелы справа
            padding_left = (inner_width - len(content)) // 2
            padding_right = inner_width - len(content) - padding_left
            return f"{Fore.CYAN}║{' ' * padding_left}{color}{content}{' ' * padding_right}{Fore.CYAN}║"
        
        logger.info(f"{Fore.CYAN}╔{'═' * inner_width}╗")
        logger.info(make_box_line(""))
        
        # Выводим ASCII-арт GOATHAM DAO
        for line in goatham_art:
            logger.info(make_box_line(line.rstrip(), Fore.WHITE))
        
        logger.info(make_box_line(""))
        logger.info(make_box_line("Pacifica Volume Bot V1.0", Fore.YELLOW))
        logger.info(make_box_line(""))
        logger.info(make_box_line("by Davy и Suzu", Fore.WHITE))
        logger.info(make_box_line(""))
        logger.info(make_box_line("https://t.me/suzuich", Fore.WHITE))
        logger.info(make_box_line(""))
        logger.info(f"{Fore.CYAN}╚{'═' * inner_width}╝{Style.RESET_ALL}")
        
        # Логируем рандомизированные параметры для этого аккаунта
        logger.info(f"{Fore.CYAN}Рандомизированные параметры для аккаунта:")
        logger.info(f"  Плечо: {self.current_leverage}x")
        logger.info(f"  Slippage: {self.current_slippage*100:.3f}%")
        logger.info(f"  Take Profit: {self.current_take_profit*100:.3f}%")
        logger.info(f"  Stop Loss: {self.current_stop_loss*100:.3f}%")
        logger.info(f"  Размер позиции: {self.config.min_position_size*100:.0f}% - {self.config.max_position_size*100:.0f}% от баланса (без учета плеча)")
        
        # Настройка плеча (используем рандомизированное значение)
        # Проверяем максимальные плечи для всех рынков и корректируем текущее плечо
        min_max_leverage = None
        for market in self.config.markets:
            max_leverage = await self.get_max_leverage(market)
            if max_leverage:
                if min_max_leverage is None or max_leverage < min_max_leverage:
                    min_max_leverage = max_leverage
        
        # Если текущее плечо превышает минимальное максимальное - ограничиваем
        if min_max_leverage and self.current_leverage > min_max_leverage:
            logger.warning(f"Плечо {self.current_leverage}x превышает максимальное для некоторых рынков ({min_max_leverage}x). Используем {min_max_leverage}x")
            self.current_leverage = min_max_leverage
        
        # Устанавливаем плечо для всех рынков
        for market in self.config.markets:
            await self.set_leverage(market, self.current_leverage)
            await asyncio.sleep(1)  # Задержка между запросами
            
        # Получение баланса (с повторными попытками)
        # CloudFront может блокировать запросы из-за rate limiting
        # Добавляем задержки и увеличиваем время между попытками
        balance = None
        max_attempts = 5
        for attempt in range(max_attempts):
            # Задержка перед запросом (избегаем rate limiting)
            if attempt > 0:
                wait_time = min((attempt + 1) * 5, 30)  # Максимум 30 секунд
                logger.warning(f"Попытка {attempt + 1}/{max_attempts} получения баланса, ждём {wait_time} сек...")
                await asyncio.sleep(wait_time)
                
            balance = await self.get_balance()
            if balance is not None and balance > 0:
                logger.info(f"✓ Баланс получен: ${balance:.2f}")
                self.cached_balance = balance
                break
            
        if balance is None or balance <= 0:
            logger.error("❌ Не удалось получить баланс через API после всех попыток!")
            logger.error("Проверьте:")
            logger.error("  1. Правильность API ключей в accounts.csv")
            logger.error("  2. Бета доступ активирован на https://app.pacifica.fi")
            logger.error("  3. Наличие средств на балансе")
            return  # Останавливаем бота если нет баланса
            
        # Основной цикл
        volume_reached = False
        while self.total_volume < self.config.target_volume:
            try:
                # Проверяем возвращаемое значение trading_cycle
                volume_reached = await self.trading_cycle()
                
                # Если объем достигнут, выходим из цикла
                if volume_reached or self.total_volume >= self.config.target_volume:
                    break
                
                # Статистика
                progress = (self.total_volume / self.config.target_volume) * 100
                logger.info(f"Объем: ${self.total_volume:.2f} / ${self.config.target_volume:.2f} ({progress:.1f}%)")
                logger.info(f"PnL: ${self.total_pnl:.4f} | Сделок: {self.trades_count}")
                
                # Задержка (рандомизированная)
                delay = self.config.get_random_delay()
                logger.info(f"Ожидание {delay} секунд...")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле: {e}")
                await asyncio.sleep(10)
        
        # Целевой объем достигнут - закрываем все позиции и отменяем ордера
        logger.info("Целевой объем достигнут. Закрытие всех позиций и отмена ордеров...")
        
        # Сначала отменяем все ордера
        await self.cancel_all_orders(exclude_reduce_only=False)
        await asyncio.sleep(1)
        
        # Затем закрываем все позиции
        await self.close_all_positions()
        await asyncio.sleep(2)
        
        # Финальная проверка - убеждаемся, что все закрыто
        positions = await self.get_positions()
        if positions:
            for pos in positions:
                if abs(float(pos.amount)) > 0.000001:
                    logger.warning(f"Найдена открытая позиция {pos.symbol}, закрываем...")
                    await self.close_position(pos.symbol)
                    await asyncio.sleep(1)
        
        # Отменяем все оставшиеся ордера еще раз
        await self.cancel_all_orders(exclude_reduce_only=False)
            
        logger.info(f"{Fore.GREEN}Бот завершил работу")
        logger.info(f"Итоговый объем: ${self.total_volume:.2f}")
        logger.info(f"Итоговый PnL: ${self.total_pnl:.4f}")


async def main():
    """Главная функция"""
    
    # Настройка логирования
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "logs/pacifica_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days"
    )
    
    # Загрузка конфигурации
    config_path = Path("config.json")
    if config_path.exists():
        with open(config_path, 'r') as f:
            config_data = json.load(f)
            # Фильтруем только нужные поля (поддерживаем новый формат с диапазонами)
            valid_fields = {
                # Новый формат с диапазонами
                'hold_time_min', 'hold_time_max', 'target_volume',
                'leverage', 'markets',
                'min_position_size', 'max_position_size',
                'delay_between_trades_min', 'delay_between_trades_max',
                'use_maker_orders',
                'take_profit_percent_min', 'take_profit_percent_max',
                'stop_loss_percent_min', 'stop_loss_percent_max',
                'slippage_min', 'slippage_max',
                # Старый формат (для обратной совместимости)
                'hold_time', 'leverage', 'delay_between_trades',
                'take_profit_percent', 'stop_loss_percent', 'slippage'
            }
            filtered_data = {k: v for k, v in config_data.items() if k in valid_fields}
            
            # Конвертируем старый формат в новый (если нужно)
            if 'hold_time' in filtered_data and 'hold_time_min' not in filtered_data:
                hold_time = filtered_data.pop('hold_time')
                filtered_data['hold_time_min'] = max(1, hold_time - 2)
                filtered_data['hold_time_max'] = hold_time + 2
            if 'delay_between_trades' in filtered_data and 'delay_between_trades_min' not in filtered_data:
                delay = filtered_data.pop('delay_between_trades')
                filtered_data['delay_between_trades_min'] = max(10, delay - 15)
                filtered_data['delay_between_trades_max'] = delay + 15
            if 'take_profit_percent' in filtered_data and 'take_profit_percent_min' not in filtered_data:
                tp = filtered_data.pop('take_profit_percent')
                filtered_data['take_profit_percent_min'] = tp * 0.6
                filtered_data['take_profit_percent_max'] = tp * 1.5
            if 'stop_loss_percent' in filtered_data and 'stop_loss_percent_min' not in filtered_data:
                sl = filtered_data.pop('stop_loss_percent')
                filtered_data['stop_loss_percent_min'] = sl * 0.7
                filtered_data['stop_loss_percent_max'] = sl * 1.3
            if 'slippage' in filtered_data and 'slippage_min' not in filtered_data:
                slippage = filtered_data.pop('slippage')
                filtered_data['slippage_min'] = slippage * 0.6
                filtered_data['slippage_max'] = slippage * 1.4
                
            config = Config(**filtered_data)
    else:
        config = Config()
        
    # Загрузка аккаунта
    accounts_path = Path("accounts.csv")
    if not accounts_path.exists():
        logger.error("Файл accounts.csv не найден!")
        return
        
    import csv
    with open(accounts_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        account = next(reader, None)
        
    if not account:
        logger.error("Нет аккаунтов в accounts.csv")
        return
    
    # Определяем, используется ли API Agent или основной кошелек
    # Если api_key == walletaddress, значит это основной кошелек, а не API Agent
    api_key = account.get('api_key', '').strip()
    walletaddress = account.get('walletaddress', '').strip() if account.get('walletaddress') else None
    subaccount = account.get('subaccount', '').strip() if account.get('subaccount') else None
    main_account = walletaddress or subaccount
    
    # Если api_key совпадает с main_account, значит это основной кошелек, не API Agent
    use_api_agent = main_account and api_key != main_account
    
    # Запуск бота
    if use_api_agent:
        # API Agent Keys:
        # private_key = приватный ключ API Agent (api_secret)
        # public_key = публичный ключ основного аккаунта (walletaddress/subaccount)
        # agent_wallet = публичный ключ API Agent (api_key)
        logger.info(f"Используем API Agent Keys: Agent={api_key}, Main={main_account}")
        async with PacificaBot(
            private_key=account['api_secret'],  # Приватный ключ API Agent
            public_key=main_account,            # Основной аккаунт
            agent_wallet=api_key,                # Публичный ключ API Agent
            config=config
        ) as bot:
            await bot.run()
    else:
        # Основной кошелёк:
        # private_key = приватный ключ основного кошелька
        # public_key = публичный ключ основного кошелька
        logger.info(f"Используем основной кошелёк {api_key}")
        async with PacificaBot(
            private_key=account['api_secret'],
            public_key=api_key,
            agent_wallet=None,
            config=config
        ) as bot:
            await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Прервано пользователем")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")

