from dataclasses import dataclass


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
    print(f"  扫描间隔: 每15分钟 (在 {Config.SCAN_INTERVALS} 分钟整点)")
    print("=" * 60)
    print("\n程序运行中...按 + 或 - 键开始操作")


# 配置类
@dataclass
class Config:
    CLICK_COORDINATES = {
        'first_double_click': (165, 175),
        'second_click': (165, 300),
        'third_click': (200, 300)
    }
    SCAN_INTERVALS = [0, 15, 30, 45]  # 扫描时间点（分钟）
    SCAN_SECOND_DELAY = [2, 3]  # 扫描时间点（秒） list or int type
    SCAN_INTERVALS_DEBUG = False  # 扫描时间调试（每分钟）
    MAX_RETRIES = 5
    TIMEOUT = 10
    PROXY = 'http://127.0.0.1:7890'
    KLINE_LIMIT = 5
    KLINE_INTERVAL = "15m"
    MIN_VOLUME = 10000000
    SYMBOLS_RANGE = (1, 80)
