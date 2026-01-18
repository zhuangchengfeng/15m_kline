from dataclasses import dataclass
import requests
from datetime import datetime, timezone, timedelta
import logging
from binance.um_futures import UMFutures

# 导入信号记录器


INTERVAL_TO_MIN = {
    '1m': 1,
    '3m': 3,
    '5m': 5,
    '15m': 15,
    '30m': 30,
    '1h': 60,
    '2h': 120,
    '4h': 240,
    '6h': 360,
    '8h': 480,
    '12h': 720,
    '1d': 1440,
    '3d': 4320,
    '1w': 10080,
    '1M': 43200  # 近似值
}
def interval_divide():
    FILTERED_INTERVALS = {k: v for k, v in INTERVAL_TO_MIN.items()
                          if v >= 1 and v <= 240}

    SCHEDULE_RULES = {}

    for interval, minutes in FILTERED_INTERVALS.items():
        if minutes <= 30:  # 分钟级别周期：
            # 计算分钟数组：每个周期内的分钟点
            minute_points = list(range(0, 60, minutes))
            SCHEDULE_RULES[interval] = (None, minute_points)

        elif minutes == 60:  # 1小时周期
            # 在整点运行
            SCHEDULE_RULES[interval] = (None, [0])

        elif minutes == 120:  # 2小时周期
            # 在0,2,4,6,8,10,12,14,16,18,20,22点运行
            hour_points = list(range(0, 24, 2))
            SCHEDULE_RULES[interval] = (hour_points, [0])

        elif minutes == 240:  # 4小时周期
            # 在0,4,8,12,16,20点运行
            hour_points = [0, 4, 8, 12, 16, 20]
            SCHEDULE_RULES[interval] = (hour_points, [0])
        elif minutes == 1440:

            hour_points = [8]
            SCHEDULE_RULES[interval] = (hour_points, [0])

    return SCHEDULE_RULES

def display_status():
    """显示初始状态信息"""
    print("\n" + "=" * 60)
    print("              Trading Signal Bot 状态")
    print("=" * 60)
    print("功能说明:")
    print("  🔘 按 '+' 键: 执行当前信号并切换到下一个")
    print("  🔘 按 '-' 键: 执行当前信号并切换到上一个")
    print("显示说明:")
    print("  ✅ 已执行的信号前会显示对勾")
    print("  ⏳ 未执行的信号前会显示时钟")
    print("  [2/5]✅ 表示：第2个/共5个，已执行")
    print()
    print("配置信息:")
    print(f"  扫描间隔:  (在 {Config.SCAN_INTERVALS} 分钟整点)")
    print("=" * 60)
    print("\n程序运行中...按 + 或 - 键开始操作")


def get_exchange_info():
    url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
    res = requests.get(url=url, proxies={"http": 'http://127.0.0.1:7890', "https": 'http://127.0.0.1:7890'})
    return res.json().get('rateLimits')[0].get('limit')


# 配置类
@dataclass
class Config:
    UM_CLIENT = UMFutures(proxies={
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890"
    })

    try:
        from signal_recorder import SignalRecorder
        signal_recorder = SignalRecorder()
        RECORDER_AVAILABLE = True
        RECORDER_LOGGER = False
    except ImportError:
        logger = logging.getLogger(__name__)
        logger.warning("SignalRecorder未找到，信号将不会被记录")
        RECORDER_AVAILABLE = False

    RATELIMIT = get_exchange_info()
    CLICK_COORDINATES_BINANCE = {
        'first_double_click': (165, 175),  # 币安电脑端 查询品种坐标
        'second_click': (165, 300),}  # 默认下移125单位

    CLICK_COORDINATES_TRADING_VIEW = {
        # 'first_double_click': (145, 100),  # tradingview电脑端 查询品种坐标
        # 'second_click': (699, 287),
        'second_click': (758, 421)
    }

    #  ---------------------------------------------------------#
    SCAN_INTERVALS_DEBUG = True  # 扫描时间调试（True则启动时先运行一次）
    KLINE_INTERVAL = ['1h']
    MIN_VOLUME = 10000000  # 仅选择最小成交量需要大于MIN_VOLUME的品种
    SYMBOLS_RANGE = (1, 100)  # 取涨幅榜前1到80品种
    POSITION_SIDE = ['LONG','SHORT']
    #  ---------------------------------------------------------#

    if SCAN_INTERVALS_DEBUG:
        import datetime
        SC = datetime.datetime.now().second
    MAX_RETRIES = 2
    TIMEOUT = 10
    PROXY = 'http://127.0.0.1:7890'
    PROXY_D = {"http": 'http://127.0.0.1:7890', "https": 'http://127.0.0.1:7890'}
    KLINE_LIMIT = 499  # [1,100)	1 ,[100, 500)	2 ,[500, 1000]	5 ,> 1000	10

    DEFAULT_JSON_PATH = ['signal_data/history/', 'signal_data/']
    UTC_TZ = timezone.utc
    BEIJING_TZ = timezone(timedelta(hours=8))

    KLINE_INTERVAL_SORT = sorted(
        KLINE_INTERVAL,  # 列表形式
        key=lambda x: INTERVAL_TO_MIN.get(x, 0),
        reverse=True
    )

    SCAN_SECOND_DELAY = [4, 5, 6]  # 扫描时间点（秒） list or int type
    SCAN_INTERVALS = interval_divide().get(KLINE_INTERVAL_SORT[-1])

    EMA_ATR_INFO = False
    PLAY_SOUND = True