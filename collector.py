import aiohttp
import asyncio
import pandas as pd
from typing import Optional
import logging
import time
import json
import os
from typing import Optional, Dict, List
import pandas as pd
from config import Config
logger = logging.getLogger(__name__)


class KlineCache:
    """K线数据缓存管理器（使用Parquet格式）"""

    def __init__(self, cache_dir: str = "kline_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def get_cache_path(self, symbol: str, interval: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, f"{symbol}_{interval}.parquet")

    def load(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """加载缓存数据"""
        cache_path = self.get_cache_path(symbol, interval)
        if os.path.exists(cache_path):
            try:
                df = pd.read_parquet(cache_path)
                logger.debug(f"加载缓存: {symbol} {interval} {len(df)}条")
                return df
            except Exception as e:
                logger.warning(f"缓存加载失败: {e}")
        return None

    def save(self, symbol: str, interval: str, df: pd.DataFrame):
        """保存数据到缓存"""
        cache_path = self.get_cache_path(symbol, interval)
        try:
            df.to_parquet(cache_path, index=False)
            logger.debug(f"缓存保存: {symbol} {interval} {len(df)}条")
        except Exception as e:
            logger.warning(f"缓存保存失败: {e}")

    def update(self, symbol: str, interval: str, new_data: pd.DataFrame, max_length: int = 499):
        """更新缓存数据（替换末尾，保持长度）"""
        cache_path = self.get_cache_path(symbol, interval)

        if os.path.exists(cache_path):
            # 读取现有缓存
            old_df = pd.read_parquet(cache_path)

            # 合并数据（去掉重复的open_time）
            combined = pd.concat([old_df, new_data]).drop_duplicates(
                subset=['open_time'], keep='last'
            ).sort_values('open_time')

            # 只保留最新的 max_length 条
            updated_df = combined.tail(max_length)

            # 保存更新后的缓存
            updated_df.to_parquet(cache_path, index=False)
            logger.debug(f"缓存更新: {symbol} {interval} {len(old_df)}→{len(updated_df)}条")
            return updated_df
        else:
            # 没有缓存，直接保存
            new_data.tail(max_length).to_parquet(cache_path, index=False)
            return new_data


class BinanceKlineCollector:
    """K线数据收集器"""

    def __init__(self, proxy: Optional[str] = None, ):
        if proxy:
            self.proxy = proxy
        else:
            self.proxy = 'http://127.0.0.1:7890'

        self.total_bytes = 0
        self.request_count = 0
        self.before_bytes = 0
        self.before_request_count = 0

        self.update_kline_limit = Config.KLINE_LIMIT_UPDATE-2
        self.interval_max_delay = {
            '1m': 1*self.update_kline_limit * 60 * 1000,
            '3m': 3*self.update_kline_limit * 60 * 1000,
            '5m': 5*self.update_kline_limit * 60 * 1000,
            '15m': 15*self.update_kline_limit * 60 * 1000,
            '30m': 30*self.update_kline_limit * 60 * 1000,
            '1h': 1*self.update_kline_limit * 60 * 60 * 1000,
            '2h': 2*self.update_kline_limit * 60 * 60 * 1000,
            '4h': 4*self.update_kline_limit * 60 * 60 * 1000,
        }

        # 添加缓存管理器
        self.cache = KlineCache()
        self.first_scan_done = False  # 标记是否已完成首次扫描

    def save_stats_snapshot(self):
        """保存统计快照（用于计算本次扫描的增量）"""
        self.before_bytes = self.total_bytes
        self.before_request_count = self.request_count

    async def fetch_kline(self, symbol: str, interval: str, limit: int, max_retries: int = 3,
                          use_cache: bool = True) -> Optional[pd.DataFrame]:
        """获取单个币种K线数据，支持缓存

        Args:
            limit: 期望返回的K线数量（最终返回的数据长度）
            use_cache: 是否使用缓存（首次扫描时设为False）
        """

        # 如果不是首次扫描且启用了缓存，使用增量更新
        if use_cache and self.first_scan_done:
            # 增量获取时，只需要获取少量新数据
            fetch_limit = min(Config.KLINE_LIMIT_UPDATE, limit)  # 最多获取条新数据
            return await self.fetch_kline_incremental(symbol, interval, fetch_limit, limit, max_retries)
        else:
            # 首次扫描，全量获取
            return await self.fetch_kline_full(symbol, interval, limit, max_retries)

    async def _make_request_with_retry(self, url: str, params: dict, max_retries: int) -> Optional[tuple]:
        """带重试机制的请求方法，返回 (response_text, data) 或 None"""

        current_timestamp = time.time() * 1000

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, proxy=self.proxy,
                                           timeout=aiohttp.ClientTimeout(total=10)) as response:

                        response_text = await response.text()   #放在if外面  即使不是200状态码也统计花费流量
                        self.total_bytes += len(response_text.encode('utf-8'))
                        self.request_count += 1

                        if response.status == 200:
                            data = json.loads(response_text)

                            # 检查数据是否延迟
                            latest_close_time = data[-1][6]
                            delay_ms = current_timestamp - latest_close_time

                            if delay_ms > 0:
                                logger.debug(f"{params.get('symbol')} 数据延迟，第{attempt + 1}次重试")
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(3)
                                    current_timestamp = time.time() * 1000
                                    continue
                                else:
                                    logger.warning(f"{params.get('symbol')} 数据持续延迟，放弃重试")
                                    return None

                            return response_text, data

            except asyncio.TimeoutError:
                logger.warning(f"{params.get('symbol')} 请求超时，第{attempt + 1}次重试")
            except Exception as e:
                logger.warning(f"{params.get('symbol')} 请求异常: {e}，第{attempt + 1}次重试")

            # 统一的重试逻辑
            if attempt < max_retries - 1:
                await asyncio.sleep(3)
                current_timestamp = time.time() * 1000

        return None
    async def fetch_kline_full(self, symbol: str, interval: str, limit: int, max_retries: int) -> Optional[
        pd.DataFrame]:
        """全量获取K线数据（首次扫描用）"""
        url = 'https://fapi.binance.com/fapi/v1/klines'
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}

        result = await self._make_request_with_retry(url, params, max_retries)
        if result is None:
            return None

        response_text, data = result

        # 转换为DataFrame
        df = pd.DataFrame([item[:7] for item in data],
                          columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time'])
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)

        # 保存到缓存
        self.cache.save(symbol, interval, df)

        return df

    async def fetch_kline_incremental(self, symbol: str, interval: str, fetch_limit: int,
                                      target_length: int, max_retries: int) -> Optional[pd.DataFrame]:
        """增量获取K线数据"""
        # 先检查缓存
        cached_df = self.cache.load(symbol, interval)

        # 检查缓存是否存在且完整
        if cached_df is None:
            logger.debug(f"{symbol} 无缓存，使用全量获取")
            return await self.fetch_kline_full(symbol, interval, target_length, max_retries)
        elif len(cached_df) < Config.KLINE_LIMIT:
            logger.debug(f"{symbol} 缓存不完整 ({len(cached_df)}/{Config.KLINE_LIMIT})，使用全量获取")
            return await self.fetch_kline_full(symbol, interval, target_length, max_retries)

        # 检查缓存时效性
        latest_time = cached_df['close_time'].iloc[-1]
        current_time = time.time() * 1000
        max_delay = self.interval_max_delay.get(interval, 30 * 60 * 1000)
        time_diff = current_time - latest_time

        if time_diff > max_delay:
            logger.debug(f"{symbol} {interval} 缓存已过期 ({time_diff / 1000 / 60:.1f}分钟 > {max_delay / 1000 / 60}分钟)，重新全量获取")
            return await self.fetch_kline_full(symbol, interval, target_length, max_retries)

        # 获取最新K线
        url = 'https://fapi.binance.com/fapi/v1/klines'
        params = {'symbol': symbol, 'interval': interval, 'limit': fetch_limit}

        result = await self._make_request_with_retry(url, params, max_retries)
        if result is None:
            logger.warning(f"{symbol} 增量获取失败，返回缓存数据")
            return None  # 返回缓存数据，而不是 None

        response_text, data = result

        # 转换为DataFrame
        new_df = pd.DataFrame([item[:7] for item in data],
                              columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time'])
        new_df[['open', 'high', 'low', 'close', 'volume']] = new_df[['open', 'high', 'low', 'close', 'volume']].astype(
            float)

        # 更新缓存
        updated_df = self.cache.update(symbol, interval, new_df, max_length=target_length)

        return updated_df