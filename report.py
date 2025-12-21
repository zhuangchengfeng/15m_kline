# report.py
from binance.um_futures import UMFutures
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict

# 导入信号记录器
try:
    from .signal_recorder import SignalRecorder

    signal_recorder = SignalRecorder()
    RECORDER_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("SignalRecorder未找到，标记价格将不会被更新")
    RECORDER_AVAILABLE = False


class Report:
    def __init__(self, proxies=None):
        """
        初始化币安交易分析器

        Args:
            proxies: 代理设置，默认为None
        """
        self.proxies = proxies or {
            "http": "http://127.0.0.1:7890",
            "https": "http://127.0.0.1:7890"
        }
        self.client = UMFutures(proxies=self.proxies)

        # 初始化日志
        self.logger = logging.getLogger(__name__)

    def latest_price(self, symbol):
        """获取最新价格"""
        price = float(self.client.ticker_price(symbol)['price'])
        return price

    def update_mark_price(self, symbol: str) -> bool:
        """
        更新指定symbol的标记价格

        Args:
            symbol: 交易对

        Returns:
            bool: 是否更新成功
        """
        if not RECORDER_AVAILABLE:
            self.logger.warning("SignalRecorder不可用")
            return False

        try:
            # 先归档非当天文件
            signal_recorder.archive_non_current_files(days_to_keep=0)

            # 检查日期变化
            signal_recorder._check_date_change(archive_old=False)

            # 获取最新价格
            mark_price = self.latest_price(symbol)
            update_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

            # 更新标记价格
            signal_recorder.update_mark_price(symbol, mark_price, update_time)

            self.logger.info(f"✅ 已更新 {symbol}: {mark_price}, 时间: {update_time}")
            return True

        except Exception as e:
            self.logger.error(f"更新 {symbol} 价格失败: {e}")
            return False
    def update_all_mark_prices(self) -> bool:
        """
        更新所有已记录symbol的标记价格

        步骤：
        1. 归档非当天文件到history目录
        2. 更新当天文件的价格
        """
        if not RECORDER_AVAILABLE:
            self.logger.warning("SignalRecorder不可用，无法更新标记价格")
            return False

        try:
            self.logger.info("🔄 开始更新标记价格流程...")

            # 步骤1: 归档非当天的JSON文件
            self.logger.info("📦 归档非当天文件...")
            archived_count = signal_recorder.archive_non_current_files(days_to_keep=0)
            self.logger.info(f"已归档 {archived_count} 个文件")

            # 步骤2: 检查日期变化（确保使用当天文件）
            signal_recorder._check_date_change(archive_old=False)

            # 步骤3: 获取所有已记录的symbol
            all_data = signal_recorder.get_all_data()
            symbols = list(all_data.keys())

            if not symbols:
                self.logger.info("📭 没有需要更新价格的symbol")
                return True

            self.logger.info(f"📊 发现 {len(symbols)} 个需要更新的symbol")

            updated_count = 0
            update_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

            for symbol in symbols:
                try:
                    # 获取最新价格
                    mark_price = self.latest_price(symbol)

                    # 更新标记价格和更新时间
                    signal_recorder.update_mark_price(symbol, mark_price, update_time)

                    updated_count += 1
                    self.logger.debug(f"已更新 {symbol}: {mark_price}")

                    # 每10个输出一次进度
                    if updated_count % 10 == 0:
                        self.logger.info(f"进度: {updated_count}/{len(symbols)}")

                except Exception as e:
                    self.logger.error(f"更新 {symbol} 价格失败: {e}")

            self.logger.info(f"✅ 当天价格更新完成: {updated_count}/{len(symbols)}")

            # 步骤4: 更新3天内的历史文件
            self.logger.info("🕐 开始更新3天内的历史文件...")
            history_results = self.update_recent_history(days=3)

            total_updated = sum(r[0] for r in history_results.values())
            total_symbols = sum(r[1] for r in history_results.values())

            self.logger.info(f"📈 历史数据更新完成: {total_updated}/{total_symbols}")

            return True

        except Exception as e:
            self.logger.error(f"更新标记价格失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def update_history_mark_price(self, date_str: str, symbol: str) -> bool:
        """
        更新历史文件中指定symbol的标记价格

        Args:
            date_str: 日期字符串，如 "2025-12-20"
            symbol: 交易对

        Returns:
            bool: 是否更新成功
        """
        if not RECORDER_AVAILABLE:
            self.logger.warning("SignalRecorder不可用")
            return False

        try:
            # 获取最新价格
            mark_price = self.latest_price(symbol)
            update_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

            # 更新历史文件
            success = signal_recorder.update_history_mark_price(
                date_str, symbol, mark_price, update_time
            )

            return success

        except Exception as e:
            self.logger.error(f"更新历史标记价格失败: {e}")
            return False

    def update_all_history_mark_prices(self, date_str: str, days_limit: int = 3) -> Tuple[int, int]:
        """
        更新历史文件中所有symbol的标记价格

        Args:
            date_str: 日期字符串
            days_limit: 只更新几天内的数据，默认3天

        Returns:
            Tuple[int, int]: (成功更新数, 总symbol数)
        """
        if not RECORDER_AVAILABLE:
            self.logger.warning("SignalRecorder不可用")
            return 0, 0

        def get_price(symbol: str) -> float:
            """内部函数用于获取价格"""
            return self.latest_price(symbol)

        # 调用信号记录器的方法
        updated_count, total_symbols = signal_recorder.update_all_history_mark_prices(
            date_str, get_price, days_limit
        )

        return updated_count, total_symbols

    def batch_update_history_dates(self, date_strings: List[str], days_limit: int = 3) -> Dict[str, Tuple[int, int]]:
        """
        批量更新多个历史日期的标记价格

        Args:
            date_strings: 日期字符串列表
            days_limit: 只更新几天内的数据

        Returns:
            Dict[str, Tuple[int, int]]: 每个日期的更新结果
        """
        results = {}

        for date_str in date_strings:
            self.logger.info(f"🔄 开始更新 {date_str} 的标记价格...")
            updated, total = self.update_all_history_mark_prices(date_str, days_limit)
            results[date_str] = (updated, total)

        return results

    def update_recent_history(self, days: int = 3) -> Dict[str, Tuple[int, int]]:
        """
        更新最近N天的历史数据

        Args:
            days: 天数

        Returns:
            Dict[str, Tuple[int, int]]: 每个日期的更新结果
        """
        if not RECORDER_AVAILABLE:
            self.logger.warning("SignalRecorder不可用")
            return {}

        # 获取所有历史日期
        all_dates = signal_recorder.get_history_dates()

        if not all_dates:
            self.logger.info(f"📭 没有历史数据")
            return {}

        # 过滤最近N天
        recent_dates = []
        today = datetime.now()

        for date_str in all_dates:
            try:
                # 解析日期字符串
                file_date = datetime.strptime(date_str, "%Y-%m-%d")

                # 计算天数差
                days_diff = (today - file_date).days

                if 0 < days_diff <= days:  # 只更新今天之前的数据
                    recent_dates.append(date_str)

            except Exception as e:
                self.logger.warning(f"解析日期 {date_str} 失败: {e}")
                continue

        if not recent_dates:
            self.logger.info(f"📅 最近 {days} 天没有历史数据需要更新")
            return {}

        self.logger.info(f"📋 找到 {len(recent_dates)} 个需要更新的历史日期")

        # 批量更新
        results = self.batch_update_history_dates(recent_dates, days_limit=days)

        # 汇总统计
        total_updated = sum(r[0] for r in results.values())
        total_symbols = sum(r[1] for r in results.values())

        if total_updated > 0:
            self.logger.info(f"✅ 历史数据更新完成: 共更新 {total_updated}/{total_symbols} 个symbol")

        return results

    def show_history_dates(self) -> List[str]:
        """显示所有历史日期"""
        if not RECORDER_AVAILABLE:
            self.logger.warning("SignalRecorder不可用")
            return []

        # 使用正确的方法名
        dates = signal_recorder.get_history_dates()

        self.logger.info("可用的历史日期:")
        for i, date_str in enumerate(dates, 1):
            # 使用正确的方法名
            data = signal_recorder.load_history_file(date_str)
            symbol_count = len(data)
            signal_count = sum(len(v.get("signals", [])) for v in data.values())

            self.logger.info(f"  {i}. {date_str}: {symbol_count}个symbol, {signal_count}个信号")

        return dates

    def show_today_stats(self):
        """显示当天统计数据"""
        if not RECORDER_AVAILABLE:
            self.logger.warning("SignalRecorder不可用")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        data = signal_recorder.get_all_data()

        if not data:
            self.logger.info(f"📭 今天({today_str})没有数据")
            return

        self.logger.info(f"📊 今天({today_str})统计数据:")
        self.logger.info(f"  Symbol数量: {len(data)}")

        total_signals = 0
        symbols_with_update = 0

        for symbol, info in data.items():
            signals = info.get("signals", [])
            total_signals += len(signals)

            if info.get("update_time"):
                symbols_with_update += 1

            # 显示收益统计
            if signals and info.get("mark_price", 0) > 0:
                avg_gap = sum(s.get("gap", 0) for s in signals) / len(signals)
                self.logger.debug(f"    {symbol}: {len(signals)}个信号, "
                                  f"最新价: {info.get('mark_price', 'N/A')}, "
                                  f"平均收益: {avg_gap:.2%}")

        self.logger.info(f"  总信号数: {total_signals}")
        self.logger.info(f"  已更新价格的symbol: {symbols_with_update}/{len(data)}")


if __name__ == '__main__':
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    print("=" * 60)
    print("           Report工具 - 更新JSON文件")
    print("=" * 60)

    # 测试功能
    r = Report()

    # 1. 归档文件并更新当天价格
    print("\n1. 归档文件并更新当天价格:")
    success = r.update_all_mark_prices()

    # 2. 显示当天统计
    print("\n2. 当天统计数据:")
    r.show_today_stats()

    # 3. 显示历史日期
    print("\n3. 历史文件列表:")
    r.show_history_dates()

    print("\n" + "=" * 60)
    print("完成！")
    print("=" * 60)