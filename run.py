import asyncio
from typing import List, Optional, Dict, Any
import logging
import time
from datetime import datetime
import queue
import concurrent.futures
from .collector import BinanceKlineCollector
from .detect import detect_signal
from .config import Config, display_status
from .alert_manager import AlertManager
from .keyboard_handler import KeyboardHandler
from .signal_manager import SignalManager
from .mouse_operator import MouseOperator


async def fetch_all_kline(symbols: List[str], interval: str, limit: int, proxy: str, max_retries: int) -> List[Dict[str, Any]]:
    """并发获取所有币种K线数据"""
    collector = BinanceKlineCollector(proxy)
    tasks = [collector.fetch_kline(symbol, interval, limit, max_retries) for symbol in symbols]
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
        self.mouse_operator = MouseOperator(config.CLICK_COORDINATES)  # 新增

        self.running = False
        self.last_display_time = time.time()
        self.last_status_str = ""
        self.is_scanning = False
        self.last_scan_time: Optional[datetime] = None

    async def run(self):
        """运行主程序"""
        self.running = True

        # 显示初始状态
        display_status()

        # 启动键盘监听
        self.keyboard_handler.start()

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

    async def process_cycle(self):
        """处理每个周期"""
        now = datetime.now()

        # 处理键盘事件
        await self.handle_keyboard_events()

        # 检查是否需要扫描
        if self.should_scan(now):
            await self.perform_scan(now)

        # 显示状态 - 实时更新
        current_time = time.time()
        if current_time - self.last_display_time >= 0.1:
            self.display_status_info(now)
            self.last_display_time = current_time

        await asyncio.sleep(0.2)

    def should_scan(self, now: datetime) -> bool:
        """判断是否应该扫描"""
        if self.config.SCAN_INTERVALS_DEBUG:
            if self.last_scan_time and (now - self.last_scan_time).total_seconds() < 60:
                return False
        else:
            # 检查时间间隔
            if now.minute not in self.config.SCAN_INTERVALS:
                return False

            # 检查是否正在扫描中
            if self.is_scanning:
                return False

            # 避免重复扫描（按分钟，不是按秒）
            if self.last_scan_time and now.minute == self.last_scan_time.minute:
                return False

            # 避免重复扫描
            if self.last_scan_time and (now - self.last_scan_time).total_seconds() < 57:
                return False

            if isinstance(self.config.SCAN_SECOND_DELAY,list):
                if now.second not in self.config.SCAN_SECOND_DELAY:
                    return False
            elif isinstance(self.config.SCAN_SECOND_DELAY,int):
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
                logger.info(f"🎯 发现信号: {'|*|'.join(signal_symbols)}")
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
            logger.error(f"❌ 扫描失败: {e}")
        finally:
            self.is_scanning = False

    async def scan_signal_signals(self) -> List[str]:
        """扫描信号"""
        # 获取币种列表
        try:
            from V1_0.symbol_manager import SymbolManager
            manager = SymbolManager(self.config.MIN_VOLUME)
            symbols = manager.get_top_gainers_symbols(*self.config.SYMBOLS_RANGE)
        except ImportError:
            logger.warning("使用示例币种")
            symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'DOGEUSDT']

        # 并发获取数据
        results = await fetch_all_kline(
            symbols,
            self.config.KLINE_INTERVAL,
            self.config.KLINE_LIMIT,
            self.config.PROXY,
            self.config.MAX_RETRIES
        )

        # 检测信号
        signal_symbols = []
        for result in results:
            if result['success']:
                # 检测信号，自动记录且检查重复
                has_signal = detect_signal(
                    result['data'],
                    result['symbol'],
                    record_signal=True,
                    check_duplicate=True
                )
                if has_signal:
                    signal_symbols.append(result['symbol'])

        # 更新信号管理器
        self.signal_manager.update_signals(signal_symbols)

        return signal_symbols

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

    def display_status_info(self, now: datetime):
        """显示状态信息"""
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
                status_str = f"{executed_status} [{current_time_str}] 当前: {current_symbol} {position_info} | 下次扫描倒计时: {countdown}"
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
                status_str = f"📊 [{current_time_str}]  | 下次扫描: {countdown}"
            else:
                status_str = f"📊 [{current_time_str}]  | 即将扫描..."

        # 只有当字符串变化时才更新显示，减少闪烁
        if status_str != self.last_status_str:
            print(f"\r{status_str}", end="", flush=True)
            self.last_status_str = status_str

    def calculate_next_scan_time(self, now: datetime) -> datetime:
        """计算下次扫描时间"""
        current_minute = now.minute

        # 找到下一个扫描时间点
        for interval in sorted(self.config.SCAN_INTERVALS):
            if interval > current_minute:
                next_time = now.replace(
                    minute=interval,
                    second=0,
                    microsecond=0
                )
                return next_time

        # 如果当前时间已过所有扫描点，使用下一个小时的第一个扫描点
        next_hour = (now.hour + 1) % 24
        next_time = now.replace(
            hour=next_hour,
            minute=min(self.config.SCAN_INTERVALS),
            second=0,
            microsecond=0
        )
        return next_time


# 主函数
async def main():
    config = Config()
    bot = TradingSignalBot(config)
    await bot.run()


if __name__ == '__main__':
    # 配置日志

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序已退出")
