# detect.py
import logging
from datetime import datetime, timezone, timedelta
from config import Config
from ema_atr_manager import EmaAtrManager
import config as cf
from structure import is_strong_bullish, check_risk_reward, is_strong_bearish, is_strong_bearish_double
import structure
import smc   #付费使用包 VX：Tugzcf

ema_atr = EmaAtrManager()
logger = logging.getLogger(__name__)

# 设置北京时区
BEIJING_TZ = timezone(timedelta(hours=8))
UTC_TZ = timezone.utc

import pandas as pd
import numpy as np


def detect_signal(interval_check, result: dict) -> tuple:
    """
    检测形态并可选地记录信号

    Args:
        interval_check: '1h' '15m' '1d' '4h'
        result: K线数据 DICT
    Returns:
        tuple: 是否有信号 (1/-1, 文本) 或 (0, None)
    """
    has_signal = (0, None)

    kline_data = result['data']
    if kline_data is None or len(kline_data) < Config.KLINE_LIMIT and cf.INTERVAL_TO_MIN.get(interval_check) < 240:
        return (0, None)

    if kline_data is None or len(kline_data) < 6 and cf.INTERVAL_TO_MIN.get(interval_check) == 10080:
        return (0, None)

    prev = kline_data.iloc[-3]
    def price_power(x):
        return abs(latest['close'] - latest['open']) > (abs(prev['close'] - prev['open']) * x)

    def volume_power(x):
        return latest['volume'] >= (prev['volume'] * x)

    # 长影线阈值：影线长度占整根K线长度的比例
    SHADOW_RATIO_THRESHOLD = 0.6   # 60% 以上认定为“很长”

    # ========== 多头（LONG） ==========
    if 'LONG' in Config.POSITION_SIDE:
        # 周线信号：当前K线为阳线
        if interval_check == '1w':
            current = kline_data.iloc[-1]
            if current['close'] > current['open']:
                return (1, '做多')

        # 15分钟信号：最新K线具有很长的下影线
        if interval_check == '15m':
            latest = kline_data.iloc[-2]   # 最新已完成的K线

            red_green = (latest['close'] > latest['open']) and (prev['close'] < prev['open'])
            close_prices = kline_data['close'].astype(float).tolist()


            if red_green:

                # if structure.calculate_rsi(kline_data,position=-3) <= 30:
                #     if structure.is_price_at_low_zone(kline_data,20,None,0.3):
                #         return (1, '做多')
                low_zone = structure.is_price_at_low_zone(kline_data, percentile_threshold=0.618, iloc=-3) or  structure.is_price_at_low_zone(kline_data, percentile_threshold=0.618, iloc=-2)
                if price_power(2) and latest['close'] >= ema_atr.calculate_ema(close_prices)[-2] and low_zone:
                    return (1, '做多')
                # if price_power(3) and structure.is_price_at_low_zone(kline_data,percentile_threshold=0.25,iloc=-3) and structure.is_strong_bullish(latest,shadow_threshold=0.5):
                #     return (1, '做多')

            high = latest['high']
            low = latest['low']
            open_ = latest['open']
            close = latest['close']

            # 下影线长度 = min(open, close) - low
            lower_shadow = min(open_, close) - low
            total_range = high - low
            if total_range > 0 and (lower_shadow / total_range) >= SHADOW_RATIO_THRESHOLD and volume_power(1) and structure.is_price_at_low_zone(kline_data,percentile_threshold=0.386,iloc=-2):
                return (1, '做多')

    # ========== 空头（SHORT） ==========
    if 'SHORT' in Config.POSITION_SIDE:
        # 周线信号：当前K线为阴线
        if interval_check == '1w':
            current = kline_data.iloc[-1]
            if current['close'] < current['open']:
                return (-1, '做空')

        # 15分钟信号：最新K线具有很长的上影线
        if interval_check == '15m':
            latest = kline_data.iloc[-2]
            red_green = (latest['close'] < latest['open']) and (prev['close'] > prev['open'])
            if red_green:
                if structure.is_price_at_high_zone(kline_data,20,None,0.2) and price_power(2):
                    return (-1, '做空')

            high = latest['high']
            low = latest['low']
            open_ = latest['open']
            close = latest['close']

            # 上影线长度 = high - max(open, close)
            upper_shadow = high - max(open_, close)
            total_range = high - low

            if total_range > 0 and (upper_shadow / total_range) >= SHADOW_RATIO_THRESHOLD and volume_power(1):
                return (-1, '做空')

    return has_signal


# 辅助函数：时间戳转北京时间字符串
def timestamp_to_beijing_str(timestamp_ms: float) -> str:
    """
    将毫秒时间戳转换为北京时间的字符串

    Args:
        timestamp_ms: 毫秒时间戳

    Returns:
        str: 北京时间字符串，格式：YYYY/MM/DD HH:MM:SS
    """
    try:
        timestamp_seconds = timestamp_ms / 1000.0
        utc_time = datetime.fromtimestamp(timestamp_seconds, tz=UTC_TZ)
        beijing_time = utc_time.astimezone(BEIJING_TZ)
        return beijing_time.strftime("%Y/%m/%d %H:%M:%S")
    except Exception as e:
        logger.error(f"时间戳转换失败: {e}")
        return datetime.now(BEIJING_TZ).strftime("%Y/%m/%d %H:%M:%S")


# 测试函数
def test_time_conversion():
    """测试时间转换功能"""
    test_timestamp = 1734681600000  # 2025-12-20 00:00:00 UTC

    beijing_str = timestamp_to_beijing_str(test_timestamp)
    logger.info(f"测试时间转换: {test_timestamp} -> {beijing_str}")

    # 预期输出：2025/12/20 08:00:00 (UTC+8)
    return beijing_str


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 测试时间转换
    result = test_time_conversion()
    print(f"测试结果: {result}")
