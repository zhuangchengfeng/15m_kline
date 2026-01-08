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

import pandas as pd
import numpy as np


def detect_rg_pattern_signals(df, close_col='close', open_col='open', low_col='low'):
    """
    检测RED_GREEN_K线组合信号

    规则：
    1. 寻找阴阳K线组合（当前为阴线，前一根为阳线）
    2. 当发现一个阴阳组合时，向前查找最近的一个阴阳组合
    3. 如果之前的阴线最低点 > 当前阴线最低点，产生信号

    参数：
    df: DataFrame，包含OHLC数据
    close_col: 收盘价列名
    open_col: 开盘价列名
    low_col: 最低价列名

    返回：
    signals: 包含信号的DataFrame
    """

    # 复制数据避免修改原数据
    df = df.copy()

    # 确保数据按时间升序排列（旧数据在前，新数据在后）
    df = df.sort_values('open_time').reset_index(drop=True)

    # 判断K线阴阳（True为阳线，False为阴线）
    df['is_yang'] = df[close_col] > df[open_col]

    # 找出阴阳组合：
    df['is_yin_yang_pattern'] = (df['is_yang']) & (~df['is_yang']).shift(1)
    # 找出所有阴阳组合的位置
    pattern_indices = df[df['is_yin_yang_pattern']].index.tolist()
    # 初始化信号列
    df['signal'] = 0  # 0表示无信号，1表示有信号
    df['prev_pattern_low'] = np.nan  # 记录前一个模式的最低点
    df['current_pattern_low'] = np.nan  # 记录当前模式的最低点

    if len(pattern_indices) >= 2:
        # 只取最后两个索引
        prev_idx = pattern_indices[-2]-1  # 倒数第二个模式
        current_idx = pattern_indices[-1]-1  # 最后一个模式（最新的）

        prev_low = df.loc[prev_idx, low_col]
        current_low = df.loc[current_idx, low_col]
        # 判断条件
        if prev_low < current_low:
            return True
        else:
            return False
    else:
        return False





def detect_signal(interval_check, result: dict) -> bool:
    """
    检测形态并可选地记录信号

    Args:
        interval_check:'1h' '15m' '1d' '4h'
        result: K线数据 DICT
        symbol: 交易对
    Returns:
        bool: 是否有信号
    """
    kline_data = result['data']
    kline_data:pd.DataFrame
    if kline_data is None or len(kline_data) < Config.KLINE_LIMIT and interval_check != '1d':
        return False
    current = kline_data.iloc[-1]
    prev = kline_data.iloc[-3]  # 前一根K线
    latest = kline_data.iloc[-2]  # 最新K线
    extra_prev = kline_data.iloc[-4]
    extra_prev_2 = kline_data.iloc[-5]

    r_g_p = detect_rg_pattern_signals(kline_data)
    atrdiffemacheck = ema_atr.run(symbol=result['symbol'],klines=kline_data,interval_check=interval_check)

    has_signal = False

    def price_power(x):
        return abs(latest['close'] - latest['open']) > (abs(prev['close'] - prev['open']) * x)

    def volume_power(x):
        return latest['volume'] >= (prev['volume'] * x)

    # if interval_check == '15m':
    #     c = (latest['close'] > latest['open']) and (prev['close'] < prev['open']) and price_power(0.618)
    #     if c and atrdiffemacheck:
    #         has_signal = True

    if interval_check == '1h':
        # c = (latest['low'] > prev['low']) and (latest['high'] > prev['high']) and (latest['close'] > latest['open'])
        # cc = (current['low'] < latest['low']) and (current['low'] < prev['low']) and (current['low'] < extra_prev['low'])
        # d = (latest['high']-latest['close']) < (latest['close']-latest['low']) * 1
        # e = (latest['low'] <= extra_prev['high'])
        f = (latest['close'] > latest['open']) and (prev['close'] < prev['open'])
        if r_g_p and atrdiffemacheck and price_power(1.3) and f:
            has_signal = True

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
