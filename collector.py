import aiohttp
import asyncio
import pandas as pd
from typing import Optional
import logging
import time
import json
from typing import Optional, Dict, List
import pandas as pd
from config import Config
import config as cf

logger = logging.getLogger(__name__)


class KlineCache:
    """K线数据缓存管理器（仅内存缓存）"""

    def __init__(self):
        # 内存缓存
        self._memory_cache: Dict[str, pd.DataFrame] = {}

    def _get_cache_key(self, symbol: str, interval: str) -> str:
        """获取缓存键"""
        return f"{symbol}_{interval}"

    def get_memory_size_mb(self) -> float:
        """获取内存缓存占用的字节大小（MB）"""
        total_bytes = 0

        for key, df in self._memory_cache.items():
            try:
                df_bytes = df.memory_usage(deep=True).sum()
                total_bytes += df_bytes
                logger.debug(f"{key} 内存占用: {df_bytes / (1024 * 1024):.2f} MB")
            except Exception as e:
                logger.warning(f"计算 {key} 内存占用失败: {e}")

        total_mb = total_bytes / (1024 * 1024)
        return total_mb

    def get_memory_stats(self) -> Dict:
        """获取详细的内存统计信息"""
        stats = {
            'total_items': len(self._memory_cache),
            'items_detail': [],
            'total_mb': 0
        }

        total_bytes = 0
        for key, df in self._memory_cache.items():
            try:
                df_bytes = df.memory_usage(deep=True).sum()
                total_bytes += df_bytes
                stats['items_detail'].append({
                    'key': key,
                    'rows': len(df),
                    'columns': len(df.columns),
                    'mb': df_bytes / (1024 * 1024)
                })
            except Exception as e:
                stats['items_detail'].append({
                    'key': key,
                    'error': str(e)
                })

        stats['total_mb'] = total_bytes / (1024 * 1024)
        stats['total_bytes'] = total_bytes
        return stats

    def load(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """从内存加载缓存数据"""
        cache_key = self._get_cache_key(symbol, interval)
        df = self._memory_cache.get(cache_key)
        if df is not None:
            logger.debug(f"内存缓存命中: {symbol} {interval} {len(df)}条")
        return df

    def save(self, symbol: str, interval: str, df: pd.DataFrame):
        """保存数据到内存缓存"""
        cache_key = self._get_cache_key(symbol, interval)
        self._memory_cache[cache_key] = df
        logger.debug(f"缓存保存: {symbol} {interval} {len(df)}条")

    def update(self, symbol: str, interval: str, new_data: pd.DataFrame, max_length: int = 499):
        """更新缓存数据（仅内存操作）"""
        cache_key = self._get_cache_key(symbol, interval)
        old_df = self._memory_cache.get(cache_key)

        if old_df is not None:
            if len(old_df) > 0 and len(new_data) > 0:
                last_old_time = old_df['open_time'].iloc[-1]
                first_new_time = new_data['open_time'].iloc[0]

                if first_new_time > last_old_time:
                    # 简单拼接
                    combined = pd.concat([old_df, new_data])
                    updated_df = combined.tail(max_length)
                else:
                    # 需要去重和排序
                    combined = pd.concat([old_df, new_data]).drop_duplicates(
                        subset=['open_time'], keep='last'
                    ).sort_values('open_time')
                    updated_df = combined.tail(max_length)
            else:
                updated_df = new_data.tail(max_length)

            self._memory_cache[cache_key] = updated_df
            logger.debug(f"内存缓存更新: {symbol} {interval} {len(old_df)}→{len(updated_df)}条")
            return updated_df
        else:
            # 无缓存，直接保存
            result_df = new_data.tail(max_length)
            self._memory_cache[cache_key] = result_df
            return result_df

    def interval_to_ms(self, interval: str) -> int:
        """将K线周期转换为毫秒数"""
        minutes = cf.INTERVAL_TO_MIN.get(interval, 0)
        if minutes == 0:
            raise ValueError(f"Unknown interval: {interval}")
        return minutes * 60 * 1000

    def is_continuous(self, symbol: str, interval: str) -> bool:
        """检查某个缓存是否连续"""
        df = self.load(symbol, interval)
        if df is None or len(df) <= 1:
            return True
        expected_ms = self.interval_to_ms(interval)
        diffs = df['open_time'].diff().iloc[1:]
        # 允许 ±1 秒的误差
        return (abs(diffs - expected_ms) <= 1000).all()


class BinanceKlineCollector:
    """K线数据收集器"""

    def __init__(self, proxy: Optional[str] = None):
        if proxy:
            self.proxy = proxy
        else:
            self.proxy = 'http://127.0.0.1:7890'

        self.total_bytes = 0
        self.request_count = 0
        self.before_bytes = 0
        self.before_request_count = 0

        self.update_kline_limit = Config.KLINE_LIMIT_UPDATE - 2
        self.interval_max_delay = {
            '1m': 1 * self.update_kline_limit * 60 * 1000,
            '3m': 3 * self.update_kline_limit * 60 * 1000,
            '5m': 5 * self.update_kline_limit * 60 * 1000,
            '15m': 15 * self.update_kline_limit * 60 * 1000,
            '30m': 30 * self.update_kline_limit * 60 * 1000,
            '1h': 1 * self.update_kline_limit * 60 * 60 * 1000,
            '2h': 2 * self.update_kline_limit * 60 * 60 * 1000,
            '4h': 4 * self.update_kline_limit * 60 * 60 * 1000,
        }

        self.cache = KlineCache()
        self.first_scan_done = False

        connector = aiohttp.TCPConnector(
            limit=150,
            limit_per_host=150,
            ttl_dns_cache=3600,
            enable_cleanup_closed=True
        )

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=10)
        )
        self.session_created_time = time.time()

    async def ensure_session_valid(self):
        """确保 session 有效"""
        if self.session.closed:
            self.session = aiohttp.ClientSession()
            self.session_created_time = time.time()

        if time.time() - self.session_created_time > 86400:
            await self.session.close()
            self.session = aiohttp.ClientSession()
            self.session_created_time = time.time()

    def get_cache_memory_mb(self) -> float:
        return self.cache.get_memory_size_mb()

    def get_cache_memory_stats(self) -> Dict:
        return self.cache.get_memory_stats()

    def save_stats_snapshot(self):
        self.before_bytes = self.total_bytes
        self.before_request_count = self.request_count

    async def fetch_kline(self, symbol: str, interval: str, limit: int, max_retries: int = 3,
                          use_cache: bool = True, endtime=None) -> Optional[pd.DataFrame]:
        """获取单个币种K线数据，支持缓存

        Args:
            limit: 期望返回的K线数量（最终返回的数据长度）
            use_cache: 是否使用缓存（首次扫描时设为False）
        """
        if use_cache and self.first_scan_done:
            # 增量获取时，只需要获取少量新数据
            fetch_limit = min(Config.KLINE_LIMIT_UPDATE, limit)
            return await self.fetch_kline_incremental(symbol, interval, fetch_limit, limit, max_retries)
        else:
            # 首次扫描，全量获取
            return await self.fetch_kline_full(symbol, interval, limit, max_retries, endtime=endtime)

    async def _make_request_with_retry(self, url: str, params: dict, max_retries: int, endtime=None) -> Optional[tuple]:
        await self.ensure_session_valid()
        current_timestamp = time.time() * 1000
        symbol = params.get('symbol', 'unknown') if params else 'unknown'

        for attempt in range(max_retries):
            try:
                async with self.session.get(url, params=params, proxy=self.proxy,
                                            timeout=aiohttp.ClientTimeout(total=10)) as response:
                    response_text = await response.text()
                    self.total_bytes += len(response_text.encode('utf-8'))
                    self.request_count += 1
                    if response.status == 200:
                        data = json.loads(response_text)
                        if endtime is None:
                            latest_close_time = data[-1][6]
                            delay_ms = current_timestamp - latest_close_time
                            if delay_ms > 0:
                                logger.debug(f"{symbol} 数据延迟，第{attempt + 1}次重试")
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(3)
                                    current_timestamp = time.time() * 1000
                                    continue
                                else:
                                    logger.debug(f"{symbol} 数据持续延迟，放弃重试")
                                    return None
                        return response_text, data
            except asyncio.TimeoutError:
                logger.warning(f"{symbol} 请求超时，第{attempt + 1}次重试")
                if attempt == max_retries - 1:
                    await self.session.close()
                    self.session = aiohttp.ClientSession()
            except aiohttp.ClientConnectorError as e:
                logger.warning(f"{symbol} 连接错误: {e}，第{attempt + 1}次重试")
                await self.session.close()
                self.session = aiohttp.ClientSession()
            except Exception as e:
                logger.warning(f"{symbol} 请求异常: {e}，第{attempt + 1}次重试")

            if attempt < max_retries - 1:
                await asyncio.sleep(3)
                current_timestamp = time.time() * 1000

        return None

    async def fetch_kline_full(self, symbol: str, interval: str, limit: int, max_retries: int, endtime=None) -> Optional[pd.DataFrame]:
        url = 'https://fapi.binance.com/fapi/v1/klines'
        if endtime:
            params = {'symbol': symbol, 'interval': interval, 'limit': limit, 'endTime': endtime}
        else:
            params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        result = await self._make_request_with_retry(url, params, max_retries, endtime)
        if result is None:
            return None

        response_text, data = result
        df = pd.DataFrame([item[:7] for item in data],
                          columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time'])
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)

        self.cache.save(symbol, interval, df)
        return df

    async def fetch_kline_incremental(self, symbol: str, interval: str, fetch_limit: int,
                                      target_length: int, max_retries: int) -> Optional[pd.DataFrame]:
        cached_df = self.cache.load(symbol, interval)

        if cached_df is None:
            logger.debug(f"{symbol} 无缓存，使用全量获取")
            return await self.fetch_kline_full(symbol, interval, target_length, max_retries)
        elif len(cached_df) < target_length:
            logger.info(f"{symbol} 缓存不完整 ({len(cached_df)}/{target_length})，使用全量获取")
            return await self.fetch_kline_full(symbol, interval, target_length, max_retries)

        latest_time = cached_df['close_time'].iloc[-1]
        current_time = time.time() * 1000
        max_delay = self.interval_max_delay.get(interval, 30 * 60 * 1000)
        time_diff = current_time - latest_time

        if not self.cache.is_continuous(symbol, interval):
            logger.warning(f"{symbol} {interval} 缓存时间戳不连续，重新全量获取")
            return await self.fetch_kline_full(symbol, interval, target_length, max_retries)

        if time_diff > max_delay:
            logger.debug(f"{symbol} {interval} 缓存已过期 ({time_diff / 1000 / 60:.1f}分钟 > {max_delay / 1000 / 60}分钟)，重新全量获取")
            return await self.fetch_kline_full(symbol, interval, target_length, max_retries)

        url = 'https://fapi.binance.com/fapi/v1/klines'
        params = {'symbol': symbol, 'interval': interval, 'limit': fetch_limit}
        result = await self._make_request_with_retry(url, params, 5)
        if result is None:
            logger.warning(f"{symbol} 增量获取失败，返回None数据,{interval}周期")
            return None

        response_text, data = result
        new_df = pd.DataFrame([item[:7] for item in data],
                              columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time'])
        new_df[['open', 'high', 'low', 'close', 'volume']] = new_df[['open', 'high', 'low', 'close', 'volume']].astype(float)

        updated_df = self.cache.update(symbol, interval, new_df, max_length=target_length)
        return updated_df

    async def close(self):
        if self.session:
            await self.session.close()