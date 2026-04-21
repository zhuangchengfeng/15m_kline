# detect.py
import logging
from config import Config
from ema_atr_manager import EmaAtrManager
import config as cf
import structure
import smc   #付费使用包 VX：Tugzcf
ema_atr = EmaAtrManager()
logger = logging.getLogger(__name__)



def detect_signal(interval_check, result: dict, all_periods_data=None) -> tuple:
    """
    检测形态并可选地记录信号

    Args:
        interval_check: '1h' '15m' '1d' '4h'
        result: K线数据 DICT
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
    kline_data = result['data']
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
                return (1, '做多')
        # 15分钟信号：最新K线具有很长的下影线
        if interval_check == '15m':
            latest = kline_data.iloc[-2]   # 最新已完成的K线
            prev = kline_data.iloc[-3]

            close_prices = kline_data['close'].astype(float).tolist()
            ema60 = ema_atr.calculate_ema(prices=close_prices, period=60)[-2]
            # 计算实体长度和下影线长度
            body = abs(latest['close'] - latest['open'])
            lower_shadow = min(latest['open'], latest['close']) - latest['low']
            # 分支1：强下影线 + 穿刺 + 阶段低点
            if body < lower_shadow or (price_power(1) and volume_power(1)):
                if smc.detect_engulfing_pierce(kline_data,logic_mode='shadow')[0]:
                    low_zone = structure.is_price_at_low_zone(kline_data,lookback=4, rank_threshold=1, iloc=[-2,-3])  #经历了至少一小时的回调，阶段低点
                    if low_zone:
                        return (1, '做多')

            # 分支2：站上EMA60 + 实体突破看跌吞没阻力
            if latest['close'] >= ema60:
                if smc.detect_engulfing_pierce(kline_data,logic_mode='body')[0]:
                    return (1, '做多')

            # 分支3：站上EMA60 + 阴阳转换 + 回踩 + 上方无压力位 + 低位回调  （捕捉单边）
    # ========== 空头（SHORT） ==========
    if 'SHORT' in Config.POSITION_SIDE:
        # 周线信号：当前K线为阴线
        if interval_check == '1w':

            current = kline_data.iloc[-1]
            if current['close'] < current['open']:
                return (-1, '做空')

        # 15分钟信号：最新K线具有很长的上影线
        if interval_check == '15m':
            latest = kline_data.iloc[-2]  # 最新已完成的K线
            prev = kline_data.iloc[-3]

            close_prices = kline_data['close'].astype(float).tolist()
            ema60 = ema_atr.calculate_ema(prices=close_prices, period=60)[-2]

            # 计算实体长度和上影线长度
            body = abs(latest['close'] - latest['open'])
            upper_shadow = latest['high'] - max(latest['open'], latest['close'])

            # 分支1：强上影线 + 空头穿刺 + 阶段高点
            if body < upper_shadow or (price_power(1) and volume_power(1)):
                # 空头影线穿刺：使用 detect_engulfing_pierce 的第二个返回值（看跌穿刺）
                if smc.detect_engulfing_pierce(kline_data, logic_mode='shadow')[1]:
                    high_zone = structure.is_price_at_high_zone(kline_data, lookback=4, rank_threshold=1, iloc=[-2, -3])
                    if high_zone:
                        return (-1, '做空')

            # 分支2：跌破EMA60 + 实体突破看涨吞没支撑（空头使用 body 模式的第二个返回值）
            if latest['close'] <= ema60:
                if smc.detect_engulfing_pierce(kline_data, logic_mode='body')[1]:
                    return (-1, '做空')

    return has_signal