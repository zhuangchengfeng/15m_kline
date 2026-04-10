from binance.um_futures import UMFutures
import datetime
import pandas as pd

client = UMFutures(proxies={
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
})


def get_24h_volume_by_15min(symbol: str, end_time: datetime.datetime):
    """
    获取指定时间点前24小时的15分钟K线累计成交额

    Args:
        symbol: 交易对，例如 'BTCUSDT'
        end_time: 结束时间（北京时间或UTC时间），例如 datetime.datetime(2026, 4, 9, 18, 15, 0)

    Returns:
        dict: {
            'symbol': 交易对,
            'end_time': 结束时间,
            'start_time': 开始时间（24小时前）,
            'total_volume': 累计成交额,
            'kline_count': K线数量
        }
    """

    # 确保时间带时区信息（转换为UTC，因为币安API使用UTC时间）
    if end_time.tzinfo is None:
        # 如果没有时区信息，假设是北京时间
        beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
        end_time = end_time.replace(tzinfo=beijing_tz)

    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))

    # 转换为UTC时间
    end_time_utc = end_time.astimezone(beijing_tz)
    # 计算24小时前的时间
    start_time_utc = end_time_utc - datetime.timedelta(hours=24)
    # 转换为毫秒时间戳
    end_timestamp_ms = int(end_time_utc.timestamp() * 1000)
    start_timestamp_ms = int(start_time_utc.timestamp() * 1000)

    print(f"查询时间范围:")
    print(f"  开始时间 (UTC): {start_time_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  结束时间 (UTC): {end_time_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  开始时间戳: {start_timestamp_ms}")
    print(f"  结束时间戳: {end_timestamp_ms}")

    try:
        # 获取K线数据
        # limit=1500 足够获取96根K线（24小时）
        klines = client.klines(
            symbol=symbol,
            interval='15m',
            startTime=start_timestamp_ms,
            endTime=end_timestamp_ms,
            limit=1500
        )

        # 计算累计成交额
        total_quote_volume = 0.0  # 成交额（计价货币，如USDT）
        kline_count = 0

        for kline in klines:
            # 成交额在索引7（第8个字段）
            # 注意：币安返回的是字符串，需要转换为float
            quote_volume = float(kline[7])
            total_quote_volume += quote_volume
            kline_count += 1

        # 计算24小时前的精确时间（用于返回）
        start_time_for_return = end_time - datetime.timedelta(hours=24)
        return {
            'symbol': symbol,
            'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'start_time': start_time_for_return.strftime('%Y-%m-%d %H:%M:%S'),
            'total_quote_volume': total_quote_volume,
            'total_quote_volume_formatted': f"{total_quote_volume:,.2f}",
            'kline_count': kline_count,
            'data': klines  # 如果需要原始数据
        }

    except Exception as e:
        print(f"获取数据失败: {e}")
        return None


# 使用示例
if __name__ == '__main__':
    # 示例1：获取指定时间前24小时的累计成交额
    target_time = datetime.datetime(2026, 4, 9, 14, 45, 0)  # 2026年4月9日 18:15:00
    result = get_24h_volume_by_15min('DYMUSDT', target_time)

    if result:
        print("\n" + "=" * 50)
        print(f"交易对: {result['symbol']}")
        print(f"统计周期: 15分钟K线")
        print(f"统计范围: {result['start_time']} 至 {result['end_time']}")
        print(f"实际K线数量: {result['kline_count']} 根")
        print(f"24小时累计成交额: {result['total_quote_volume']} USDT")
        print(f"24小时累计成交额f: {result['total_quote_volume_formatted']} USDT")
        print("=" * 50)

