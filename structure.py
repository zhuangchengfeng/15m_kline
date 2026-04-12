import pandas as pd
import numpy as np


def is_cross_above_boll(kline_data, lookback=20, bb_std=2.0, volume_multiplier=2):
    """
    判断 latest 或 prev 是否上穿布林带上轨，并且：
    1. latest 成交量 > prev 成交量
    2. latest 和 prev 的成交量都大于之前20根中每一根的 volume_multiplier 倍
    """
    if kline_data is None or len(kline_data) < lookback + 3:
        return False

    # 计算布林带
    ma20 = kline_data['close'].rolling(window=lookback).mean()
    std = kline_data['close'].rolling(window=lookback).std()
    bb_upper = ma20 + (std * bb_std)
    # 获取数据
    latest = kline_data.iloc[-2]
    prev = kline_data.iloc[-3]

    # 成交量历史数据（之前10根）
    volume_history = kline_data['volume'].iloc[-(12 + 3):-3].values

    # 成交量条件
    volume_increasing = latest['volume'] > prev['volume']
    volume_surge = (latest['volume'] > volume_history * volume_multiplier).all() and \
                   (prev['volume'] > volume_history * volume_multiplier).all()
    # 布林带上穿条件
    latest_bb_upper = bb_upper.iloc[-2]
    prev_bb_upper = bb_upper.iloc[-3]
    latest_cross_bb = (latest['close'] > latest_bb_upper) and (latest['open'] <= latest_bb_upper)
    prev_cross_bb = (prev['close'] > prev_bb_upper) and (prev['open'] <= prev_bb_upper) if len(
        kline_data) >= 4 else False
    cross_bb_occurred = latest_cross_bb or prev_cross_bb
    return cross_bb_occurred and volume_increasing and volume_surge


def is_cross_below_boll(kline_data, lookback=20, bb_std=2.0, volume_multiplier=2):
    """
    判断 latest 或 prev 是否下穿布林带下轨（空头用），并且：
    1. latest 成交量 > prev 成交量
    2. latest 和 prev 的成交量都大于之前20根中每一根的 volume_multiplier 倍
    """
    if kline_data is None or len(kline_data) < lookback + 3:
        return False

    # 计算布林带
    ma20 = kline_data['close'].rolling(window=lookback).mean()
    std = kline_data['close'].rolling(window=lookback).std()
    bb_lower = ma20 - (std * bb_std)  # 下轨

    # 获取数据
    latest = kline_data.iloc[-2]
    prev = kline_data.iloc[-3]

    # 成交量历史数据（之前12根，与多头保持一致）
    volume_history = kline_data['volume'].iloc[-(12 + 3):-3].values

    # 成交量条件
    volume_increasing = latest['volume'] > prev['volume']
    volume_surge = (latest['volume'] > volume_history * volume_multiplier).all() and \
                   (prev['volume'] > volume_history * volume_multiplier).all()

    # 布林带下穿条件
    latest_bb_lower = bb_lower.iloc[-2]
    prev_bb_lower = bb_lower.iloc[-3]

    # latest 下穿：开盘在上方，收盘在下方
    latest_cross_bb = (latest['close'] < latest_bb_lower) and (latest['open'] >= latest_bb_lower)

    # prev 下穿：开盘在上方，收盘在下方
    prev_cross_bb = (prev['close'] < prev_bb_lower) and (prev['open'] >= prev_bb_lower) if len(
        kline_data) >= 4 else False

    cross_bb_occurred = latest_cross_bb or prev_cross_bb

    return cross_bb_occurred and volume_increasing and volume_surge


def is_cross_above_ma20(kline_data, lookback=20):
    """
    判断 latest 或 prev 是否上穿 MA20
    上穿定义：开盘价在 MA20 下方，收盘价在 MA20 上方

    Returns:
        bool: 是否发生上穿
    """
    if kline_data is None or len(kline_data) < lookback + 2:
        return False

    # 计算 MA20
    ma20 = kline_data['close'].rolling(window=lookback).mean()

    # 获取数据
    latest = kline_data.iloc[-2]
    prev = kline_data.iloc[-3]

    latest_ma20 = ma20.iloc[-2]
    prev_ma20 = ma20.iloc[-3]

    # 判断 latest 是否上穿
    latest_cross = (latest['open'] < latest_ma20) and (latest['close'] > latest_ma20)

    # 判断 prev 是否上穿
    prev_cross = (prev['open'] < prev_ma20) and (prev['close'] > prev_ma20)

    return latest_cross or prev_cross


def is_cross_below_ma20(kline_data, lookback=20):
    """
    判断 latest 或 prev 是否下穿 MA20（空头用）
    下穿定义：开盘价在 MA20 上方，收盘价在 MA20 下方
    """
    if kline_data is None or len(kline_data) < lookback + 2:
        return False

    ma20 = kline_data['close'].rolling(window=lookback).mean()

    latest = kline_data.iloc[-2]
    prev = kline_data.iloc[-3]

    latest_ma20 = ma20.iloc[-2]
    prev_ma20 = ma20.iloc[-3]

    # 判断 latest 是否下穿
    latest_cross = (latest['open'] > latest_ma20) and (latest['close'] < latest_ma20)

    # 判断 prev 是否下穿
    prev_cross = (prev['open'] > prev_ma20) and (prev['close'] < prev_ma20)

    return latest_cross or prev_cross

def is_strong_bullish_double(klines, min_body_pct=1.0, shadow_threshold=0.5, check_lower_shadow=False):
    """
    判断是否为实体足够大、影线很短的阴K线（连续两根）

    Args:
        klines: K线列表，至少包含2根K线
        min_body_pct: 最小实体百分比（相对于开盘价），默认1%
        shadow_threshold: 影线/实体比例阈值，小于此值表示影线很短
        check_lower_shadow: 是否检查下影线
            - False: 只要求上影线短（允许有下影线）
            - True: 上下影线都要求短

    Returns:
        bool: 是否满足条件
    """
    body = []
    body_pct = 0
    total_shadow = 0
    for kline in klines:
        if kline['close'] <= kline['open']:
            return False

        # 计算实体百分比
        body.append(abs(kline['close'] - kline['open']))
        body_pct += (sum(body) / kline['open']) * 100

        # 计算上影线
        upper_shadow = kline['high'] - kline['close']
        total_shadow += upper_shadow

        # 如果需要检查下影线
        if check_lower_shadow:
            lower_shadow = kline['open'] - kline['low']
            total_shadow += lower_shadow
    # 实体必须大于最小百分比
    if body_pct < min_body_pct:
        return False

    for i in range(len(body) - 1):
        if body[i] <= body[i + 1]:
            return False


    shadow_ratio = total_shadow / sum(body)

    return shadow_ratio < shadow_threshold


def is_strong_bearish_double(klines, min_body_pct=1.0, shadow_threshold=0.35, check_upper_shadow=False):
    """
    判断是否为实体足够大、影线很短的阴K线（连续两根）

    Args:
        klines: K线列表，至少包含2根K线
        min_body_pct: 最小实体百分比（相对于开盘价），默认1%
        shadow_threshold: 影线/实体比例阈值，小于此值表示影线很短
        check_upper_shadow: 是否检查上影线
            - False: 只要求下影线短（允许有上影线）
            - True: 上下影线都要求短

    Returns:
        bool: 是否满足条件
    """
    body = []
    body_pct = 0
    total_shadow = 0

    for kline in klines:
        # 必须是阴线
        if kline['close'] >= kline['open']:
            return False

        # 计算实体
        body.append(abs(kline['close'] - kline['open']))
        body_pct += (sum(body) / kline['open']) * 100

        # 计算下影线（阴线下影线 = 收盘 - 最低）
        lower_shadow = kline['close'] - kline['low']
        total_shadow += lower_shadow

        # 如果需要检查上影线
        if check_upper_shadow:
            upper_shadow = kline['high'] - kline['open']
            total_shadow += upper_shadow

    # 实体必须大于最小百分比
    if body_pct < min_body_pct:
        return False

    # 实体必须逐级变大（空头：阴线实体越来越大，表示空头力量增强）
    for i in range(len(body) - 1):
        if body[i] <= body[i + 1]:
            return False

    shadow_ratio = total_shadow / sum(body)

    return shadow_ratio < shadow_threshold

def is_strong_bullish(kline, min_body_pct=1.0, shadow_threshold=0.25, check_lower_shadow=False):
    """
    判断是否为实体足够大、影线很短的阳K线

    Args:
        kline: K线数据（包含 open, close, high, low）
        min_body_pct: 最小实体百分比（相对于开盘价），默认1%
        shadow_threshold: 影线/实体比例阈值，小于此值表示影线很短
        check_lower_shadow: 是否检查下影线
            - False: 只要求上影线短（允许有下影线，如锤子线）
            - True: 上下影线都要求短（光头光脚阳线）

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

    # 计算上影线
    upper_shadow = kline['high'] - kline['close']
    total_shadow = upper_shadow

    # 如果需要检查下影线
    if check_lower_shadow:
        lower_shadow = kline['open'] - kline['low']
        total_shadow += lower_shadow

    shadow_ratio = total_shadow / body

    return shadow_ratio < shadow_threshold

def is_strong_bearish(kline, min_body_pct=1.0, shadow_threshold=0.25, check_upper_shadow=False):
    """
    判断是否为实体足够大、影线很短的阴K线

    Args:
        kline: K线数据（包含 open, close, high, low）
        min_body_pct: 最小实体百分比（相对于开盘价），默认1%
        shadow_threshold: 影线/实体比例阈值，小于此值表示影线很短
        check_upper_shadow: 是否检查上影线
            - False: 只要求下影线短（允许有上影线，如倒锤子线）
            - True: 上下影线都要求短（光头光脚阴线）

    Returns:
        bool: 是否满足条件
    """
    # 必须是阴线
    if kline['close'] >= kline['open']:
        return False

    # 计算实体百分比
    body = abs(kline['close'] - kline['open'])
    body_pct = (body / kline['open']) * 100

    if body_pct < min_body_pct:
        return False

    # 计算下影线
    lower_shadow = kline['close'] - kline['low']
    total_shadow = lower_shadow

    # 如果需要检查上影线
    if check_upper_shadow:
        upper_shadow = kline['high'] - kline['open']
        total_shadow += upper_shadow

    shadow_ratio = total_shadow / body

    return shadow_ratio < shadow_threshold


def check_risk_reward(kline_data, side, lookback=21, min_ratio=0.5, mode='',print_out=True):
    """
    使用 MA20（布林带中轨）判断盈亏比

    Args:
        kline_data: K线数据
        side: 'LONG' 或 'SHORT'
        lookback: 计算MA20的回溯周期，默认21
        min_ratio: 最小盈亏比
        print_out: 是否打印盈亏比信息

    Returns:
        bool: 是否满足盈亏比要求
    """
    if kline_data is None or len(kline_data) < lookback + 1:
        return False

    # 计算 MA20（收盘价的简单移动平均）
    ma20 = kline_data['close'].rolling(window=lookback).mean()

    latest = kline_data.iloc[-2]
    current = latest['close']
    ma20_value = ma20.iloc[-2]  # 对应 latest 的 MA20 值

    # 最近 lookback 根K线的最高点和最低点（用于计算目标位）
    recent_klines = kline_data.iloc[-lookback - 1:-1]
    highest = recent_klines['close'].max()
    lowest = recent_klines['close'].min()

    if side == 'LONG':
        # 目标位：前高（highest）
        # 止损位：MA20（中轨）

        # 如果当前价已经高于目标位，直接通过
        if current >= highest:
            if print_out:
                print(f"✅ 已超过目标位 {highest}")
            return True

        # 如果当前价已经低于 MA20（止损位），不应该做多
        if current <= ma20_value:
            if print_out:
                print(f"❌ 当前价 {current} 已低于 MA20 {ma20_value:.4f}，不适合做多")
            return False

        upside = (highest - current) / current  # 上涨空间（到前高）
        downside = (current - ma20_value) / current  # 下跌空间（到 MA20）

        if downside <= 0:
            return False

        ratio = upside / downside

        if print_out:
            print(f"📊 做多盈亏比: {ratio:.2f} | 上涨空间: {upside * 100:.2f}% | 下跌空间: {downside * 100:.2f}%")
            print(f"   当前价: {current:.4f} | MA20(止损): {ma20_value:.4f} | 目标(前高): {highest:.4f}")

    else:  # SHORT
        # 目标位：前低（lowest）
        # 止损位：MA20（中轨）

        # 如果当前价已经低于目标位，直接通过
        if current <= lowest:
            if print_out:
                print(f"✅ 已低于目标位 {lowest}")
            return True

        # 如果当前价已经高于 MA20（止损位），不应该做空
        if current >= ma20_value:
            if print_out:
                print(f"❌ 当前价 {current} 已高于 MA20 {ma20_value:.4f}，不适合做空")
            return False

        downside = (current - lowest) / current  # 下跌空间（到前低）
        upside = (ma20_value - current) / current  # 上涨空间（到 MA20）

        if upside <= 0:
            return False

        ratio = downside / upside

        if print_out:
            print(f"📊 做空盈亏比: {ratio:.2f} | 下跌空间: {downside * 100:.2f}% | 上涨空间: {upside * 100:.2f}%")
            print(f"   当前价: {current:.4f} | MA20(止损): {ma20_value:.4f} | 目标(前低): {lowest:.4f}")

    if mode =='rg_gr':
        return (ratio >= min_ratio or ratio <=0.2)
    return ratio >= min_ratio

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

