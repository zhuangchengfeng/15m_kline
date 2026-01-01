# report.py
from binance.um_futures import UMFutures
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
import os, json
from config import Config
import time
import coloredlogs
import logging

# 配置彩色日志
coloredlogs.install(
    level='INFO',
    fmt='%(asctime)s - %(name)s - %(message)s',  # 去掉levelname
    datefmt='%Y-%m-%d %H:%M:%S',
    field_styles={
        'asctime': {'color': 'green'},
        'name': {'color': 'blue', 'bold': True},
        'message': {'color': 'white'}
    },
    level_styles={
        'debug': {'color': 'cyan'},
        'info': {'color': 'white'},
        'warning': {'color': 'yellow', 'bold': True},
        'error': {'color': 'red', 'bold': True},
        'critical': {'color': 'red', 'bold': True, 'background': 'white'}
    }
)
# 然后正常使用logger
logger = logging.getLogger(__name__)



# 导入信号记录器
try:
    from signal_recorder import SignalRecorder

    signal_recorder = SignalRecorder()
    RECORDER_AVAILABLE = True
except ImportError:
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

        # 初始化价格缓存
        self._price_cache = {}
        self._cache_time = None
        self._cache_max_age = 60  # 缓存最大有效期（秒）

        # 初始化日志
        self.logger = logger

    def _refresh_price_cache(self):
        """
        刷新价格缓存，一次性获取所有交易对的价格
        """
        try:
            current_time = datetime.now()

            # 检查缓存是否过期
            if (self._cache_time and
                    (current_time - self._cache_time).total_seconds() < self._cache_max_age and
                    self._price_cache):
                return True

            # 获取所有交易对的价格
            all_prices = self.client.ticker_price()

            # 更新缓存
            self._price_cache = {}
            for price_info in all_prices:
                symbol = price_info['symbol']
                price = float(price_info['price'])
                self._price_cache[symbol] = price

            self._cache_time = current_time
            self.logger.debug(f"已更新价格缓存，共 {len(self._price_cache)} 个交易对")
            return True

        except Exception as e:
            self.logger.error(f"刷新价格缓存失败: {e}")
            return False

    def latest_price(self, symbol):
        """获取最新价格"""
        try:
            # 先刷新缓存
            if not self._refresh_price_cache():
                # 如果刷新失败，则使用原始方法
                return float(self.client.ticker_price(symbol)['price'])

            # 从缓存中获取价格
            if symbol in self._price_cache:
                return self._price_cache[symbol]
            else:
                # 如果缓存中没有该symbol，尝试直接获取
                self.logger.warning(f"缓存中未找到 {symbol}，尝试直接获取")
                return float(self.client.ticker_price(symbol)['price'])

        except Exception as e:
            self.logger.error(f"获取 {symbol} 价格失败: {e}")
            raise

    def batch_latest_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        批量获取多个symbol的最新价格

        Args:
            symbols: 交易对列表

        Returns:
            Dict[str, float]: 交易对到价格的映射
        """
        try:
            # 刷新缓存
            if not self._refresh_price_cache():
                # 如果刷新失败，则逐个获取
                result = {}
                for symbol in symbols:
                    try:
                        result[symbol] = float(self.client.ticker_price(symbol)['price'])
                    except Exception as e:
                        self.logger.error(f"获取 {symbol} 价格失败: {e}")
                        result[symbol] = 0.0
                return result

            # 从缓存中批量获取
            result = {}
            missing_symbols = []

            for symbol in symbols:
                if symbol in self._price_cache:
                    result[symbol] = self._price_cache[symbol]
                else:
                    missing_symbols.append(symbol)

            # 处理缓存中没有的symbol
            if missing_symbols:
                self.logger.warning(f"缓存中缺少以下symbol: {missing_symbols}")
                for symbol in missing_symbols:
                    try:
                        result[symbol] = float(self.client.ticker_price(symbol)['price'])
                    except Exception as e:
                        self.logger.error(f"获取 {symbol} 价格失败: {e}")
                        result[symbol] = 0.0

            return result

        except Exception as e:
            self.logger.error(f"批量获取价格失败: {e}")
            # 降级为逐个获取
            result = {}
            for symbol in symbols:
                try:
                    result[symbol] = float(self.client.ticker_price(symbol)['price'])
                except Exception as e:
                    self.logger.error(f"获取 {symbol} 价格失败: {e}")
                    result[symbol] = 0.0
            return result

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

            # 批量获取所有价格
            self.logger.info("📡 批量获取所有symbol的价格...")
            prices = self.batch_latest_prices(symbols)

            updated_count = 0
            update_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

            for symbol in symbols:
                try:
                    # 从批量结果中获取价格
                    mark_price = prices.get(symbol)
                    if mark_price is None or mark_price == 0.0:
                        self.logger.warning(f"未能获取 {symbol} 的价格，跳过")
                        continue

                    # 更新标记价格和更新时间
                    signal_recorder.update_mark_price(symbol, mark_price, update_time)

                    updated_count += 1
                    # self.logger.debug(f"已更新 {symbol}: {mark_price}")

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

        # 优化后的价格获取函数
        def get_price(symbol: str) -> float:
            """内部函数用于获取价格"""
            try:
                # 先尝试从缓存获取
                if self._refresh_price_cache() and symbol in self._price_cache:
                    return self._price_cache[symbol]
                else:
                    return self.latest_price(symbol)
            except Exception as e:
                self.logger.error(f"获取 {symbol} 价格失败: {e}")
                return 0.0

        # 调用信号记录器的方法
        updated_count, total_symbols = signal_recorder.update_all_history_mark_prices(
            date_str, get_price, days_limit
        )

        return updated_count, total_symbols

    # 以下方法保持不变...
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
                self.logger.info(f"    {symbol}: {len(signals)}个信号, "
                                  f"最新价: {info.get('mark_price', 'N/A')}, "
                                  f"平均收益: {avg_gap:.2%}")

        self.logger.info(f"  总信号数: {total_signals}")
        self.logger.info(f"  已更新价格的symbol: {symbols_with_update}/{len(data)}")


def analyze_gap_sorted_signals(json_name=None, json_data=None, top_n=None,
                               ):
    """
    根据 gap 大小排序并生成信号分析信息

    参数:
    json_file_path: JSON 文件路径
    json_data: 直接传入的 JSON 数据（字典格式）
    top_n: 只显示前 N 个结果（可选）

    返回:
    格式化的分析结果字符串
    """
    # 加载数据
    """
    根据 gap 大小排序并生成信号分析信息
    """
    # 如果提供了json_name，先更新该文件的价格
    if json_name and not json_data:
        # 获取文件名中的日期部分（去掉.json）
        date_str = json_name.replace('.json', '')

        # 创建Report实例
        r = Report()

        # 检查是否是当天文件
        today_str = datetime.now().strftime("%Y-%m-%d")

        if date_str == today_str:
            # 更新当天文件
            print(f"🔄 更新当天价格: {json_name}")
            r.update_all_mark_prices()
        else:
            # 只更新指定的历史文件 - 直接读取文件并更新每个symbol
            print(f"🔄 更新历史文件: {json_name}")

            # 1. 找到文件路径
            file_path = None
            for base_path in Config.DEFAULT_JSON_PATH:
                test_path = os.path.join(base_path, json_name)
                if os.path.exists(test_path):
                    file_path = test_path
                    break

            if not file_path:
                print(f"❌ 未找到文件: {json_name}")
            else:
                # 2. 加载文件数据
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # 3. 更新文件中每个symbol的价格
                    symbols = list(data.keys())
                    prices = r.batch_latest_prices(symbols)  # 批量获取价格

                    updated_count = 0
                    update_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

                    for symbol in symbols:
                        mark_price = prices.get(symbol)
                        if mark_price and mark_price > 0:
                            # 更新标记价格
                            data[symbol]["mark_price"] = mark_price
                            data[symbol]["update_time"] = update_time

                            # 计算所有信号的gap
                            for signal in data[symbol].get("signals", []):
                                signal["gap"] = round((mark_price - signal["open_price"]) / signal["open_price"], 4)

                            updated_count += 1

                    # 4. 保存更新后的文件
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

                    print(f"✅ 已更新 {updated_count}/{len(symbols)} 个symbol的价格")

                except Exception as e:
                    print(f"⚠️  更新文件失败: {e}")
    default_file_path = Config.DEFAULT_JSON_PATH
    for i in default_file_path:
        file = i + json_name
        if os.path.exists(file):

            break
    else:
        return f"错误: 文件 '{json_name}' 不存在"


    if json_data :
        data = json_data
    elif json_name:
        with open(file=file, mode='r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        return "错误: 必须提供 json_file_path 或 json_data 参数"

    # 收集所有信号
    all_signals = []

    for symbol, info in data.items():
        mark_price = info.get('mark_price', 0)
        update_time = info.get('update_time', 'N/A')

        for signal in info.get('signals', []):
            signal_info = {
                'symbol': symbol,
                'mark_price': mark_price,
                'update_time': update_time,
                'time': signal.get('time', 'N/A'),
                'open_price': signal.get('open_price', 0),
                'gap': signal.get('gap', 0),
                'type': signal.get('type', '未知'),
                'gap_percent': signal.get('gap', 0) * 100  # 计算百分比绝对值用于排序
            }
            all_signals.append(signal_info)

    if not all_signals:
        return "未找到任何信号数据"

    # 按 gap 绝对值排序（从大到小）
    all_signals.sort(key=lambda x: x['gap_percent'], reverse=False)
    # 如果指定了 top_n，只取前 N 个
    if top_n and top_n > 0:
        all_signals = all_signals[:top_n]

    # 生成格式化输出
    output_lines = []
    output_lines.append("=" * 80)
    output_lines.append("信号分析报告 - 按 Gap 大小排序")
    output_lines.append("=" * 80)
    output_lines.append(f"总信号数量: {len(all_signals)}")
    output_lines.append("")

    # 表头
    output_lines.append(f"{'排名':<5} {'交易对':<15} {'信号类型':<10} {'Gap(%)':<10} {'开仓价':<15} {'标记价':<15} {'时间'}")
    output_lines.append("-" * 90)

    # 表格内容
    for i, signal in enumerate(all_signals, 1):
        rank = f"{i}"
        symbol = signal['symbol']
        signal_type = signal['type']

        # 格式化 gap，带正负号，保留4位小数
        gap_value = signal['gap']
        gap_percent = round(signal['gap_percent'], 4)
        gap_display = f"{gap_value:+.4f}"

        # 显示百分比和原始值
        gap_info = f"{gap_display}"

        open_price = f"{signal['open_price']}"
        mark_price = f"{signal['mark_price']}"
        time = signal['time']

        output_lines.append(
            f"{rank:<5} {symbol:<15} {signal_type:<10} {gap_percent}{'%':<10} {open_price:<15} {mark_price:<15} {time}")

    output_lines.append("")
    output_lines.append("分析说明:")
    output_lines.append("1. Gap: (标记价 - 开仓价) / 开仓价")
    output_lines.append("2. 正值表示标记价高于开仓价，负值表示标记价低于开仓价")
    output_lines.append("3. 按 |Gap| 从大到小排序")

    # 添加统计信息
    positive_gaps = [s for s in all_signals if s['gap'] > 0]
    negative_gaps = [s for s in all_signals if s['gap'] < 0]

    output_lines.append("")
    output_lines.append("统计信息:")
    output_lines.append(f"  上涨信号 (Gap>0): {len(positive_gaps)} 个")
    output_lines.append(f"  下跌信号 (Gap<0): {len(negative_gaps)} 个")
    output_lines.append(f"  最大涨幅: {max([s['gap'] for s in all_signals]) * 100:.2f}%" if all_signals else "无数据")
    output_lines.append(f"  最大跌幅: {min([s['gap'] for s in all_signals]) * 100:.2f}%" if all_signals else "无数据")

    return "\n".join(output_lines)


if __name__ == '__main__':


    # 这样所有的输出都会通过同一个处理器，保证顺序
    logger.info("=" * 60)
    logger.info("           Report工具 - 更新JSON文件")
    logger.info("=" * 60)

    # 测试功能
    r = Report()

    logger.warning("1. 当天统计数据:")
    r.show_today_stats()

    logger.warning("2. 历史文件列表:")
    r.show_history_dates()

    logger.info("=" * 60)
    logger.info("完成！")
    logger.info("=" * 60)

    logger.warning("3. 更新并汇报指定json:")
    data = analyze_gap_sorted_signals(json_name='2026-01-02.json')
    logger.info(data)