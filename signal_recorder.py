# signal_recorder.py - 完整修复版本
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional
import logging
logger = logging.getLogger(__name__)


class SignalRecorder:
    def __init__(self, hour,data_dir: str = "signal_data"):
        """初始化信号记录器"""
        self.data_dir = data_dir
        self.history_dir = os.path.join(data_dir, "history")

        self.hour = min(hour,24)
        # 创建目录
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(self.history_dir, exist_ok=True)

        # 当前文件
        self.current_date = datetime.now().strftime("%Y/%m/%d").replace("/", "-")
        self.current_file = os.path.join(data_dir, f"{self.current_date}.json")

        # 加载数据
        self.data = self._load_or_init_data()
        self.duplicate_time_window = 10  # 防重复时间窗口(分钟)

    def _load_or_init_data(self) -> Dict[str, Any]:
        """加载或初始化数据"""
        if os.path.exists(self.current_file):
            try:
                with open(self.current_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data
            except Exception as e:
                logger.error(f"加载信号文件失败: {e}")
                return {}
        return {}

    def _check_date_change(self, archive_old: bool = True):
        """
        检查日期变化
        """
        today_str = datetime.now().strftime("%Y/%m/%d").replace("/", "-")

        if today_str != self.current_date:
            # 保存当前数据
            if self.data:
                self.save()

            if archive_old and os.path.exists(self.current_file) and self.data:
                # 归档旧文件到history目录
                archive_file = os.path.join(self.history_dir, os.path.basename(self.current_file))
                try:
                    os.replace(self.current_file, archive_file)
                    logger.info(f"已归档文件到: {archive_file}")
                except Exception as e:
                    logger.error(f"归档文件失败: {e}")

            # 创建新文件
            self.current_date = today_str
            self.current_file = os.path.join(self.data_dir, f"{self.current_date}.json")
            self.data = {}

    def add_signal(self, **kwargs) -> Tuple[bool, str]:
        """
        添加信号记录

        Args:
            **kwargs: 必须包含 symbol, interval, position_side, open_price
                     可选: time_str, check_duplicate
        """
        # 检查必要参数
        required_params = ['symbol', 'interval', 'position_side', 'open_price']
        for param in required_params:
            if param not in kwargs:
                return False, f"缺少必要参数: {param}"

        # 获取参数
        symbol = kwargs['symbol']
        interval = kwargs['interval']
        position_side = kwargs['position_side']
        open_price = kwargs['open_price']
        time_str = kwargs.get('time_str')  # 可选，默认None
        check_duplicate = kwargs.get('check_duplicate', True)  # 可选，默认True

        # 检查日期变化
        self._check_date_change()

        # 获取当前时间
        if time_str is None:
            time_str = datetime.now()
        elif isinstance(time_str, str):
            # 如果传入的是字符串，转换为datetime对象
            time_str = datetime.strptime(time_str, "%Y/%m/%d %H:%M:%S")

        # 检查重复信号
        if check_duplicate:
            # 首先检查是否为重复信号（相同类型、相似价格）
            if self._is_duplicate_signal(symbol, open_price, time_str):
                return False, f"重复信号: {symbol} 价格: {open_price}"

        # 初始化symbol的数据结构
        if symbol not in self.data:
            self.data[symbol] = {
                "signals": []
            }

        # 创建信号记录
        signal_record = {
            "open_time": time_str.strftime("%Y/%m/%d %H:%M:%S"),
            "open_price": open_price,
            "after_close_time": (time_str + timedelta(hours=self.hour)).strftime("%Y/%m/%d %H:%M:%S"),
            "after_high_price": 0.0,
            "after_low_price": 0.0,
            "rate_of_up_change": '',
            "rate_of_down_change": '',
            "interval":interval,
            "position_side":position_side,
            "update_time": time_str.strftime("%Y/%m/%d %H:%M:%S")

        }

        # 添加到信号列表
        self.data[symbol]["signals"].append(signal_record)

        # 保存到文件
        self.save()

        msg = f"已记录信号: {symbol} - 价格: {open_price}"
        logger.debug(msg)
        return True, msg

    def save(self):
        """保存数据"""
        try:
            with open(self.current_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存信号文件失败: {e}")

    def load_history_file(self, date_str: str) -> Dict[str, Any]:
        """
        加载历史文件

        Args:
            date_str: 日期字符串，如 "2025-12-20"

        Returns:
            Dict: 历史数据
        """
        # 先尝试从history目录加载
        history_file = os.path.join(self.history_dir, f"{date_str}.json")
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载历史文件失败: {e}")

        # 尝试从当前目录加载
        current_file = os.path.join(self.data_dir, f"{date_str}.json")
        if os.path.exists(current_file):
            try:
                with open(current_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载文件失败: {e}")

        logger.warning(f"未找到日期为 {date_str} 的文件")
        return {}

    def _is_duplicate_signal(self, symbol: str, open_price: float, time_str: str) -> bool:
        """
        检查是否为重复信号

        Args:
            symbol: 交易对
            open_price: 开仓价格
            time_str: 时间字符串

        Returns:
            bool: 是否为重复信号
        """
        if symbol not in self.data:
            return False

        # 转换时间字符串为datetime对象
        try:
            current_time = datetime.strptime(time_str, "%Y/%m/%d %H:%M:%S")
        except:
            # 如果时间格式不正确，使用当前时间
            current_time = datetime.now()

        # 获取该symbol的所有信号
        signals = self.data[symbol].get("signals", [])

        for signal in signals[::-1]:  # 从最新的开始检查
            # 检查时间差
            try:
                signal_time = datetime.strptime(signal["time"], "%Y/%m/%d %H:%M:%S")
            except:
                continue

            time_diff = (current_time - signal_time).total_seconds() / 60  # 转换为分钟

            # 如果在时间窗口内，检查是否为重复
            if time_diff <= self.duplicate_time_window:
                # 检查价格是否相近（避免微小波动重复记录）
                price_diff = abs(open_price - signal["open_price"]) / signal["open_price"]
                if price_diff < 0.01:  # 价格差异小于1%
                    return True

        return False



