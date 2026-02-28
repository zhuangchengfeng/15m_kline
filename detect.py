# detect.py
import logging
from datetime import datetime, timezone, timedelta
from config import Config
from ema_atr_manager import EmaAtrManager

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
    if kline_data is None or len(kline_data) < Config.KLINE_LIMIT and interval_check != '1d':
        return (0, None)
    # current = kline_data.iloc[-1]
    prev = kline_data.iloc[-3]  # 前一根K线
    latest = kline_data.iloc[-2]  # 最新K线

    extra_prev = kline_data.iloc[-4]
    # extra_prev_2 = kline_data.iloc[-5]

    # r_g_p = detect_rg_pattern_signals(kline_data)
    # ema_diff_atr = ema_atr.run(symbol=result['symbol'],klines=kline_data,interval_check=interval_check)
    # atr = ema_atr.run(symbol=result['symbol'],klines=kline_data,interval_check=interval_check,return_x='atr')

    def price_power(x):
        return abs(latest['close'] - latest['open']) > (abs(prev['close'] - prev['open']) * x)

    def volume_power(x):
        return latest['volume'] >= (prev['volume'] * x)

    if 'LONG' in Config.POSITION_SIDE:
        if interval_check == '1h':
            close_prices = kline_data['close'].astype(float).tolist()
            ema60 = ema_atr.calculate_ema(prices=close_prices,period=60)[-2]
            if (latest['close'] > latest['open']) and latest['open'] > ema60 and latest['open'] <= ema60*1.0618:
                has_signal = (1, '做多')
        if interval_check == '5m':
            close_prices = kline_data['close'].astype(float).tolist()
            ema60 = ema_atr.calculate_ema(prices=close_prices,period=60)[-2]
            red_green = (latest['close'] > latest['open']) and (prev['close'] < prev['open'])
            if red_green and (latest['open'] <= ema60*1.04382) and (latest['open'] > ema60):
                has_signal = (1, '做多')
    if 'SHORT' in Config.POSITION_SIDE:
        if interval_check == '1h':
            close_prices = kline_data['close'].astype(float).tolist()
            ema60 = ema_atr.calculate_ema(prices=close_prices,period=60)[-2]
            if (latest['close'] < latest['open']) and latest['open'] < ema60 and latest['open'] >= ema60/1.0618:
                has_signal = (-1, '做空')
        if interval_check == '5m':
            close_prices = kline_data['close'].astype(float).tolist()
            ema60 = ema_atr.calculate_ema(prices=close_prices,period=60)[-2]
            red_green = (latest['close'] < latest['open']) and (prev['close'] > prev['open'])
            if red_green and (latest['open'] >= ema60/1.04382) and (latest['open'] < ema60):
                has_signal = (-1, '做空')

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
