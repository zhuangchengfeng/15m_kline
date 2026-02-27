import pygetwindow as gw
import time


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



