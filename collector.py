import aiohttp
import asyncio
import pandas as pd
from typing import Optional
import logging
import time

logger = logging.getLogger(__name__)

class BinanceKlineCollector:
    """K线数据收集器"""

    def __init__(self,proxy: Optional[str] = None,):
        if proxy:
            self.proxy = proxy
        else:
            self.proxy = 'http://127.0.0.1:7890'


    async def fetch_kline(self, symbol: str, interval: str, limit: int, max_retries: int = 3) -> Optional[pd.DataFrame]:
        """获取单个币种K线数据，带有重试机制"""
        url = 'https://fapi.binance.com/fapi/v1/klines'
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}

        # 获取当前时间戳
        current_timestamp = time.time() * 1000

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, proxy=self.proxy,
                                           timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            data = await response.json()
                            # 检查数据是否延迟（最新K线的收盘时间应该接近当前时间）
                            latest_close_time = data[-1][6]  # 最新一根K线的收盘时间

                            # 计算延迟（单位：毫秒）
                            delay_ms = current_timestamp - latest_close_time
                            if delay_ms > 0:  #
                                logger.warning(f"{symbol} 数据延迟，第{attempt + 1}次重试")

                                if attempt < max_retries - 1:
                                    # 等待一小段时间后重试
                                    await asyncio.sleep(3)
                                    # 更新当前时间戳
                                    current_timestamp = time.time() * 1000
                                    continue
                                else:
                                    logger.error(f"{symbol} 数据持续延迟，放弃重试")

                            # 只取前7列数据
                            df = pd.DataFrame([item[:7] for item in data],
                                              columns=['open_time', 'open', 'high', 'low', 'close', 'volume',
                                                       'close_time'])
                            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
                            return df
                        else:
                            logger.warning(f"{symbol} 请求失败，状态码: {response.status}")

            except asyncio.TimeoutError:
                logger.warning(f"{symbol} 请求超时，第{attempt + 1}次重试")
            except Exception as e:
                logger.warning(f"{symbol} 请求异常: {e}，第{attempt + 1}次重试")

            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                # 更新当前时间戳
                current_timestamp = time.time() * 1000

        return None