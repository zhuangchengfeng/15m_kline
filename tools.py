import pygetwindow as gw
from functools import wraps
import time
import logging
from datetime import datetime, timezone, timedelta
import config
from binance.um_futures import UMFutures

UM_CLIENT = UMFutures(proxies={
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
})


def get_server_time_ms():
    """获取服务器时间（毫秒时间戳）"""
    client = UM_CLIENT
    resp = client.time()
    return resp['serverTime']

def ms_to_datetime(ms):
    """毫秒时间戳转本地 datetime 对象"""
    return datetime.fromtimestamp(ms / 1000.0)

def compare_times():
    """对比本地时间与服务器时间，输出差值（秒）"""
    local_before = time.time() * 1000
    server_ms = get_server_time_ms()
    local_after = time.time() * 1000

    local_estimate = (local_before + local_after) / 2
    diff_ms = server_ms - local_estimate
    print(f"服务器时间: {ms_to_datetime(server_ms)}")
    print(f"本地估算时间: {datetime.fromtimestamp(local_estimate / 1000)}")
    print(f"时间差: {diff_ms / 1000:.3f} 秒 (服务器时间 - 本地时间)")
    return diff_ms

def run_time_sync_monitor(iterations=10, interval=1):
    """
    封装的时间同步监控方法
    :param iterations: 对比次数
    :param interval: 每次对比间隔（秒）
    """
    print(f"开始时间同步监控，共 {iterations} 次，间隔 {interval} 秒\n")
    for i in range(iterations):
        print(f"--- 第 {i+1} 次 ---")
        diff = compare_times()
        if i < iterations - 1:
            time.sleep(interval)
    print("\n监控结束")


def get_timestamp(year, month, day, hour, minute, tz='Asia/Shanghai'):
    """
    将指定时间转换为毫秒时间戳

    Args:
        year: 年份
        month: 月份
        day: 日期
        hour: 小时
        minute: 分钟
        tz: 时区，默认 'Asia/Shanghai' (北京时间 UTC+8)

    Returns:
        int: 毫秒时间戳
    """
    # 创建 datetime 对象
    dt = datetime(year, month, day, hour, minute)

    # 设置时区
    if tz == 'Asia/Shanghai':
        # 北京时间 UTC+8
        beijing_tz = timezone(timedelta(hours=8))
        dt = dt.replace(tzinfo=beijing_tz)
    elif tz == 'UTC':
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        # 其他时区可以在这里添加
        raise ValueError(f"不支持的时区: {tz}")

    # 转换为毫秒时间戳
    timestamp_ms = int(dt.timestamp() * 1000)

    return timestamp_ms


def get_active_window_info():
    """获取当前活动窗口信息"""
    try:
        # 获取当前活动窗口
        active_window = gw.getActiveWindow()

        if active_window:
            return {
                "title": active_window.title,
                "process": None,  # pygetwindow不提供进程名
                "geometry": {
                    "left": active_window.left,
                    "top": active_window.top,
                    "width": active_window.width,
                    "height": active_window.height
                }
            }
        return None
    except Exception as e:
        print(f"获取窗口信息失败: {e}")
        return None


# 实时监控活动窗口变化
def monitor_active_window(interval=1):
    """监控活动窗口变化"""
    last_title = None

    while True:
        window = get_active_window_info()
        if window and window["title"] != last_title:
            last_title = window["title"]

        time.sleep(interval)




def async_timer_decorator(func):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):  # 注意 self 参数
        start_time = time.time()
        result = await func(self, *args, **kwargs)
        end_time = time.time()

        # 尝试从实例获取 logger
        if hasattr(self, 'logger'):
            self.logger.info(f"{func.__name__} 运行时间: {end_time - start_time:.2f} 秒")
        else:
            # 如果没有 logger，使用 print 作为后备
            logger = logging.getLogger(__name__)
            logger.info(f"{func.__name__} 运行时间: {end_time - start_time:.2f} 秒")

        return result

    return wrapper


# 辅助函数：时间戳转北京时间字符串
def timestamp_to_beijing_str(timestamp_ms: float) -> str:
    """
    将毫秒时间戳转换为北京时间的字符串

    Args:
        timestamp_ms: 毫秒时间戳

    Returns:
        str: 北京时间字符串，格式：YYYY/MM/DD HH:MM:SS
    """
    # 设置北京时区
    BEIJING_TZ = timezone(timedelta(hours=8))
    UTC_TZ = timezone.utc

    try:
        timestamp_seconds = timestamp_ms / 1000.0
        utc_time = datetime.fromtimestamp(timestamp_seconds, tz=UTC_TZ)
        beijing_time = utc_time.astimezone(BEIJING_TZ)
        return beijing_time.strftime("%Y/%m/%d %H:%M:%S")
    except Exception as e:
        print(f"时间戳转换失败: {e}")
        return datetime.now(BEIJING_TZ).strftime("%Y/%m/%d %H:%M:%S")


if __name__ == '__main__':
    run_time_sync_monitor()