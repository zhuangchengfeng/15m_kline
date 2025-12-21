# detect.py
import pandas as pd
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# 设置北京时区
BEIJING_TZ = timezone(timedelta(hours=8))
UTC_TZ = timezone.utc

# 导入信号记录器
try:
    from signal_recorder import SignalRecorder

    signal_recorder = SignalRecorder()
    RECORDER_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("SignalRecorder未找到，信号将不会被记录")
    RECORDER_AVAILABLE = False


def detect_signal(kline_data: pd.DataFrame, symbol: str = None,
                  record_signal: bool = True, check_duplicate: bool = True) -> bool:
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
    if kline_data is None or len(kline_data) < 5:
        return False

    prev = kline_data.iloc[-3]  # 前一根K线
    latest = kline_data.iloc[-2]  # 最新K线
    extra_prev = kline_data.iloc[-4]
    extra_prev_2 = kline_data.iloc[-5]
    open_price = float(latest['close'])

    def price_power(x):
        return abs(latest['close'] - latest['open']) > (abs(prev['close'] - prev['open']) * x)

    def volume_power(x):
        return latest['volume'] >= (prev['volume'] * x)

    signal_type = None
    has_signal = False

    # 检测a形态 三阴接一阳 且阳线大于2倍阴线
    a = (extra_prev_2['close'] < extra_prev_2['open']) \
        and (extra_prev['close'] < extra_prev['open']) \
        and (prev['close'] < prev['open']) \
        and (latest['close'] > latest['open']) \
        and price_power(2)

    if a:
        signal_type = '超跌反弹'
        has_signal = True

    # 检测b形态  阴阳阴阳
    b = (extra_prev_2['close'] < extra_prev_2['open']) \
        and (extra_prev['close'] > extra_prev['open']) \
        and (prev['close'] < prev['open']) \
        and (latest['close'] > latest['open']) \
        and price_power(1.5) \
        and volume_power(1.5)

    if b:
        signal_type = '2B'
        has_signal = True

    # 检测c形态  追涨形态
    c = price_power(2) and volume_power(2.5) and (latest['close'] > latest['open']) and (prev['close'] > prev['open'])

    if c:
        signal_type = '追涨'
        has_signal = True

    # 如果有信号且需要记录
    if has_signal and symbol and record_signal and RECORDER_AVAILABLE:
        try:
            # 获取开仓价格（使用latest['close']）

            # 获取当前K线的open_time（当前正在运行的K线的开始时间）
            # kline_data.iloc[-1] 是当前正在运行的K线
            current_kline = kline_data.iloc[-1]

            # 转换时间戳为北京时间
            # 币安K线数据中的open_time是毫秒时间戳（Unix毫秒）
            timestamp_ms = current_kline['open_time']

            # 转换为秒（保留小数）
            timestamp_seconds = timestamp_ms / 1000.0

            # 创建UTC时间
            utc_time = datetime.fromtimestamp(timestamp_seconds, tz=UTC_TZ)

            # 转换为北京时间
            beijing_time = utc_time.astimezone(BEIJING_TZ)

            # 格式化为字符串
            time_str = beijing_time.strftime("%Y/%m/%d %H:%M:%S")

            # 调试信息：打印时间转换结果
            logger.debug(f"时间转换: timestamp_ms={timestamp_ms}, "
                         f"UTC={utc_time.strftime('%Y/%m/%d %H:%M:%S')}, "
                         f"Beijing={time_str}")

            # 记录信号（返回是否成功）
            success, message = signal_recorder.add_signal(
                symbol=symbol,
                signal_type=signal_type,
                open_price=open_price,
                time_str=time_str,  # 使用K线开始时间的北京时间
                check_duplicate=check_duplicate
            )

            if not success:
                # 记录重复信号信息
                logger.debug(f"重复信号: {message}")
            else:
                # 记录成功信息
                logger.info(f"✅ 记录信号: {symbol} {signal_type} 时间: {time_str} 价格: {open_price}")

        except Exception as e:
            logger.error(f"❌ 记录信号失败: {e}")
            # 调试信息：打印异常详情
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")

            # 如果时间转换失败，尝试使用当前时间作为备选
            try:
                backup_time_str = datetime.now(BEIJING_TZ).strftime("%Y/%m/%d %H:%M:%S")
                logger.warning(f"使用备选时间: {backup_time_str}")

                # 使用当前时间重新尝试记录
                success, message = signal_recorder.add_signal(
                    symbol=symbol,
                    signal_type=signal_type,
                    open_price=open_price,
                    time_str=backup_time_str,
                    check_duplicate=check_duplicate
                )

                if success:
                    logger.info(f"✅ 使用备选时间记录成功: {symbol}")

            except Exception as e2:
                logger.error(f"❌ 备选时间记录也失败: {e2}")

    return has_signal


def get_recent_signals(symbol: str, hours: int = 24):
    """
    获取指定symbol最近N小时的信号

    Args:
        symbol: 交易对
        hours: 小时数

    Returns:
        List: 信号列表
    """
    if RECORDER_AVAILABLE:
        return signal_recorder.get_recent_signals(symbol, hours)
    return []


def clear_old_signals(days: int = 7):
    """清理指定天数前的信号"""
    if RECORDER_AVAILABLE:
        signal_recorder.clear_old_signals(days)


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