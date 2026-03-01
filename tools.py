import pygetwindow as gw
import time

import logging
from functools import wraps


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


