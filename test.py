# test_fix.py
import logging
from .signal_recorder import SignalRecorder

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def test_fixes():
    """测试所有修复"""
    print("🔧 测试信号记录器修复...")

    recorder = SignalRecorder(data_dir="test_signal_data")

    # 测试1: get_all_data() 方法
    print("\n✅ 测试1: get_all_data()")
    data = recorder.get_all_data()
    print(f"当前数据: {data}")

    # 测试2: 添加信号
    print("\n✅ 测试2: 添加信号")
    success, msg = recorder.add_signal("BTCUSDT", "a", 50000)
    print(f"结果: {success}, 消息: {msg}")

    # 测试3: 获取历史日期
    print("\n✅ 测试3: 获取历史日期")
    dates = recorder.get_history_dates()
    print(f"历史日期: {dates}")

    # 测试4: 加载历史文件（兼容性测试）
    print("\n✅ 测试4: 兼容性方法")
    if dates:
        data1 = recorder.load_history_file(dates[0] if dates else "2025-12-20")
        data2 = recorder.load_history_data(dates[0] if dates else "2025-12-20")
        print(f"方法兼容性: {data1 == data2}")

    print("\n🎉 所有测试完成!")


if __name__ == "__main__":
    test_fixes()