from dataclasses import dataclass
import requests
from datetime import timezone, timedelta
import logging
import datetime
import time
# 导入信号记录器
from tools import get_timestamp

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
    '1w': 10080,
}


def interval_divide():
    filtered_intervals = {k: v for k, v in INTERVAL_TO_MIN.items()
                          }
    schedule_rules = {}
    for interval, minutes in filtered_intervals.items():
        if minutes <= 30:  # 分钟级别周期：
            # 计算分钟数组：每个周期内的分钟点
            minute_points = list(range(0, 60, minutes))
            schedule_rules[interval] = (None, minute_points)

        elif minutes == 60:  # 1小时周期
            # 在整点运行
            schedule_rules[interval] = (None, [0])

        elif minutes == 120:  # 2小时周期
            # 在0,2,4,6,8,10,12,14,16,18,20,22点运行
            hour_points = list(range(0, 24, 2))
            schedule_rules[interval] = (hour_points, [0])

        elif minutes == 240:  # 4小时周期
            # 在0,4,8,12,16,20点运行
            hour_points = [0, 4, 8, 12, 16, 20]
            schedule_rules[interval] = (hour_points, [0])
        elif minutes == 1440:

            hour_points = [8]
            schedule_rules[interval] = (hour_points, [0])

    return schedule_rules


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

    return res.json()


# 配置类
@dataclass
class Config:


    RATELIMIT = get_exchange_info().get('rateLimits')[0].get('limit')
    ONE_MONTH_LATER = int(time.time() * 1000) + (30 * 24 * 3600 * 1000)

    P5 = True
    if P5:
        CLICK_COORDINATES_BINANCE = {
            'first_double_click': (165, 508),  # 币安电脑端自定义布局 查询品种坐标
            'second_click': (165, 620), }  # 下移单位
    else:
        CLICK_COORDINATES_BINANCE = {
            'first_double_click': (165, 175),  # 币安电脑端 查询品种坐标
            'second_click': (165, 300), }  # 下移单位

    CLICK_COORDINATES_TRADING_VIEW = {
        'second_click': (758, 421)
    }

    #  ---------------------------------------------------------#
    SCAN_INTERVALS_DEBUG = False  # 调试模式
    KLINE_INTERVAL = ['15m','1w','1h']   #修改detect时一定要注意  保证这里出现的周期和detect出现的一致
    MIN_VOLUME = 10000000  # 仅选择最小成交量需要大于MIN_VOLUME的品种
    SYMBOLS_RANGE = (1, 150)  # 取涨幅榜前1到品种
    POSITION_SIDE = ['LONG']
    BLACK_SYMBOL_LIST = []
    # END_TIME = get_timestamp(2026, 5, 1, 18, 15)    #:int ms  用于回测，输入结束时间判断K线信号
    END_TIME = None
    BACK_TESTING_SYMBOLS = []  #不回测时请清空
    #  ---------------------------------------------------------#


    # 添加日志级别配置
    @property
    def LOG_LEVEL(self):
        """根据调试模式返回日志级别"""
        return logging.DEBUG if self.SCAN_INTERVALS_DEBUG else logging.INFO

    SC = datetime.datetime.now().second
    MAX_RETRIES = 3
    TIMEOUT = 10
    PROXY = 'http://127.0.0.1:7890'
    PROXY_D = {"http": 'http://127.0.0.1:7890', "https": 'http://127.0.0.1:7890'}

    #  ---------------------------------------------------------#
    # 原来的 KLINE_LIMIT = 385
    # 改为字典，根据周期设置不同的保留K线数量
    KLINE_LIMIT = {
        '1m':385,
        '15m': 385,  # 15分钟周期保留385根（约4天）
        '1h':385,
        '1w': 1,  # 周线保留6根（约6周）
        # 其他周期可以添加默认值 # [1,100) 1 ,[100, 500) 2 ,[500, 1000] 5 ,> 1000 10
    }

    @classmethod
    def get_kline_limit(self, interval: str, default: int = 6) -> int:
        """根据K线周期返回需要保留的K线数量"""
        return self.KLINE_LIMIT.get(interval, default)

    KLINE_LIMIT_UPDATE = 6  # 增量更新最小K线  节省流量
    USE_DERIVED_MODE = True  # True: 大周期由小周期派生（默认模式）: 大周期直接请求API（非默认模式）

    #  ---------------------------------------------------------#

    UTC_TZ = timezone.utc
    BEIJING_TZ = timezone(timedelta(hours=8))

    KLINE_INTERVAL_SORT = sorted(
        KLINE_INTERVAL,  # 列表形式
        key=lambda x: INTERVAL_TO_MIN.get(x, 0),
        reverse=True
    )
    SCAN_SECOND_DELAY = range(8,58)  # 扫描时间点（秒） list or int type
    SCAN_INTERVALS = interval_divide().get(KLINE_INTERVAL_SORT[-1])
    EMA_ATR_INFO = False
    PLAY_SOUND = True

    API_KEY_SECRET_FILE_PATH = "H:\交易经验\l.txt"  # save your bn key and secret .txt  double lines
    TARGET = round(200, 0)  # 你 的目标本金,your point USDT in the future
    POLY_MARKET = False

    RATIO = 1.3
    SCAN_ON_START = True

    try:
        from signal_recorder import SignalRecorder
        DEFAULT_JSON_PATH = ['signal_data/history/', 'signal_data/']
        AFTER_TIME_HOUR = 4
        duplicate_window = INTERVAL_TO_MIN.get(KLINE_INTERVAL_SORT[-1])
        signal_recorder = SignalRecorder(hour=AFTER_TIME_HOUR,duplicate_window=duplicate_window)
        RECORDER_AVAILABLE = False if len(BACK_TESTING_SYMBOLS) >0 else True
        RECORDER_LOGGER = False
    except ImportError:
        import traceback
        traceback.print_exc()
        logger = logging.getLogger(__name__)
        logger.warning("SignalRecorder未找到，信号将不会被记录")
        RECORDER_AVAILABLE = False

Config()
