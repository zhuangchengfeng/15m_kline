# detect.py
import pandas as pd
import logging
from datetime import datetime, timezone, timedelta
from config import Config
from ema_atr_manager import EmaAtrManager

ema_atr = EmaAtrManager()
logger = logging.getLogger(__name__)

# 设置北京时区
BEIJING_TZ = timezone(timedelta(hours=8))
UTC_TZ = timezone.utc




def detect_signal(interval_check, result: dict) -> bool:
    """
    检测形态并可选地记录信号

    Args:
        kline_data: K线数据
        symbol: 交易对
        record_signal: 是否记录信号
        check_duplicate: 是否检查重复

    Returns:
        bool: 是否有信号
    """
    kline_data = result['data']
    kline_data:pd.DataFrame
    if kline_data is None or len(kline_data) < Config.KLINE_LIMIT:
        return False
    current = kline_data.iloc[-1]
    prev = kline_data.iloc[-3]  # 前一根K线
    latest = kline_data.iloc[-2]  # 最新K线
    extra_prev = kline_data.iloc[-4]
    extra_prev_2 = kline_data.iloc[-5]

    atrdiffemacheck = ema_atr.run(symbol=result['symbol'],klines=kline_data,interval_check=interval_check)
    has_signal = False

    def price_power(x):
        return abs(latest['close'] - latest['open']) > (abs(prev['close'] - prev['open']) * x)

    def volume_power(x):
        return latest['volume'] >= (prev['volume'] * x)

    if interval_check == '15m':
        c = (latest['close'] > latest['open']) and (prev['close'] < prev['open']) and price_power(0.618)
        if c and atrdiffemacheck:
            has_signal = True

    if interval_check == '1h':
        c = (latest['low'] > prev['low']) and (latest['high'] > prev['high']) and (latest['close'] > latest['open'])
        # cc = (current['low'] < latest['low']) and (current['low'] < prev['low']) and (current['low'] < extra_prev['low'])
        # d = (latest['high']-latest['close']) < (latest['close']-latest['low']) * 1
        e = (latest['low'] <= extra_prev['high'])
        f = (latest['close'] > latest['open']) and (prev['close'] < prev['open'])
        if e and c and f and atrdiffemacheck:
            has_signal = True
        # if (c or cc) and d and e:
        #     has_signal = True

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
