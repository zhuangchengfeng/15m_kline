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
    """K线数据缓存管理器（内存缓存 + 异步持久化）"""

    def __init__(self, cache_dir: str = "kline_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

        # 内存缓存
        self._memory_cache: Dict[str, pd.DataFrame] = {}

        # 启动时加载所有现有缓存到内存
        # self._load_all_to_memory()

    def _get_cache_key(self, symbol: str, interval: str) -> str:
        """获取缓存键"""
        return f"{symbol}_{interval}"

    def _get_cache_path(self, symbol: str, interval: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, f"{symbol}_{interval}.parquet")

    def _load_all_to_memory(self):
        """启动时加载所有现有缓存到内存"""
        try:
            for file in os.listdir(self.cache_dir):
                if file.endswith('.parquet'):
                    # 从文件名解析 symbol 和 interval
                    name_parts = file.replace('.parquet', '').split('_')
                    if len(name_parts) >= 2:
                        symbol = '_'.join(name_parts[:-1])  # 处理可能带下划线的symbol
                        interval = name_parts[-1]
                        cache_path = os.path.join(self.cache_dir, file)
                        try:
                            df = pd.read_parquet(cache_path)
                            cache_key = self._get_cache_key(symbol, interval)
                            self._memory_cache[cache_key] = df
                            logger.debug(f"预加载缓存到内存: {symbol} {interval} {len(df)}条")
                        except Exception as e:
                            logger.warning(f"预加载缓存失败 {file}: {e}")
            logger.info(f"内存缓存初始化完成，已加载 {len(self._memory_cache)} 个缓存文件")
        except Exception as e:
            logger.warning(f"扫描缓存目录失败: {e}")

    def _save_to_disk(self, symbol: str, interval: str, df: pd.DataFrame):
        """同步保存到磁盘（保持原有接口但内部使用）"""
        cache_path = self._get_cache_path(symbol, interval)
        try:
            if Config.SAVE_DISK:
                df.to_parquet(cache_path, index=False)
                logger.debug(f"缓存持久化: {symbol} {interval} {len(df)}条")
        except Exception as e:
            logger.warning(f"缓存持久化失败: {e}")

    def get_memory_size_mb(self) -> float:
        """获取内存缓存占用的字节大小（MB）"""
        total_bytes = 0

        for key, df in self._memory_cache.items():
            # 估算 DataFrame 的内存占用
            try:
                # 方法1：使用 pandas 的 memory_usage
                df_bytes = df.memory_usage(deep=True).sum()
                total_bytes += df_bytes
                logger.debug(f"{key} 内存占用: {df_bytes / (1024 * 1024):.2f} MB")
            except Exception as e:
                logger.warning(f"计算 {key} 内存占用失败: {e}")

        # 转换为 MB
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
        """加载缓存数据（从内存加载）"""
        cache_key = self._get_cache_key(symbol, interval)

        # 从内存获取
        df = self._memory_cache.get(cache_key)

        if df is not None:
            logger.debug(f"内存缓存命中: {symbol} {interval} {len(df)}条")
            return df

        # 内存没有，尝试从磁盘加载
        cache_path = self._get_cache_path(symbol, interval)
        if os.path.exists(cache_path):
            try:
                df = pd.read_parquet(cache_path)
                # 加载到内存
                self._memory_cache[cache_key] = df
                logger.debug(f"从磁盘加载到内存: {symbol} {interval} {len(df)}条")
                return df
            except Exception as e:
                logger.warning(f"缓存加载失败: {e}")

        return None

    def save(self, symbol: str, interval: str, df: pd.DataFrame):
        """保存数据到缓存（内存 + 磁盘）"""
        cache_key = self._get_cache_key(symbol, interval)

        # 保存到内存
        self._memory_cache[cache_key] = df

        # 同步保存到磁盘（保持简单，不引入异步）
        self._save_to_disk(symbol, interval, df)

        logger.debug(f"缓存保存: {symbol} {interval} {len(df)}条")

    def update(self, symbol: str, interval: str, new_data: pd.DataFrame, max_length: int = 499):
        """更新缓存数据（内存操作 + 磁盘持久化）"""
        cache_key = self._get_cache_key(symbol, interval)

        # 从内存获取现有缓存
        old_df = self._memory_cache.get(cache_key)

        if old_df is not None:
            # 快速路径：如果新数据的第一条时间晚于旧数据的最后一条时间
            if len(old_df) > 0 and len(new_data) > 0:
                last_old_time = old_df['open_time'].iloc[-1]
                first_new_time = new_data['open_time'].iloc[0]

                if first_new_time > last_old_time:
                    # 简单拼接，避免复杂的合并操作
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

            # 更新内存缓存
            self._memory_cache[cache_key] = updated_df
                # 保存到磁盘
            self._save_to_disk(symbol, interval, updated_df)

            logger.debug(f"内存缓存更新: {symbol} {interval} {len(old_df)}→{len(updated_df)}条")
            return updated_df
        else:
            # 内存中没有，但可能有磁盘文件
            cache_path = self._get_cache_path(symbol, interval)
            if os.path.exists(cache_path):
                try:
                    old_df = pd.read_parquet(cache_path)
                    # 合并数据
                    combined = pd.concat([old_df, new_data]).drop_duplicates(
                        subset=['open_time'], keep='last'
                    ).sort_values('open_time')
                    updated_df = combined.tail(max_length)

                    # 保存到内存和磁盘
                    self._memory_cache[cache_key] = updated_df
                    self._save_to_disk(symbol, interval, updated_df)

                    logger.debug(f"磁盘缓存更新后加载到内存: {symbol} {interval} {len(old_df)}→{len(updated_df)}条")
                    return updated_df
                except Exception as e:
                    logger.warning(f"缓存更新失败: {e}")

            # 完全没有缓存，直接保存
            result_df = new_data.tail(max_length)
            self._memory_cache[cache_key] = result_df
            self._save_to_disk(symbol, interval, result_df)
            return result_df


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

        # 添加缓存管理器（现在使用内存缓存）
        self.cache = KlineCache()
        self.first_scan_done = False  # 标记是否已完成首次扫描

        # 创建带连接池限制的 session
        connector = aiohttp.TCPConnector(
            limit=20,  # 最大并发连接数
            limit_per_host=10,  # 每个主机的最大连接数
            ttl_dns_cache=300,  # DNS缓存时间
            enable_cleanup_closed=True  # 自动清理关闭的连接
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

        # 每24小时重新创建 session（避免SSL问题）
        if time.time() - self.session_created_time > 86400:
            await self.session.close()
            self.session = aiohttp.ClientSession()
            self.session_created_time = time.time()

    def get_cache_memory_mb(self) -> float:
        """获取内存缓存占用的MB大小"""
        return self.cache.get_memory_size_mb()

    def get_cache_memory_stats(self) -> Dict:
        """获取详细的内存缓存统计"""
        return self.cache.get_memory_stats()

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
        await self.ensure_session_valid()  # 确保 session 有效

        current_timestamp = time.time() * 1000
        symbol = params.get('symbol', 'unknown') if params else 'unknown'

        for attempt in range(max_retries):
            try:
                # 使用共享 session
                async with self.session.get(url, params=params, proxy=self.proxy,
                                            timeout=aiohttp.ClientTimeout(total=10)) as response:

                    response_text = await response.text()
                    self.total_bytes += len(response_text.encode('utf-8'))
                    self.request_count += 1

                    if response.status == 200:
                        data = json.loads(response_text)

                        # 检查数据是否延迟
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
                    # 最后一次超时，可能需要重建 session
                    await self.session.close()
                    self.session = aiohttp.ClientSession()
            except aiohttp.ClientConnectorError as e:
                logger.warning(f"{symbol} 连接错误: {e}，第{attempt + 1}次重试")
                # 连接错误，重建 session
                await self.session.close()
                self.session = aiohttp.ClientSession()
            except Exception as e:
                logger.warning(f"{symbol} 请求异常: {e}，第{attempt + 1}次重试")

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

        # 保存到缓存（保存到内存和磁盘）
        self.cache.save(symbol, interval, df)

        return df

    async def fetch_kline_incremental(self, symbol: str, interval: str, fetch_limit: int,
                                      target_length: int, max_retries: int) -> Optional[pd.DataFrame]:
        """增量获取K线数据"""
        # 先检查缓存（从内存加载）
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
            logger.debug(
                f"{symbol} {interval} 缓存已过期 ({time_diff / 1000 / 60:.1f}分钟 > {max_delay / 1000 / 60}分钟)，重新全量获取")
            return await self.fetch_kline_full(symbol, interval, target_length, max_retries)

        # 获取最新K线
        url = 'https://fapi.binance.com/fapi/v1/klines'
        params = {'symbol': symbol, 'interval': interval, 'limit': fetch_limit}

        result = await self._make_request_with_retry(url, params, max_retries)
        if result is None:
            logger.warning(f"{symbol} 增量获取失败，返回None数据")
            return None

        response_text, data = result

        # 转换为DataFrame
        new_df = pd.DataFrame([item[:7] for item in data],
                              columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time'])
        new_df[['open', 'high', 'low', 'close', 'volume']] = new_df[['open', 'high', 'low', 'close', 'volume']].astype(
            float)

        # 更新缓存（内存操作 + 磁盘持久化）
        updated_df = self.cache.update(symbol, interval, new_df, max_length=target_length)

        return updated_df

    async def close(self):
        """关闭session"""
        if self.session:
            await self.session.close()