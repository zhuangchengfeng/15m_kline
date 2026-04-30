# detect.py
import logging
from config import Config
from ema_atr_manager import EmaAtrManager
import config as cf
import structure
import smc   #付费5USDT使用包 VX：Tugzcf
import numpy as np
ema_atr = EmaAtrManager()
logger = logging.getLogger(__name__)



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

    required_len = Config.get_kline_limit(interval_check)
    if kline_data is None or len(kline_data) < required_len:
        return (0, None)

    def price_power(x):
        return abs(latest['close'] - latest['open']) > (abs(prev['close'] - prev['open']) * x)

    def volume_power(x):
        return latest['volume'] >= (prev['volume'] * x)
    # 长影线阈值：影线长度占整根K线长度的比例
    # ========== 多头（LONG） ==========
    if 'LONG' in Config.POSITION_SIDE:
        # 周线信号：当前K线为阳线
        if interval_check == '1w':
            current = kline_data.iloc[-1]
            if current['close'] > current['open']:
                return [1, '做多','1w_']
        if interval_check =='1h':
            return [1, '做多','1h_pass_']
        if interval_check == '15m':
            latest = kline_data.iloc[-2]  # 最新已完成的15m K线
            prev = kline_data.iloc[-3]
            engulf_prices_15m = smc.get_engulfing_prices(kline_data)

            # 获取1h的吞没价格数组
            if target_dict_1h is not None and target_dict_1h.get('data') is not None:
                kline_1h = target_dict_1h['data']
                # 获取1h的吞没价格（看涨价格放long，看跌价格放short）
                engulf_prices_1h = smc.get_engulfing_prices(kline_1h)
                engulf_data = smc.get_engulfing_prices_with_indices(kline_1h)
                long_prices = engulf_data['long']['prices']
                long_indices = engulf_data['long']['indices']
                lower, upper = smc.find_nearest_bounds(latest['close'], long_prices)
                if lower is not None and upper is not None:
                    idx_candidates = long_indices[long_prices == upper]
                    target_idx = idx_candidates[-1]  # 取最新的那个吞没K线
                elif lower is not None and upper is None:
                    # 15m收盘价高于所有历史吞没价格 → 视为强势突破（无假突破过滤）
                    target_idx = None
                    pass
                elif lower is None and upper is not None:
                    # 15m收盘价低于所有历史吞没价格 → 下方无支撑，可能深跌，可按空头逻辑处理
                    return has_signal
                else:
                    return has_signal
            else:
                return has_signal

            pierce = smc.check_pierce_engulfing(latest, engulf_prices_1h['long'], mode='long')
            if pierce:
                low_zone = structure.is_price_at_low_zone(kline_data, lookback=4, rank_threshold=1, iloc=[-2])
                if low_zone:
                    fake_break = smc.check_fake_break_upward(kline_1h, target_idx, upper, min_confirm_bars=6)
                    if not fake_break:
                    # 其它辅助条件：阶段低点等
                        return [1, '做多', '15m_2_']

            red_green = (latest['close'] > latest['open']) and (prev['close'] < prev['open'])
            if red_green:
                if price_power(1):
                    low_zone = structure.is_price_at_low_zone(kline_data,lookback=4, rank_threshold=1, iloc=[-2])
                    if low_zone:
                        break_15m = smc.check_break_engulfing(prev, latest, engulf_prices_15m['long'])
                        break_1h = smc.check_break_engulfing(prev, latest, engulf_prices_1h['long'])
                        if break_15m and break_1h:
                            return [1, '做多', '_15m_2break_1h_and']

            if price_power(3): #23:38:13 - INFO -   API3USDT L ... [1] 1w_1h_pass_15m_2_ | PENDLEUSDT L .
                break_15m = smc.check_break_engulfing(prev, latest, engulf_prices_15m['long']) or smc.check_break_engulfing(kline_data.iloc[-4], latest, engulf_prices_15m['long'])
                break_1h = smc.check_break_engulfing(prev, latest, engulf_prices_1h['long']) or smc.check_break_engulfing(kline_data.iloc[-4], latest, engulf_prices_1h['long'])
                if break_15m and break_1h:
                    return [1, '做多', '_15m_hopestar_1h_and']
        return has_signal