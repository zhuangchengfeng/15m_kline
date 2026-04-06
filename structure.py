import pandas as pd
import numpy as np


def is_strong_bullish(kline, min_body_pct=1.0, shadow_threshold=0.25):
    """
    判断是否为实体足够大、影线很短的阳K线

    Args:
        kline: K线数据（包含 open, close, high, low）
        min_body_pct: 最小实体百分比（相对于开盘价），默认1%
        shadow_threshold: 影线/实体比例阈值，小于此值表示影线很短

    Returns:
        bool: 是否满足条件
    """
    # 必须是阳线
    if kline['close'] <= kline['open']:
        return False

    # 计算实体百分比
    body = abs(kline['close'] - kline['open'])
    body_pct = (body / kline['open']) * 100

    # 实体必须大于最小百分比
    if body_pct < min_body_pct:
        return False

    # 计算影线比例
    upper_shadow = kline['high'] - kline['close']  # 阳线上影线 = 最高 - 收盘
    lower_shadow = kline['open'] - kline['low']  # 阳线下影线 = 开盘 - 最低
    total_shadow = upper_shadow + lower_shadow

    shadow_ratio = total_shadow / body

    # 影线必须很短
    return shadow_ratio < shadow_threshold

def is_morning_star(kline_data, doji_ratio=0.25, position=-2):
    """
    判断最后三根K线是否为希望之星
    :param kline_data: DataFrame，包含open,high,low,close
    :param doji_ratio: 星线实体占整个K线范围的最大比例
    :param position: K线位置索引，默认-1表示最新K线
    :return: bool
    """
    if len(kline_data) < 3:
        return False

    # 定位三根K线
    idx = position
    latest = kline_data.iloc[idx]
    prev = kline_data.iloc[idx - 1]
    extra_prev = kline_data.iloc[idx - 2]

    # 第一根阴线
    if extra_prev['close'] >= extra_prev['open']:
        return False

    # 第三根阳线
    if latest['close'] <= latest['open']:
        return False

    # 第二根星线（实体小）
    body_prev = abs(prev['close'] - prev['open'])
    range_prev = prev['high'] - prev['low']
    if range_prev == 0 or body_prev > doji_ratio * range_prev:
        return False

    # 第三根阳线深入第一根阴线实体
    first_black_open = extra_prev['open']
    first_black_close = extra_prev['close']
    # 取阴线实体的60%位置（可调整）
    penetration_level = first_black_open - (first_black_open - first_black_close) * 0.5
    if latest['close'] <= penetration_level:
        return False

    return True


def is_evening_star(kline_data, doji_ratio=0.25, penetration_depth=0.5, position=-2):
    """
    判断最后三根K线是否为黄昏之星（顶部反转）

    :param kline_data: DataFrame，包含open,high,low,close
    :param doji_ratio: 星线实体占整个K线范围的最大比例（默认0.3）
    :param penetration_depth: 第三根阴线深入第一根阳线实体的比例（默认0.5，即1/2）
    :param position: K线位置索引，默认-1表示最新K线
    :return: bool
    """
    if len(kline_data) < 3:
        return False

    # 定位三根K线（从旧到新：extra_prev -> prev -> latest）
    idx = position
    latest = kline_data.iloc[idx]  # 第三根：最新K线（应为阴线）
    prev = kline_data.iloc[idx - 1]  # 第二根：星线（实体小）
    extra_prev = kline_data.iloc[idx - 2]  # 第一根：阳线

    # 1. 第一根是阳线（上涨延续）
    if extra_prev['close'] <= extra_prev['open']:
        return False

    # 2. 第三根是阴线（下跌确认）
    if latest['close'] >= latest['open']:
        return False

    # 3. 第二根是星线（实体小）
    body_prev = abs(prev['close'] - prev['open'])
    range_prev = prev['high'] - prev['low']
    if range_prev == 0 or body_prev > doji_ratio * range_prev:
        return False

    # 4. 第三根阴线需要深入第一根阳线的实体
    first_white_open = extra_prev['open']  # 第一根开盘价（较低）
    first_white_close = extra_prev['close']  # 第一根收盘价（较高）

    # 计算深入位置（从顶部往下算）
    # 例如：阳线实体范围 = first_white_close - first_white_open
    # penetration_level = first_white_close - (实体范围 * 深入比例)
    penetration_level = first_white_close - (first_white_close - first_white_open) * penetration_depth

    # 阴线收盘价应该低于深入位置（即跌破了阳线实体的指定比例）
    if latest['close'] >= penetration_level:
        return False

    return True

def rma(src, length):
    """
    实现 TradingView 的 RMA (移动平均)
    RMA 是 Wilder 平滑，相当于 alpha = 1/length 的指数平均

    :param src: 输入数据序列
    :param length: 周期
    :return: RMA 序列
    """
    alpha = 1.0 / length
    rma_values = np.full_like(src, np.nan, dtype=np.float64)

    # 第一个值用 SMA 填充
    if len(src) >= length:
        rma_values[length - 1] = np.mean(src[:length])

    # 递归计算后续值
    for i in range(length, len(src)):
        rma_values[i] = alpha * src[i] + (1 - alpha) * rma_values[i - 1]

    return rma_values


def calculate_rsi(kline_data, column='close', period=6, position=-1):
    """
    按照 TradingView 的方式计算 RSI6
    使用 RMA 加权平均，完全对齐 TradingView 的 ta.rsi(close, 6)

    :param kline_data: DataFrame，包含价格数据
    :param column: 用于计算的列名，默认'close'
    :param period: RSI周期，默认6
    :param position: 获取哪个位置的RSI，默认-1表示最新值
    :return: 指定位置的RSI值，如果没有足够数据返回None
    """
    if len(kline_data) < period + 1:
        return None

    # 获取价格序列
    src = kline_data[column].values

    # 计算上涨和下跌
    # u = math.max(x - x[1], 0)
    # d = math.max(x[1] - x, 0)
    changes = np.diff(src)
    u = np.where(changes > 0, changes, 0)
    d = np.where(changes < 0, -changes, 0)

    # 在序列开头补一个0，使长度与src一致
    u = np.concatenate([[0], u])
    d = np.concatenate([[0], d])

    # 计算 RMA(u, period) 和 RMA(d, period)
    rma_u = rma(u, period)
    rma_d = rma(d, period)

    # 计算 RS 和 RSI
    # rs = ta.rma(u, y) / ta.rma(d, y)
    # res = 100 - 100 / (1 + rs)
    rsi_values = np.full_like(src, np.nan)

    for i in range(len(src)):
        if np.isnan(rma_u[i]) or np.isnan(rma_d[i]) or rma_d[i] == 0:
            if rma_d[i] == 0 and not np.isnan(rma_u[i]):
                rsi_values[i] = 100.0  # 没有下跌
            continue

        rs = rma_u[i] / rma_d[i]
        rsi_values[i] = 100 - 100 / (1 + rs)

    # 返回指定位置的值
    if position < 0:
        position = len(rsi_values) + position

    if position < 0 or position >= len(rsi_values):
        return None

    return rsi_values[position]

