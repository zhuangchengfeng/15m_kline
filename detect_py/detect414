# detect.py
import logging
from datetime import datetime, timezone, timedelta
from config import Config
from ema_atr_manager import EmaAtrManager
import config as cf
from structure import is_strong_bullish, check_risk_reward, is_strong_bearish, is_strong_bearish_double
import structure

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
        interval_check:'1h' '15m' '1d' '4h'
        result: K线数据 DICT
        symbol: 交易对
    Returns:
        tuple: 是否有信号,语言文本
    """
    has_signal = (0, None)

    kline_data = result['data']
    kline_data: pd.DataFrame
    if kline_data is None or len(kline_data) < Config.KLINE_LIMIT and cf.INTERVAL_TO_MIN.get(interval_check) < 240:
        return (0, None)

    if kline_data is None or len(kline_data) < 6 and cf.INTERVAL_TO_MIN.get(interval_check) == 10080:
        return (0, None)

    def price_power(x,y=None):
        if y is None:
            return abs(latest['close'] - latest['open']) > (abs(prev['close'] - prev['open']) * x)
        else:
            return (abs(latest['close'] - latest['open']) > (abs(prev['close'] - prev['open']) * x) and abs(latest['close'] - latest['open']) < (abs(prev['close'] - prev['open']) * y))

    def volume_power(x):
        return latest['volume'] >= (prev['volume'] * x)


    if 'LONG' in Config.POSITION_SIDE:
        if interval_check == '1w':
            current = kline_data.iloc[-1]
            latest = kline_data.iloc[-2]
            green = current['close']> current['open']
            # print(f'{interval_check},{green}')
            if green :
                has_signal = (1,'做多')
                return has_signal

        if interval_check == '15m':
            latest = kline_data.iloc[-2]  # 最新K线
            prev = kline_data.iloc[-3]  # 前一根K线
            red_green = (latest['close'] > latest['open']) and (prev['close'] < prev['open'])
            both_strong_bullish = structure.is_strong_bullish_double([latest,prev])

            if len(Config.BACK_TESTING_SYMBOLS) >=1:
                print(f"red_green:{red_green} \r\n"
                      f"price_power : {price_power(0.618,3.86)}\r\n"
                      f"is_strong_bullish : {is_strong_bullish(latest,0.5,0.618)}\r\n"
                      f"both_strong_bullish : {both_strong_bullish}\r\n")

            if both_strong_bullish:
                cross = structure.is_cross_above_boll(kline_data)
                if cross:
                    has_signal = (1, '做多')
                    return has_signal

            if (red_green and price_power(0.618) and is_strong_bullish(latest,0.5,2)):
                has_signal = (1, '做多')
                return has_signal

    if 'SHORT' in Config.POSITION_SIDE:
        if interval_check == '1w':
            current = kline_data.iloc[-1]
            red = current['close'] < current['open']

            if red:
                has_signal = (-1, '做空')
                return has_signal

        if interval_check == '15m':
            latest = kline_data.iloc[-2]  # 最新K线
            prev = kline_data.iloc[-3]  # 前一根K线
            red_green = (latest['close'] < latest['open']) and (prev['close'] > prev['open'])
            both_strong_bearish = structure.is_strong_bearish_double([latest, prev])

            if len(Config.BACK_TESTING_SYMBOLS) >= 1:
                print(f"red_green:{red_green} \r\n"
                      f"price_power : {price_power(1)}\r\n"
                      f"is_strong_bearish : {is_strong_bearish(latest, 0.5, 0.618)}\r\n"
                      f"both_strong_bearish : {both_strong_bearish}\r\n")

            if both_strong_bearish:
                cross = structure.is_cross_below_boll(kline_data)  # 空头使用下穿
                if cross:
                    has_signal = (-1, '做空')
                    return has_signal

            if (red_green and price_power(0.618) and is_strong_bearish(latest, 0.5, 0.618)):
                has_signal = (-1, '做空')
                return has_signal
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
