import asyncio
from typing import List, Optional, Dict, Any
import logging
import time
import datetime
import queue
import concurrent.futures
from collector import BinanceKlineCollector
from detect import detect_signal
from config import Config, display_status
from alert_manager import AlertManager
from keyboard_handler import KeyboardHandler
from signal_manager import SignalManager
from mouse_operator import MouseOperator
import requests
from ema_atr_manager import EmaAtrManager
from speaking_manager import PlaySound
import threading
import os
from tools import async_timer_decorator


async def fetch_all_kline(symbols: List[str], interval: str, limit: int, max_retries: int,
                          collector: BinanceKlineCollector, use_cache: bool = True) -> List[Dict[str, Any]]:
    """并发获取所有币种K线数据"""
    tasks = [collector.fetch_kline(symbol, interval, limit, max_retries, use_cache) for symbol in symbols]
    results = await asyncio.gather(*tasks)
    return [{
        'symbol': symbols[i],
        'data': results[i],
        'success': results[i] is not None
    } for i in range(len(symbols))]

# 主程序类
class TradingSignalBot:
    def __init__(self, config: Config):
        self.config = config
        self.signal_manager = SignalManager()
        self.keyboard_handler = KeyboardHandler()
        self.alert_manager = AlertManager()
        self.kline_collector = BinanceKlineCollector(config.PROXY)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        self.mouse_operator = MouseOperator()  # 新增
        self.ema_atr_operator = EmaAtrManager()
        self.play_operator = PlaySound()

        self.running = False
        self.last_display_time = time.time()
        self.last_status_str = ""
        self.is_scanning = False
        self.last_scan_time: Optional[datetime] = None

        self.sound_d = {}
        if os.path.exists(self.config.API_KEY_SECRET_FILE_PATH):
            from really import xxt
            self.times = xxt()
    async def run(self):
        """运行主程序"""
        self.running = True

        # 显示初始状态
        display_status()

        # 启动键盘监听
        self.keyboard_handler.start()

        if self.config.SCAN_ON_START:
            # 启动时立即执行一次扫描
            logger.info("🚀 执行首次扫描")
            await self.process_cycle(un_check=True)

        # 启动主循环
        try:
            await self.main_loop()
        except KeyboardInterrupt:
            logger.info("程序被用户中断")
        finally:

            await self.shutdown()

    async def shutdown(self):
        """关闭程序"""
        self.running = False
        self.keyboard_handler.stop()
        self.alert_manager.stop_beep()
        self.executor.shutdown(wait=False)
        logger.info("程序已关闭")

    async def main_loop(self):
        """主循环"""
        logger.info("程序启动")

        while self.running:
            try:
                await self.process_cycle()
            except Exception as e:
                logger.error(f"主循环错误: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(1)

    async def process_cycle(self,un_check=False):
        """处理每个周期"""
        now = datetime.datetime.now()

        # 处理键盘事件
        await self.handle_keyboard_events()
        if un_check:
            # 检查是否需要扫描
            check = True
        else:
            check = self.should_scan(now)

        if check:
            await self.perform_scan(now)
            url = 'https://fapi.binance.com/fapi/v1/ping'
            res = requests.get(url=url, proxies=self.config.PROXY_D)
            logger.info(f'本次扫描权重占用{res.headers.get("x-mbx-used-weight-1m")} / {self.config.RATELIMIT} ')
            await self.log_memory_usage()

        # 显示状态 - 实时更新
        current_time = time.time()
        if current_time - self.last_display_time >= 0.1:
            self.display_status_info(now,self.times)
            self.last_display_time = current_time

        await asyncio.sleep(0.2)

    async def log_memory_usage(self):
        """记录内存使用情况"""
        memory_mb = self.kline_collector.get_cache_memory_mb()
        logger.info(f"💾 内存缓存占用: {memory_mb:.2f} MB")

        # 如果需要详细信息
        if self.config.SCAN_INTERVALS_DEBUG:
            stats = self.kline_collector.get_cache_memory_stats()
            logger.debug(f"内存缓存详情: {stats['total_items']} 个对象, 总计 {stats['total_mb']:.2f} MB")

    def should_scan(self, now: datetime) -> bool:
        """判断是否应该扫描"""
        if self.config.SCAN_INTERVALS[0] is not None:
            if now.hour not in self.config.SCAN_INTERVALS[0]:
                return False
            else:
                if now.minute not in self.config.SCAN_INTERVALS[1]:
                    return False
        else:
            if now.minute not in self.config.SCAN_INTERVALS[1]:
                return False

        # 检查是否正在扫描中
        if self.is_scanning:
            return False

        # 避免重复扫描（按分钟，不是按秒）
        if self.last_scan_time and now.minute == self.last_scan_time.minute:
            return False
        if isinstance(self.config.SCAN_SECOND_DELAY, list):
            if now.second not in self.config.SCAN_SECOND_DELAY:
                return False
        elif isinstance(self.config.SCAN_SECOND_DELAY, int):
            if now.second != self.config.SCAN_SECOND_DELAY:
                return False

        return True

    async def perform_scan(self, scan_time: datetime):
        """执行扫描"""
        self.is_scanning = True
        logger.info(f"🔍 开始扫描 {scan_time.strftime('%H:%M')}")
        try:
            signal_symbols = await self.scan_signal_signals()
            if signal_symbols:
                # logger.info(f"🎯 发现信号: {'|*|'.join(signal_symbols)}")
                self.alert_manager.beep_alert()
                # 显示当前选择的信号
                current_symbol = self.signal_manager.get_current_symbol()
                if current_symbol:
                    position_info = self.signal_manager.get_current_position_info()
                    logger.info(f"📍 当前选择信号: {current_symbol} {position_info}")
            else:
                logger.info("📉 未发现信号")

            self.last_scan_time = scan_time

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"❌ 扫描失败: {e}")
        finally:
            self.is_scanning = False
    @async_timer_decorator
    async def scan_signal_signals(self) -> List[str]:
        """扫描信号"""
        # 保存统计信息
        self.kline_collector.save_stats_snapshot()

        # 检查是否是首次扫描
        first_scan = not hasattr(self.kline_collector, 'first_scan_done') or not self.kline_collector.first_scan_done

        # 获取币种列表
        try:
            from symbol_manager import SymbolManager
            manager = SymbolManager(self.config.MIN_VOLUME)
            symbols = manager.get_top_gainers_symbols(*self.config.SYMBOLS_RANGE)
        except ImportError:
            logger.warning("import出错，使用示例币种")
            symbols = ['BTCUSDT']

        # 并发获取数据
        d = {}
        for i in self.config.KLINE_INTERVAL_SORT:
            # 根据是否首次扫描决定是否使用缓存
            use_cache = not first_scan

            # 修改 fetch_all_kline 函数也需要传入 use_cache 参数
            results_aw = await fetch_all_kline(
                symbols,
                i,
                self.config.KLINE_LIMIT,
                self.config.MAX_RETRIES,
                self.kline_collector,
                use_cache  # 新增参数
            )
            d.update({i: results_aw})
        data_legal_length = (len(d.get(self.config.KLINE_INTERVAL_SORT[0])))

        # 如果是首次扫描，标记已完成
        if first_scan:
            self.kline_collector.first_scan_done = True
            # logger.info("✅ 首次扫描完成，已缓存所有K线数据，后续将使用增量更新")

        # 打印本次扫描的流量统计
        total_mb = self.kline_collector.total_bytes / (1024 * 1024)
        once_mb = (self.kline_collector.total_bytes - self.kline_collector.before_bytes) / (1024 * 1024)
        logger.info(
            f"📊 本次扫描流量: 请求 {self.kline_collector.request_count - self.kline_collector.before_request_count} 次 | "
            f"本次接收数据: {once_mb:.2f} MB | "
            f"运行累计流量：{total_mb:.2f} MB | "
            f"获得{data_legal_length} / {self.config.SYMBOLS_RANGE[1]} 品种数据")

        # 检测信号
        signal_d = {}
        for i in symbols:
            signal_d.update({i: [0, None]})
        signal_symbols = []
        for interval, results in d.items():
            for result in results:
                if result['success']:
                    # 检测信号，自动记录且检查重复
                    has_signal = detect_signal(
                        interval,
                        result,
                    )
                    if has_signal[0]:
                        n = signal_d.get(result['symbol'])[0] + has_signal[0]
                        signal_d.update({result['symbol']: [n, result]})
                        self.sound_d.update({result['symbol']: has_signal[1]})

        count = len(self.config.KLINE_INTERVAL)
        for k, v in signal_d.items():
            if v[0] >= count or v[0] <= -count:
                if v[0] >=count:
                    position_side = 'L'
                else:
                    position_side = 'S'
                self.recorder(result=v[1],position_side=position_side, record_signal=self.config.RECORDER_AVAILABLE)
                if '\u4e00' <= k <= '\u9fff':
                    logger.debug(f'已删除中文品种{k}')
                else:
                    signal_symbols.append(k)

        # 更新信号管理器
        self.signal_manager.update_signals(signal_symbols)
        return signal_symbols

    def recorder(self,result: dict , position_side:str ,record_signal: bool = True, check_duplicate: bool = True):
        # 如果有信号且需要记录

        if record_signal and self.config.RECORDER_AVAILABLE:
            try:
                # 获取开仓价格（使用latest['close']） 即前一根K线的收盘价作为当前开仓价格

                # 获取当前K线的open_time（当前正在运行的K线的开始时间）
                # kline_data.iloc[-1] 是当前正在运行的K线
                current_kline = result['data'].iloc[-1]

                # 转换时间戳为北京时间
                # 币安K线数据中的open_time是毫秒时间戳（Unix毫秒）
                timestamp_ms = current_kline['open_time']

                # 转换为秒（保留小数）
                timestamp_seconds = timestamp_ms / 1000.0

                # 创建UTC时间
                utc_time = datetime.datetime.fromtimestamp(timestamp_seconds, tz=self.config.UTC_TZ)

                # 转换为北京时间
                beijing_time = utc_time.astimezone(self.config.BEIJING_TZ)

                # 格式化为字符串
                time_str = beijing_time.strftime("%Y/%m/%d %H:%M:%S")

                # 调试信息：打印时间转换结果
                # logger.debug(f"时间转换: timestamp_ms={timestamp_ms}, "
                #              f"UTC={utc_time.strftime('%Y/%m/%d %H:%M:%S')}, "
                #              f"Beijing={time_str}")

                # 记录信号（返回是否成功）
                signal_params = {
                    'symbol': result['symbol'],
                    'interval': self.config.KLINE_INTERVAL_SORT[-1],
                    'position_side': position_side,
                    'open_price': result['data'].iloc[-2]['close'],
                    'time_str': time_str,  # 使用K线开始时间的北京时间
                    'check_duplicate': check_duplicate,
                }

                success, message = self.config.signal_recorder.add_signal(**signal_params)
                if self.config.RECORDER_LOGGER:
                    if not success:
                        # 记录重复信号信息
                        logger.debug(f"重复信号: {message}")
                    else:
                        # 记录成功信息
                        logger.debug(f"✅ 已记录信号: {result['symbol']} 时间: {time_str} 价格: {result['data'].iloc[-2]['close']}")
                        pass
            except Exception as e:
                logger.error(f"❌ 记录信号失败: {e}")
                # 调试信息：打印异常详情
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")

                # 如果时间转换失败，尝试使用当前时间作为备选
                try:
                    backup_time_str = datetime.datetime.now(self.config.BEIJING_TZ).strftime("%Y/%m/%d %H:%M:%S")
                    logger.warning(f"使用备选时间: {backup_time_str}")

                    # 使用当前时间重新尝试记录
                    success, message = self.config.signal_recorder.add_signal(
                        symbol=result['symbol'],
                        interval=self.config.KLINE_INTERVAL_SORT[-1],
                        open_price=result['data'].iloc[-2]['close'],
                        time_str=backup_time_str,
                        check_duplicate=check_duplicate
                    )

                    if success:
                        logger.debug(f"✅ 使用备选时间记录成功: {result['symbol']}")

                except Exception as e2:
                    logger.error(f"❌ 备选时间记录也失败: {e2}")

    async def handle_keyboard_events(self):
        """处理键盘事件"""
        try:
            if self.keyboard_handler.key_press_queue.empty():
                return

            event = self.keyboard_handler.key_press_queue.get_nowait()

            if event == 'execute_next':
                await self.execute_and_move_next()

            elif event == 'execute_previous':
                await self.execute_and_move_previous()

        except queue.Empty:
            pass
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"键盘事件处理错误: {e}")

    async def execute_and_move_next(self):
        """执行当前信号并移动到下一个"""
        if not self.signal_manager.has_signals():
            logger.warning("⚠️ 没有可执行的信号")
            return

        result = self.signal_manager.execute_and_move_next()
        if not result:
            return

        executed_symbol = result['executed']
        move = result['moved']
        # 总是执行鼠标操作（无论是否移动）
        success = await self._perform_mouse_operation(executed_symbol)
        if self.config.PLAY_SOUND:
            if self.sound_d.get(executed_symbol) =='做多':
                threading.Thread(target=self.play_operator.play_sound_for_LONG(), daemon=True).start()
            else:
                threading.Thread(target=self.play_operator.play_sound_for_SHORT(), daemon=True).start()

        if success:
            if move:
                next_symbol = result['next']
                logger.info(f"✅ 已激活: {executed_symbol} ➡️ 下一个将切换到: {next_symbol}")
            else:
                logger.info(f"✅ {executed_symbol} 📍 已是最后一个")
        else:
            logger.error(f"❌ 执行失败: {executed_symbol}")

    async def execute_and_move_previous(self):
        """执行当前信号并移动到上一个"""
        if not self.signal_manager.has_signals():
            logger.warning("⚠️ 没有可执行的信号")
            return

        result = self.signal_manager.execute_and_move_previous()
        if not result:
            return

        executed_symbol = result['executed']
        move = result['moved']

        # 总是执行鼠标操作（无论是否移动）
        success = await self._perform_mouse_operation(executed_symbol)
        if self.config.PLAY_SOUND:
            if self.sound_d.get(executed_symbol) =='做多':
                threading.Thread(target=self.play_operator.play_sound_for_LONG(), daemon=True).start()

            else:
                threading.Thread(target=self.play_operator.play_sound_for_SHORT(), daemon=True).start()

        if success:
            if move:
                prev_symbol = result['prev']
                logger.info(f"✅ 已激活: {executed_symbol} ➡️ 下一个将切换到: {prev_symbol}")
            else:
                logger.info(f"✅ 已执行: {executed_symbol} 📍 已是第一个")
        else:
            logger.error(f"❌ 执行失败: {executed_symbol}")

    async def _perform_mouse_operation(self, symbol: str) -> bool:
        """执行鼠标操作"""
        try:
            # 在线程池中执行鼠标操作
            success = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.mouse_operator.perform_operations(symbol)  # 使用 MouseOperator
            )
            return success
        except Exception as e:
            logger.error(f"鼠标操作异常: {e}")
            return False

    def display_status_info(self, now: datetime, times: float):
        """显示状态信息
            times  次数"""
        current_time_str = now.strftime("%H:%M:%S")

        # 获取当前信号信息
        current_symbol = self.signal_manager.get_current_symbol()
        position_info = self.signal_manager.get_current_position_info()

        if self.is_scanning:
            status_str = f"🔍 [{current_time_str}] 正在扫描中..."
        elif current_symbol:
            # 检查是否已执行
            is_executed = self.signal_manager.is_current_executed()
            executed_status = "✅" if is_executed else "⏳"

            # 计算下次扫描时间
            next_scan = self.calculate_next_scan_time(now)
            time_until = next_scan - now
            total_seconds = int(time_until.total_seconds())
            if total_seconds > 0:
                mins, secs = divmod(total_seconds, 60)
                countdown = f"{mins:02d}:{secs:02d}"
                status_str = f"{executed_status} [{current_time_str}] 当前: {current_symbol} {position_info} | 下次扫描倒计时: {countdown} | 距离\033[32m{self.config.TARGET}\033[0mUSDT目标还剩\033[33m{times}\033[0m次\033[34m{(self.config.RATIO-1):.1%}\033[0m的复利"
            else:
                status_str = f"{executed_status} [{current_time_str}] 当前: {current_symbol} {position_info} | 即将扫描..."
        else:
            # 计算下次扫描时间
            next_scan = self.calculate_next_scan_time(now)
            time_until = next_scan - now
            total_seconds = int(time_until.total_seconds())
            if total_seconds > 0:
                mins, secs = divmod(total_seconds, 60)
                countdown = f"{mins:02d}:{secs:02d}"
                status_str = f"📊 [{current_time_str}]  | 下次扫描: {countdown} | 距离\033[32m{self.config.TARGET}\033[0mUSDT目标还剩\033[33m{times}\033[0m次\033[34m{(self.config.RATIO-1):.1%}\033[0m的复利"
            else:
                status_str = f"📊 [{current_time_str}]  | 即将扫描..."

        # 只有当字符串变化时才更新显示，减少闪烁
        if status_str != self.last_status_str:
            print(f"\r{status_str}", end="", flush=True)
            self.last_status_str = status_str

    def calculate_next_scan_time(self, now: datetime) -> datetime:
        """计算下次扫描时间"""
        current_minute = now.minute
        if self.config.SCAN_INTERVALS[0] is None:
            # 找到下一个扫描时间点
            for interval in sorted(self.config.SCAN_INTERVALS[1]):
                if interval > current_minute:
                    next_time = now.replace(
                        minute=interval,
                        second=min(self.config.SCAN_SECOND_DELAY),
                        microsecond=0
                    )
                    return next_time
            # 如果当前时间已过所有扫描点，使用下一个小时的第一个扫描点
            next_hour_time = now + datetime.timedelta(hours=1)
            next_time = next_hour_time.replace(
                minute=min(self.config.SCAN_INTERVALS[1]),
                second=min(self.config.SCAN_SECOND_DELAY),
                microsecond=0
            )
            return next_time
        else:  # 情况2：有小时限制的扫描
            current_hour = now.hour
            hour_points = sorted(self.config.SCAN_INTERVALS[0])
            minute_points = self.config.SCAN_INTERVALS[1]
            # 在当前天内查找
            for hour in hour_points:
                if hour > current_hour:
                    next_time = now.replace(
                        hour=hour,
                        minute=min(minute_points),
                        second=min(self.config.SCAN_SECOND_DELAY),
                        microsecond=0
                    )
                    return next_time
            # 如果当前时间已过所有扫描点，使用第二天的第一个扫描点
            # 创建一个明天的日期对象
            tomorrow = now + datetime.timedelta(days=1)
            next_time = tomorrow.replace(
                hour=min(hour_points),
                minute=min(minute_points),
                second=min(self.config.SCAN_SECOND_DELAY),
                microsecond=0
            )
            return next_time
# 主函数
async def main(config):
    bot = TradingSignalBot(config)
    await bot.run()


if __name__ == '__main__':
    # 配置日志
    config = Config()

    # 配置根日志 - 设置为 WARNING 减少第三方库的干扰
    logging.basicConfig(
        level=logging.WARNING,  # 根日志设为 WARNING，屏蔽第三方库的 DEBUG
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    local_modules = []
    for file in os.listdir('.'):
        if file.endswith('.py') and not file.startswith('__'):
            module_name = file[:-3]  # 去掉 .py
            local_modules.append(module_name)

    # 添加 __main__
    local_modules.append('__main__')
    level = logging.DEBUG if config.SCAN_INTERVALS_DEBUG else logging.INFO

    # 一键设置所有本地模块的日志级别
    for module in local_modules:
        logging.getLogger(module).setLevel(level)

    # 屏蔽第三方库
    for module in ['aiohttp', 'urllib3', 'asyncio', 'binance', 'requests']:
        logging.getLogger(module).setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    try:
        asyncio.run(main(config))
    except KeyboardInterrupt:
        logger.info("程序已退出")
