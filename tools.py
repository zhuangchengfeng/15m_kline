import pygetwindow as gw
import time

import logging
from functools import wraps
from datetime import datetime, timezone, timedelta


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


from functools import wraps
import time


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


