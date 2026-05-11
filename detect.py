# detect.py
import logging
import time
from config import Config
from ema_atr_manager import EmaAtrManager
import config as cf
import structure
import smc   #付费5USDT使用包 VX：Tugzcf
import numpy as np
import pandas as pd
ema_atr = EmaAtrManager()
logger = logging.getLogger(__name__)

import numpy as np
import pandas as pd

def has_pressure_aging(short_open_times, short_prices, latest, hours: int) -> bool:
    """
    检查是否存在满足条件的短吞没形态（价格 + 时间）

    Args:
        short_open_times: numpy array或list，吞没形态下一根K线的开盘时间（毫秒时间戳）
        short_prices: numpy array或list，吞没形态的收盘价
        latest_close: 最新K线的收盘价（float）
        latest_open_time: 最新K线的开盘时间（毫秒时间戳，int）
        hours: 小时数（例如12表示12小时）

    Returns:
        bool: 存在至少一个满足条件的形态返回True，否则False
    """
    offset_ms = hours * 3600 * 1000  # 小时转毫秒
    latest_close = latest['close']
    latest_open_time = latest['open_time']
    price_cond = np.array(short_prices) > latest_close
    time_cond = (np.array(short_open_times) + offset_ms) > latest_open_time
    return np.any(price_cond & time_cond)


def detect_signal(interval_check, result: dict, all_periods_data=None) -> list:
    """
    检测形态并可选地记录信号

    Args:
        interval_check: '1h' '15m' '1d' '4h'
        result: 某个品种symbol的K线数据 DICT
        all_periods_data:所有品种所有周期数据
        all_periods_data = {
            '1m': [
                {'symbol': 'BTCUSDT', 'data': DataFrame_1m_BTC, 'success': True},
                {'symbol': 'ETHUSDT', 'data': DataFrame_1m_ETH, 'success': True}
            ],
            '1w': [
                {'symbol': 'BTCUSDT', 'data': DataFrame_1w_BTC, 'success': True},
                {'symbol': 'ETHUSDT', 'data': None, 'success': False}
            ]
        }
    Returns:
        tuple: 是否有信号 (1/-1, 文本) 或 (0, None)
    """
    has_signal = (0, None)
    symbol = result['symbol']
    # print(symbol)
    # print(all_periods_data)
    kline_data = result['data']
    target_dict_1h = next((d for d in all_periods_data.get('1h') if d.get('symbol') == symbol), None)
    target_dict_4h = next((d for d in all_periods_data.get('4h') if d.get('symbol') == symbol), None)
    data_1h = target_dict_1h.get('data')
    data_4h = target_dict_4h.get('data')
    if data_1h is not None and data_4h is not None:
        pass
    else:
        return has_signal
    required_len = Config.get_kline_limit(interval_check)
    if len(kline_data) < required_len :
        return (0, None)

    def price_power(x):
        return abs(latest['close'] - latest['open']) > (abs(prev['close'] - prev['open']) * x)

    def volume_power(x):
        return latest['volume'] >= (prev['volume'] * x)
    # ========== 多头（LONG） ==========
    if 'LONG' in Config.POSITION_SIDE:
        # 周线信号
        if interval_check == '1w':
            current = kline_data.iloc[-1]
            week_check = current['close'] > current['open']

            # 计算前4根实体百分比之和
            last_4_bars = kline_data.iloc[-5:-1]
            entity_pct = (last_4_bars['close'] - last_4_bars['open']) / last_4_bars['open'] * 100
            entity_sum_pct = entity_pct.sum()

            # 根据entity_sum_pct判断条件
            condition_met = False

            if entity_sum_pct >= 50:
                # 直接返回False
                condition_met = False
            elif 25 <= entity_sum_pct < 50:
                # 当前实体百分比 < 3%
                current_body = abs(current['close'] - current['open']) / current['open'] * 100
                if current_body < 3:
                    condition_met = True
            elif 12.5 <= entity_sum_pct < 25:
                # 当前实体百分比 < 2%
                current_body = abs(current['close'] - current['open']) / current['open'] * 100
                if current_body < 2:
                    condition_met = True
            elif entity_sum_pct < 12.5:
                # 当前实体百分比 < 1%
                current_body = abs(current['close'] - current['open']) / current['open'] * 100
                if current_body < 1:
                    condition_met = True

            # 最终判断：week_check为True 且 condition_met为True时才做多
            if week_check or condition_met:
                return [1, '做多', '']
            else:
                return has_signal
        if interval_check =='4h':
            return [1,'做多','']

        if interval_check =='1h':
            return [1, '做多','']

        if interval_check == '15m':
            latest = kline_data.iloc[-2]  # 最新已完成的15m K线
            prev = kline_data.iloc[-3]
            engulf_prices_15m = smc.get_engulfing_prices(kline_data)

            # 获取1h的价格数组
            kline_1h = data_1h  #复制防止修改原数据
            kline_4h = data_4h  #复制防止修改原数据
            # 获取1h的价格（看涨价格放long，看跌价格放short）
            engulf_prices_1h = smc.get_engulfing_prices(kline_1h)
            engulf_1h_data = smc.get_engulfing_prices_with_moreinfo(kline_1h)

            engulf_prices_4h = smc.get_engulfing_prices(kline_4h)
            # engulf_4h_data = smc.get_engulfing_prices_with_indices(kline_4h)

            short_open_time_series = engulf_1h_data['short']['next_open_times']
            short_prices = engulf_1h_data['short']['prices']

            close_prices = kline_data['close'].astype(float).tolist()
            ema_list = ema_atr.calculate_ema(prices=close_prices, period=60)
            ema60 = ema_list[-2]

            ema_filiter_list = ema_atr.calculate_ema(prices=close_prices, period=12)
            ema12_filter_price = ema_filiter_list[-1]
            filter_engulf_price_1h = engulf_prices_1h['long'][engulf_prices_1h['long'] <= ema12_filter_price]
            filter_engulf_price_4h = engulf_prices_4h['long'][engulf_prices_4h['long'] <= ema12_filter_price]
            pierce_ema = smc.check_pierce_engulfing(latest,np.array([ema60]) , mode='long')
            pierce_1h_smc = smc.check_pierce_engulfing(latest, filter_engulf_price_1h, mode='long')
            pierce_4h_smc = smc.check_pierce_engulfing(latest, filter_engulf_price_4h, mode='long')

            if pierce_ema and not has_pressure_aging(short_open_time_series, short_prices, latest, 12):
                lower_shadow = min(latest['open'], latest['close']) - latest['low']
                upper_shadow = latest['high'] - max(latest['open'], latest['close'])
                entity_1_3 = abs(latest['open'] - latest['close']) / 3
                low_zone = structure.is_price_at_low_zone(kline_data, lookback=8, rank_threshold=2, iloc=[-2])
                if (lower_shadow + entity_1_3 > upper_shadow) and low_zone:  # 下影线 > 上影线
                        return [1, '做多', '15m_pierce_ema']

            if pierce_1h_smc:
                lower_shadow = min(latest['open'], latest['close']) - latest['low']
                upper_shadow = latest['high'] - max(latest['open'], latest['close'])
                entity_1_3 = abs(latest['open']-latest['close'])/3
                low_zone = structure.is_price_at_low_zone(kline_data, lookback=4, rank_threshold=1, iloc=[-2])
                if (lower_shadow+entity_1_3 > upper_shadow) and low_zone:  # 下影线 > 上影线
                    return [1, '做多', '15m_pierce1h']

            if pierce_4h_smc:
                lower_shadow = min(latest['open'], latest['close']) - latest['low']
                upper_shadow = latest['high'] - max(latest['open'], latest['close'])
                entity_1_3 = abs(latest['open']-latest['close'])/3
                low_zone = structure.is_price_at_low_zone(kline_data, lookback=4, rank_threshold=1, iloc=[-2])
                if (lower_shadow+entity_1_3 > upper_shadow) and low_zone:  # 下影线 > 上影线
                    return [1, '做多', '15m_pierce4h']

            red_green = (latest['close'] > latest['open']) and (prev['close'] < prev['open'])
            if red_green:
                if price_power(1):
                    low_zone = structure.is_price_at_low_zone(kline_data,lookback=5, rank_threshold=2, iloc=[-2])
                    if low_zone:
                        break_1h = smc.check_break_engulfing(prev, latest, filter_engulf_price_1h)
                        if break_1h:
                            return [1, '做多', '_15m_2break']

            if price_power(3):
                break_1h = (smc.check_break_engulfing(prev, latest, filter_engulf_price_1h)
                            or smc.check_break_engulfing(kline_data.iloc[-4], latest, filter_engulf_price_1h,k_form='hope_star')
                            or smc.check_break_engulfing(kline_data.iloc[-4],latest,np.array([ema60]),k_form='hope_star'))
                if break_1h:
                    return [1, '做多', '_15m_hopestar']
        return has_signal