# signal_recorder.py - 完整修复版本
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class SignalRecorder:
    def __init__(self, data_dir: str = "signal_data"):
        """初始化信号记录器"""
        self.data_dir = data_dir
        self.history_dir = os.path.join(data_dir, "history")

        # 创建目录
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(self.history_dir, exist_ok=True)

        # 当前文件
        self.current_date = datetime.now().strftime("%Y/%m/%d").replace("/", "-")
        self.current_file = os.path.join(data_dir, f"{self.current_date}.json")

        # 加载数据
        self.data = self._load_or_init_data()
        self.duplicate_time_window = 15  # 防重复时间窗口(分钟)

    def _load_or_init_data(self) -> Dict[str, Any]:
        """加载或初始化数据"""
        if os.path.exists(self.current_file):
            try:
                with open(self.current_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 确保每个symbol都有update_time字段
                    for symbol in data:
                        if "update_time" not in data[symbol]:
                            data[symbol]["update_time"] = ""
                    return data
            except Exception as e:
                logger.error(f"加载信号文件失败: {e}")
                return {}
        return {}

    def _check_date_change(self, archive_old: bool = True):
        """
        检查日期变化

        Args:
            archive_old: 是否归档旧文件
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

    def add_signal(self, symbol: str, signal_type: str, open_price: float, time_str: str = None,
                   check_duplicate: bool = True) -> Tuple[bool, str]:
        """
        添加信号到记录

        Args:
            symbol: 交易对
            signal_type: 信号类型 (a, b, c)
            open_price: 开仓价格
            time_str: 时间字符串，默认为当前时间
            check_duplicate: 是否检查重复

        Returns:
            Tuple[bool, str]: (是否成功添加, 描述信息)
        """
        # 检查日期变化
        self._check_date_change()

        # 获取当前时间
        if time_str is None:
            time_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        # 检查重复信号
        if check_duplicate:
            # 首先检查是否为重复信号（相同类型、相似价格）
            if self._is_duplicate_signal(symbol, signal_type, open_price, time_str):
                return False, f"重复信号: {symbol} {signal_type} 价格: {open_price}"

            # 然后检查时间窗口内是否有相同类型的信号（无论价格）
            try:
                current_time = datetime.strptime(time_str, "%Y/%m/%d %H:%M:%S")
            except:
                current_time = datetime.now()

            if self._is_similar_signal_in_window(symbol, signal_type, current_time):
                return False, f"时间窗口内已有相同类型信号: {symbol} {signal_type}"

        # 初始化symbol的数据结构
        if symbol not in self.data:
            self.data[symbol] = {
                "mark_price": 0.0,
                "signals": []
            }

        # 创建信号记录
        signal_record = {
            "time": time_str,
            "open_price": open_price,
            "gap": 0.0,
            "type": signal_type
        }

        # 添加到信号列表
        self.data[symbol]["signals"].append(signal_record)

        # 保存到文件
        self.save()

        msg = f"已记录信号: {symbol} - {signal_type} - 价格: {open_price}"
        logger.info(msg)
        return True, msg

    def save(self):
        """保存数据"""
        try:
            with open(self.current_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存信号文件失败: {e}")

    def update_mark_price(self, symbol: str, mark_price: float, update_time: str = None):
        """
        更新标记价格和更新时间

        Args:
            symbol: 交易对
            mark_price: 标记价格
            update_time: 更新时间，默认当前时间
        """
        if symbol in self.data:
            # 更新标记价格
            self.data[symbol]["mark_price"] = mark_price

            # 更新update_time
            if update_time is None:
                update_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            self.data[symbol]["update_time"] = update_time

            # 计算所有未计算的gap
            for signal in self.data[symbol]["signals"]:
                if signal["gap"] == 0.0 and signal["open_price"] > 0:
                    signal["gap"] = round((mark_price - signal["open_price"]) / signal["open_price"], 4)

            self.save()

    def archive_non_current_files(self, days_to_keep: int = 3):
        """
        归档当天以外的JSON文件到history目录，并删除原文件

        Args:
            days_to_keep: 保留最近多少天的文件不归档
        """
        try:
            today = datetime.now()
            today_str = today.strftime("%Y-%m-%d")

            if not os.path.exists(self.data_dir):
                return 0

            archived_count = 0
            deleted_count = 0

            # 遍历data_dir中的所有JSON文件
            for filename in os.listdir(self.data_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.data_dir, filename)
                    date_str = filename.replace('.json', '')

                    # 跳过当天的文件
                    if date_str == today_str:
                        continue

                    try:
                        # 检查是否在保留天数内
                        file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        days_diff = (today - file_date).days

                        # 如果超过保留天数，归档并删除
                        if days_diff > days_to_keep:
                            # 归档到history目录
                            archive_path = os.path.join(self.history_dir, filename)

                            # 移动文件
                            os.replace(file_path, archive_path)
                            archived_count += 1
                            deleted_count += 1
                            logger.info(f"已归档并删除: {filename}")

                        # 如果在保留天数内，只归档不删除（或者也可以归档，这里我们归档并删除）
                        else:
                            # 如果文件不在history目录，先复制到history目录
                            archive_path = os.path.join(self.history_dir, filename)
                            if not os.path.exists(archive_path):
                                import shutil
                                shutil.copy2(file_path, archive_path)

                            # 删除原文件
                            os.remove(file_path)
                            archived_count += 1
                            logger.info(f"已归档: {filename}")

                    except ValueError as e:
                        logger.warning(f"文件名格式错误: {filename}, 跳过")
                        continue
                    except Exception as e:
                        logger.error(f"处理文件 {filename} 失败: {e}")

            logger.info(f"归档完成: 归档 {archived_count} 个文件，删除 {deleted_count} 个文件")
            return archived_count

        except Exception as e:
            logger.error(f"归档文件失败: {e}")
            return 0

    # 添加缺失的方法
    def get_all_data(self) -> Dict[str, Any]:
        """
        获取所有当前数据

        Returns:
            Dict: 所有数据
        """
        return self.data

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

    # 为保持兼容性添加别名
    def load_history_data(self, date_str: str) -> Dict[str, Any]:
        """load_history_data 的别名"""
        return self.load_history_file(date_str)

    def save_history_file(self, date_str: str, data: Dict[str, Any]) -> bool:
        """
        保存历史文件

        Args:
            date_str: 日期字符串
            data: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        try:
            # 保存到history目录
            history_file = os.path.join(self.history_dir, f"{date_str}.json")
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"已保存历史文件: {history_file}")
            return True
        except Exception as e:
            logger.error(f"保存历史文件失败: {e}")
            return False

    def update_history_mark_price(self, date_str: str, symbol: str, mark_price: float,
                                  update_time: str = None) -> bool:
        """
        更新历史文件中某个symbol的标记价格

        Args:
            date_str: 日期字符串
            symbol: 交易对
            mark_price: 标记价格
            update_time: 更新时间

        Returns:
            bool: 是否更新成功
        """
        try:
            # 加载历史数据
            history_data = self.load_history_file(date_str)
            if not history_data:
                return False

            if symbol not in history_data:
                logger.warning(f"历史文件 {date_str} 中没有 {symbol}")
                return False

            # 更新标记价格
            history_data[symbol]["mark_price"] = mark_price

            # 更新update_time
            if update_time is None:
                update_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            history_data[symbol]["update_time"] = update_time

            # 计算所有未计算的gap
            for signal in history_data[symbol]["signals"]:
                if signal["gap"] == 0.0 and signal["open_price"] > 0:
                    signal["gap"] = round((mark_price - signal["open_price"]) / signal["open_price"], 4)

            # 保存
            success = self.save_history_file(date_str, history_data)
            if success:
                logger.info(f"已更新历史文件 {date_str} 中 {symbol} 的价格: {mark_price}, 时间: {update_time}")

            return success

        except Exception as e:
            logger.error(f"更新历史价格失败: {e}")
            return False

    def update_all_history_mark_prices(self, date_str: str, price_getter_func,
                                       days_limit: int = 3) -> Tuple[int, int]:
        """
        更新历史文件中所有symbol的标记价格

        Args:
            date_str: 日期字符串
            price_getter_func: 获取价格的函数，接收symbol返回价格
            days_limit: 只更新几天内的数据

        Returns:
            Tuple[int, int]: (成功数, 总数)
        """
        try:
            # 检查日期是否在限制范围内
            today = datetime.now()
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                days_diff = (today - file_date).days

                # 如果超过days_limit天，不更新
                if days_diff > days_limit:
                    logger.info(f"跳过 {date_str}，超过 {days_limit} 天限制")
                    return 0, 0

            except ValueError:
                logger.warning(f"日期格式错误: {date_str}")
                return 0, 0

            # 加载历史数据
            history_data = self.load_history_file(date_str)
            if not history_data:
                return 0, 0

            total_symbols = len(history_data)
            updated_count = 0
            update_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

            for symbol in list(history_data.keys()):
                try:
                    # 获取价格
                    mark_price = price_getter_func(symbol)

                    # 更新
                    history_data[symbol]["mark_price"] = mark_price
                    history_data[symbol]["update_time"] = update_time

                    # 计算gap
                    for signal in history_data[symbol]["signals"]:
                        if signal["gap"] == 0.0 and signal["open_price"] > 0:
                            signal["gap"] = round((mark_price - signal["open_price"]) / signal["open_price"], 4)

                    updated_count += 1
                    logger.info(f"已更新 {symbol}: {mark_price}")

                except Exception as e:
                    logger.error(f"更新 {symbol} 失败: {e}")
                    continue

            # 保存
            if updated_count > 0:
                self.save_history_file(date_str, history_data)

            logger.info(f"历史文件 {date_str} 更新完成: {updated_count}/{total_symbols}")
            return updated_count, total_symbols

        except Exception as e:
            logger.error(f"更新历史文件失败: {e}")
            return 0, 0

    def get_history_dates(self) -> List[str]:
        """
        获取所有历史文件的日期列表

        Returns:
            List[str]: 日期列表
        """
        dates = []

        # 获取history目录中的文件
        try:
            for filename in os.listdir(self.history_dir):
                if filename.endswith('.json'):
                    date_str = filename.replace('.json', '')
                    dates.append(date_str)
        except Exception as e:
            logger.error(f"获取历史文件列表失败: {e}")

        # 获取当前目录中的文件（排除今天）
        try:
            for filename in os.listdir(self.data_dir):
                if filename.endswith('.json') and filename != f"{self.current_date}.json":
                    date_str = filename.replace('.json', '')
                    if date_str not in dates:
                        dates.append(date_str)
        except Exception as e:
            logger.error(f"获取文件列表失败: {e}")

        return sorted(dates, reverse=True)  # 最新的在前

    # 为保持兼容性添加别名
    def get_all_history_dates(self) -> List[str]:
        """get_all_history_dates 的别名"""
        return self.get_history_dates()

    def get_recent_signals(self, symbol: str, hours: int = 24) -> List[Dict[str, Any]]:
        """
        获取指定symbol最近N小时的信号

        Args:
            symbol: 交易对
            hours: 小时数

        Returns:
            List[Dict]: 信号列表
        """
        if symbol not in self.data:
            return []

        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_signals = []

        for signal in self.data[symbol]["signals"]:
            try:
                signal_time = datetime.strptime(signal["time"], "%Y/%m/%d %H:%M:%S")
                if signal_time >= cutoff_time:
                    recent_signals.append(signal)
            except:
                pass

        return recent_signals

    def clear_old_signals(self, days: int = 7):
        """
        清理指定天数前的信号

        Args:
            days: 天数
        """
        cutoff_time = datetime.now() - timedelta(days=days)

        for symbol in list(self.data.keys()):
            # 过滤保留最近N天的信号
            filtered_signals = []
            for signal in self.data[symbol].get("signals", []):
                try:
                    signal_time = datetime.strptime(signal["time"], "%Y/%m/%d %H:%M:%S")
                    if signal_time >= cutoff_time:
                        filtered_signals.append(signal)
                except:
                    filtered_signals.append(signal)

            # 更新信号列表
            self.data[symbol]["signals"] = filtered_signals

            # 如果该symbol没有信号了，删除整个symbol
            if not filtered_signals:
                del self.data[symbol]

    def _is_duplicate_signal(self, symbol: str, signal_type: str, open_price: float, time_str: str) -> bool:
        """
        检查是否为重复信号

        Args:
            symbol: 交易对
            signal_type: 信号类型
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
                # 检查信号类型是否相同
                if signal["type"] == signal_type:
                    # 检查价格是否相近（避免微小波动重复记录）
                    price_diff = abs(open_price - signal["open_price"]) / signal["open_price"]
                    if price_diff < 0.01:  # 价格差异小于1%
                        logger.info(f"检测到重复信号: {symbol} {signal_type} 价格差异: {price_diff:.2%} 时间差: {time_diff:.1f}分钟")
                        return True

        return False

    def _is_similar_signal_in_window(self, symbol: str, signal_type: str, current_time: datetime) -> bool:
        """
        检查在时间窗口内是否有相似信号（不检查价格）

        Args:
            symbol: 交易对
            signal_type: 信号类型
            current_time: 当前时间

        Returns:
            bool: 是否有相似信号
        """
        if symbol not in self.data:
            return False

        # 获取该symbol的所有信号
        signals = self.data[symbol].get("signals", [])

        for signal in signals[::-1]:  # 从最新的开始检查
            # 检查时间差
            try:
                signal_time = datetime.strptime(signal["time"], "%Y/%m/%d %H:%M:%S")
            except:
                continue

            time_diff = (current_time - signal_time).total_seconds() / 60  # 转换为分钟

            # 如果在时间窗口内，检查信号类型是否相同
            if time_diff <= self.duplicate_time_window and signal["type"] == signal_type:
                logger.info(f"时间窗口内有相同类型信号: {symbol} {signal_type} 时间差: {time_diff:.1f}分钟")
                return True

        return False


# 全局实例
signal_recorder = SignalRecorder()