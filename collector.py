import aiohttp
import asyncio
import pandas as pd
from typing import Optional, Dict, List
import logging
import time
import json
from config import Config
from config import INTERVAL_TO_MIN
import numpy as np

logger = logging.getLogger(__name__)
def aggregate_to_larger_interval(df_small: pd.DataFrame, target_interval: str) -> pd.DataFrame:
    """
    从小周期数据聚合生成大周期K线（不丢弃不完整的组，用于实时生成当前未完成K线）。
    """
    if df_small.empty:
        return pd.DataFrame(columns=df_small.columns)

    df = df_small.copy()
    df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
    df.set_index('timestamp', inplace=True)

    rule_map = {
        '1d': '1D',
        '1w': '1W-MON',
        '1h': '1H',
    }
    rule = rule_map.get(target_interval)
    if not rule:
        raise ValueError(f"不支持的聚合周期: {target_interval}")

    ohlc_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    resampled = df.resample(rule).agg(ohlc_dict)
    # 注意：不 dropna()，保留不完整的组（即当前未完成的大周期K线）

    resampled.reset_index(inplace=True)
    resampled.rename(columns={'timestamp': 'open_time'}, inplace=True)
    resampled['open_time'] = resampled['open_time'].astype(np.int64) // 10**6

    minutes = INTERVAL_TO_MIN.get(target_interval, 0)
    interval_ms = minutes * 60 * 1000
    resampled['close_time'] = resampled['open_time'] + interval_ms - 1

    return resampled[['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time']]

class KlineCache:
    """K线数据缓存管理器（仅内存缓存）"""

    def __init__(self):
        self._memory_cache: Dict[str, pd.DataFrame] = {}

    def _get_cache_key(self, symbol: str, interval: str) -> str:
        return f"{symbol}_{interval}"

    def get_memory_size_mb(self) -> float:
        total_bytes = 0
        for df in self._memory_cache.values():
            try:
                total_bytes += df.memory_usage(deep=True).sum()
            except Exception:
                pass
        return total_bytes / (1024 * 1024)

    def get_memory_stats(self) -> Dict:
        stats = {'total_items': len(self._memory_cache), 'items_detail': [], 'total_mb': 0}
        total_bytes = 0
        for key, df in self._memory_cache.items():
            try:
                df_bytes = df.memory_usage(deep=True).sum()
                total_bytes += df_bytes
                stats['items_detail'].append({
                    'key': key, 'rows': len(df), 'columns': len(df.columns),
                    'mb': df_bytes / (1024 * 1024)
                })
            except Exception as e:
                stats['items_detail'].append({'key': key, 'error': str(e)})
        stats['total_mb'] = total_bytes / (1024 * 1024)
        stats['total_bytes'] = total_bytes
        return stats

    def load(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        cache_key = self._get_cache_key(symbol, interval)
        df = self._memory_cache.get(cache_key)
        if df is not None:
            logger.debug(f"内存缓存命中: {symbol} {interval} {len(df)}条")
        return df

    def save(self, symbol: str, interval: str, df: pd.DataFrame):
        cache_key = self._get_cache_key(symbol, interval)
        self._memory_cache[cache_key] = df
        logger.debug(f"缓存保存: {symbol} {interval} {len(df)}条")

    def update(self, symbol: str, interval: str, new_data: pd.DataFrame, max_length: int = 499):
        cache_key = self._get_cache_key(symbol, interval)
        old_df = self._memory_cache.get(cache_key)

        if old_df is not None:
            if len(old_df) > 0 and len(new_data) > 0:
                last_old_time = old_df['open_time'].iloc[-1]
                first_new_time = new_data['open_time'].iloc[0]
                if first_new_time > last_old_time:
                    combined = pd.concat([old_df, new_data])
                    updated_df = combined.tail(max_length)
                else:
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
            result_df = new_data.tail(max_length)
            self._memory_cache[cache_key] = result_df
            return result_df

    def interval_to_ms(self, interval: str) -> int:
        minutes = INTERVAL_TO_MIN.get(interval, 0)
        if minutes == 0:
            raise ValueError(f"Unknown interval: {interval}")
        return minutes * 60 * 1000

    def is_continuous(self, symbol: str, interval: str) -> bool:
        df = self.load(symbol, interval)
        if df is None or len(df) <= 1:
            return True
        expected_ms = self.interval_to_ms(interval)
        diffs = df['open_time'].diff().iloc[1:]
        return (abs(diffs - expected_ms) <= 1000).all()


class BinanceKlineCollector:
    """K线数据收集器，支持小周期增量更新，大周期按需增量请求API"""

    def __init__(self, proxy: Optional[str] = None):
        if proxy:
            self.proxy = proxy
        else:
            self.proxy = 'http://127.0.0.1:7890'

        self.config = Config  # 添加对配置类的引用
        self.use_derived_mode = Config.USE_DERIVED_MODE  # 新增

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
            '12h': 12 * self.update_kline_limit * 60 * 60 * 1000,
            '1d': 24 * self.update_kline_limit * 60 * 60 * 1000,
            '1w': 24 * self.update_kline_limit * 60 * 60 * 1000 * 7,

        }

        self.cache = KlineCache()
        self.first_scan_done = False
        # 小周期：取配置中周期最小的一个
        self.small_interval = Config.KLINE_INTERVAL_SORT[-1]

        connector = aiohttp.TCPConnector(limit=150, limit_per_host=150, ttl_dns_cache=60, enable_cleanup_closed=True)
        self.session = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=10))
        self.session_created_time = time.time()
    def interval_to_ms(self, interval: str) -> int:
        minutes = INTERVAL_TO_MIN.get(interval, 0)
        if minutes == 0:
            raise ValueError(f"Unknown interval: {interval}")
        return minutes * 60 * 1000

    async def ensure_session_valid(self):
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
        """
        获取K线数据。
        如果 use_derived_mode = True（默认模式）：
            - 对于大周期且非首次扫描，直接从缓存读取（缓存由外部 update_large_interval 维护）。
            - 对于小周期或首次扫描，正常请求API。
        如果 use_derived_mode = False（非默认模式）：
            - 所有周期都正常请求API（支持增量更新）。
        """
        # 非派生模式：所有周期都走常规逻辑
        if not self.use_derived_mode:
            if use_cache and self.first_scan_done:
                fetch_limit = min(Config.KLINE_LIMIT_UPDATE, limit)
                return await self.fetch_kline_incremental(symbol, interval, fetch_limit, limit, max_retries)
            else:
                return await self.fetch_kline_full(symbol, interval, limit, max_retries, endtime)

        # 如果是大周期且非首次扫描，直接从缓存读取（缓存需由外部负责更新）
        if interval != self.small_interval and use_cache and self.first_scan_done:
            df = self.cache.load(symbol, interval)
            if df is not None:
                return df.tail(limit)
            else:
                # 缓存不存在，回退到全量请求
                logger.warning(f"{symbol} {interval} 缓存不存在，回退到全量API请求")
                return await self.fetch_kline_full(symbol, interval, limit, max_retries, endtime)

        # 小周期或首次扫描：正常请求API
        if use_cache and self.first_scan_done:
            fetch_limit = min(Config.KLINE_LIMIT_UPDATE, limit)
            return await self.fetch_kline_incremental(symbol, interval, fetch_limit, limit, max_retries)
        else:
            return await self.fetch_kline_full(symbol, interval, limit, max_retries, endtime)

    # 在 BinanceKlineCollector 类中添加以下辅助方法
    def _update_ongoing_with_latest_small(self, ongoing_df: pd.DataFrame, latest_small: pd.Series) -> pd.DataFrame:
        """
        根据最新的一根小周期K线，更新当前未完成的大周期K线（只更新 high, low, close, volume）
        """
        if ongoing_df.empty:
            return ongoing_df
        updated = ongoing_df.copy()
        # 最高价
        if latest_small['high'] > updated['high'].iloc[0]:
            updated.iloc[0, updated.columns.get_loc('high')] = latest_small['high']
        # 最低价
        if latest_small['low'] < updated['low'].iloc[0]:
            updated.iloc[0, updated.columns.get_loc('low')] = latest_small['low']
        # 收盘价（始终更新为最新小周期的收盘价）
        updated.iloc[0, updated.columns.get_loc('close')] = latest_small['close']
        # 成交量：加上最新小周期的成交量（API返回的未完成K线已包含之前的成交量）
        updated.iloc[0, updated.columns.get_loc('volume')] += latest_small['volume']
        return updated

    async def update_large_interval(self, symbol: str, interval: str, target_length: int, max_retries: int, return_nan=False) -> Optional[
        pd.DataFrame]:
        """
        大周期数据更新策略：
        - 历史已完成的大周期K线：从 API 获取并缓存，不再修改。
        - 当前正在运行的大周期K线：基于最新的一根小周期K线，实时更新其 high, low, close, volume。
        volume 懒得设计准确了，差不多就行了,否则代码太复杂难维护
        - 开盘价始终不变。
        """
        small_interval = self.config.KLINE_INTERVAL_SORT[-1]
        small_df = self.cache.load(symbol, small_interval)
        if small_df is None or len(small_df) < Config.get_kline_limit(small_interval):
            if return_nan:
                return None
            else:
                logger.debug(f"{symbol} 小周期数据不足，无法更新{interval}，回退全量API")
                return await self.fetch_kline_full(symbol, interval, target_length, max_retries, None)

        # 1. 获取当前缓存的大周期数据
        cached_df = self.cache.load(symbol, interval)
        current_time_ms = int(time.time() * 1000)
        # 2. 分离已完成和未完成部分
        if cached_df is None:
            logger.debug(f"{symbol} {interval} 无缓存，从API获取历史数据")
            hist_df = await self.fetch_kline_full(symbol, interval, target_length, max_retries, None)
            if hist_df is None:
                return None
            cached_df = hist_df

        completed_mask = cached_df['close_time'] <= current_time_ms
        completed_df = cached_df[completed_mask].copy()
        ongoing_mask = cached_df['close_time'] > current_time_ms
        ongoing_df = cached_df[ongoing_mask].copy()
        # 3. 检查是否需要追加新的已完成K线（新的大周期已收盘）
        if not completed_df.empty:
            last_completed = completed_df.iloc[-1]
            last_completed_close = last_completed['close_time']
            if current_time_ms > last_completed_close + self.interval_to_ms(interval):
                fetch_limit = 2
                url = 'https://fapi.binance.com/fapi/v1/klines'
                params = {'symbol': symbol, 'interval': interval, 'limit': fetch_limit}
                result = await self._make_request_with_retry(url, params, max_retries, None)
                if result:
                    _, data = result
                    new_hist_df = pd.DataFrame([item[:7] for item in data],
                                               columns=['open_time', 'open', 'high', 'low', 'close', 'volume',
                                                        'close_time'])
                    new_hist_df[['open', 'high', 'low', 'close', 'volume']] = new_hist_df[
                        ['open', 'high', 'low', 'close', 'volume']].astype(float)
                    combined = pd.concat([completed_df, new_hist_df]).drop_duplicates(subset=['open_time'],
                                                                                      keep='last').sort_values(
                        'open_time')
                    completed_df = combined
                    logger.debug(f"{symbol} {interval} 追加新的已完成K线，总长度 {len(completed_df)}")
                    # 新周期开始，清空未完成部分（新周期未完成K线将由后续聚合生成）
                    ongoing_df = pd.DataFrame(columns=cached_df.columns)

        # 4. 更新当前未完成的大周期K线
        # 如果 ongoing_df 为空，说明刚进入新周期，需要根据小周期数据生成初始未完成K线
        if ongoing_df.empty:
            # 聚合生成当前未完成K线（只取最后一根）
            aggregated_all = aggregate_to_larger_interval(small_df, interval)
            if aggregated_all.empty:
                final_df = pd.concat([completed_df, ongoing_df]).tail(target_length)
                self.cache.save(symbol, interval, final_df)
                return final_df
            ongoing_df = aggregated_all.tail(1).copy()
            # 记录当前已处理到的最新小周期时间戳，避免重复累加
            if not hasattr(self, '_last_processed_small_time'):
                self._last_processed_small_time = {}
            self._last_processed_small_time[(symbol, interval)] = small_df['open_time'].iloc[-1]
        else:
            # 已有未完成K线，只处理新增的最新一根小周期K线
            if not hasattr(self, '_last_processed_small_time'):
                self._last_processed_small_time = {}
            last_time = self._last_processed_small_time.get((symbol, interval), 0)
            # 获取最新的一根小周期K线
            latest_small = small_df.iloc[-1]
            if latest_small['open_time'] > last_time:
                ongoing_df = self._update_ongoing_with_latest_small(ongoing_df, latest_small)
                self._last_processed_small_time[(symbol, interval)] = latest_small['open_time']

        # 5. 合并已完成和未完成部分，并截断到 target_length
        final_df = pd.concat([completed_df, ongoing_df]).drop_duplicates(subset=['open_time'], keep='last').sort_values(
            'open_time')
        final_df = final_df.tail(target_length)

        self.cache.save(symbol, interval, final_df)
        logger.debug(
            f"📈 大周期更新: {symbol} {interval} 历史长度={len(completed_df)} 当前未完成长度={len(ongoing_df)} 总长度={len(final_df)}")

        return final_df

    async def _make_request_with_retry(self, url: str, params: dict, max_retries: int, endtime=None) -> Optional[tuple]:
        await self.ensure_session_valid()
        logger.debug(f"🌐 _make_request_with_retry发起请求: {params.get('symbol')} {params.get('interval')} limit={params.get('limit')} max_retries={max_retries}")
        current_timestamp = time.time() * 1000
        symbol = params.get('symbol', 'unknown')

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
                                logger.debug(f"{symbol} {params.get('interval')}数据延迟，第{attempt + 1}次重试")
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(1.5)
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
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        if endtime:
            params['endTime'] = endtime
        result = await self._make_request_with_retry(url, params, max_retries, endtime)
        if result is None:
            return None
        _, data = result
        df = pd.DataFrame([item[:7] for item in data],
                          columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time'])
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        self.cache.save(symbol, interval, df)
        return df

    async def fetch_kline_incremental(self, symbol: str, interval: str, fetch_limit: int,
                                      target_length: int, max_retries: int) -> Optional[pd.DataFrame]:
        cached_df = self.cache.load(symbol, interval)
        logger.debug(f"📡 增量请求 {symbol} {interval} fetch_limit={fetch_limit} target_length={target_length}")

        if cached_df is None:
            logger.debug(f"{symbol} 无缓存，使用全量获取")
            return await self.fetch_kline_full(symbol, interval, target_length, max_retries)
        elif len(cached_df) < target_length:
            logger.debug(f"{symbol} 缓存不完整 ({len(cached_df)}/{target_length})，使用全量获取")
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
        result = await self._make_request_with_retry(url, params, max_retries)
        if result is None:
            logger.warning(f"{symbol} 增量获取失败，返回None数据,{interval}周期")
            return None
        _, data = result
        new_df = pd.DataFrame([item[:7] for item in data],
                              columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time'])
        new_df[['open', 'high', 'low', 'close', 'volume']] = new_df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        logger.debug(f"📥 收到新数据 {symbol} {interval} {len(new_df)}条, 时间范围: {new_df['open_time'].iloc[0]} ~ {new_df['open_time'].iloc[-1]}")

        updated_df = self.cache.update(symbol, interval, new_df, max_length=target_length)
        return updated_df

    async def close(self):
        if self.session:
            await self.session.close()