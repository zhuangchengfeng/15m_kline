import os
import json
import asyncio
import aiohttp
import sys
from datetime import datetime
from config import Config
from collections import defaultdict
import warnings

# 忽略特定警告
warnings.filterwarnings("ignore", message="Event loop is closed")


class AsyncReporter:
    def __init__(self):
        """
        初始化异步报告器
        """
        self.base_url = "https://fapi.binance.com"
        self.semaphore = asyncio.Semaphore(20)  # 控制并发数
        self.proxy = 'http://127.0.0.1:7890'  # 代理配置
        self._connector = None
        self._session = None

    async def get_session(self):
        """获取或创建session"""
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(ssl=False, force_close=True)
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout
            )
        return self._session

    async def close(self):
        """手动关闭session和connector"""
        try:
            if self._session and not self._session.closed:
                await self._session.close()
        except:
            pass

        try:
            if self._connector and not self._connector.closed:
                await self._connector.close()
        except:
            pass

    def time_to_ms(self, time_str):
        """将时间字符串转换为毫秒时间戳"""
        dt = datetime.strptime(time_str, "%Y/%m/%d %H:%M:%S")
        return int(dt.timestamp() * 1000)

    def time_str_to_dt(self, time_str):
        """将时间字符串转换为datetime对象"""
        return datetime.strptime(time_str, "%Y/%m/%d %H:%M:%S")

    def calculate_rates(self, open_price, high_price, low_price):
        """计算最高和最低的涨跌幅百分比"""
        if open_price == 0:
            return "0.00%", "0.00%"
        up_rate = ((high_price - open_price) / open_price) * 100
        down_rate = ((low_price - open_price) / open_price) * 100
        return f"{up_rate:+.2f}%", f"{down_rate:+.2f}%"

    async def fetch_klines(self, session, symbol, interval, start_time, end_time):
        """异步获取单个K线数据"""
        url = f"{self.base_url}/fapi/v1/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': start_time,
            'endTime': end_time,
        }
        async with self.semaphore:
            try:
                async with session.get(url, params=params, proxy=self.proxy) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        print(f"警告: {symbol} 请求失败，状态码: {response.status}")
                        return None
            except Exception as e:
                print(f"错误: {symbol} 请求异常 - {e}")
                return None

    async def process_signal(self, session, symbol, signal):
        """处理单个信号"""
        try:
            # 检查是否需要更新
            current_time = datetime.now()
            after_close_time_dt = self.time_str_to_dt(signal["after_close_time"])
            update_time = signal.get("update_time")

            # 如果存在update_time且大于after_close_time，则跳过
            if update_time:
                update_time_dt = self.time_str_to_dt(update_time)
                if update_time_dt > after_close_time_dt:
                    return None  # 静默跳过，不打印

            # 需要更新，获取数据
            open_time = signal["open_time"]
            interval = signal["interval"]
            open_price = signal["open_price"]
            position_side = signal.get("position_side", "UNKNOWN")
            after_close_time = signal["after_close_time"]

            start_time = self.time_to_ms(open_time)
            end_time = self.time_to_ms(after_close_time)

            klines = await self.fetch_klines(session, symbol, interval, start_time, end_time)

            if klines:
                high_prices = [float(k[2]) for k in klines]
                low_prices = [float(k[3]) for k in klines]
                max_high = max(high_prices)
                min_low = min(low_prices)

                up_rate, down_rate = self.calculate_rates(open_price, max_high, min_low)

                return {
                    **signal,
                    "after_high_price": max_high,
                    "after_low_price": min_low,
                    "rate_of_up_change": up_rate,
                    "rate_of_down_change": down_rate,
                    "update_time": current_time.strftime("%Y/%m/%d %H:%M:%S"),
                    "_symbol": symbol,
                    "_position_side": position_side
                }
            else:
                return None
        except Exception as e:
            print(f"  处理异常 {symbol}: {e}")
            return None

    async def analyze_json_file_async(self, json_file_path):
        """异步分析JSON文件"""
        current_file = os.path.join('signal_data', json_file_path)
        session = None
        try:
            with open(current_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            print(f"开始异步分析 {json_file_path} ...")
            if self.proxy:
                print(f"使用代理: {self.proxy}")

            # 获取session
            session = await self.get_session()

            tasks = []
            signal_count = 0
            need_update_count = 0

            for symbol, symbol_data in data.items():
                for signal in symbol_data.get("signals", []):
                    signal_count += 1
                    # 检查是否需要更新
                    after_close_time = signal.get("after_close_time")
                    update_time = signal.get("update_time")

                    if after_close_time and update_time:
                        try:
                            after_dt = self.time_str_to_dt(after_close_time)
                            update_dt = self.time_str_to_dt(update_time)
                            if update_dt <= after_dt:
                                need_update_count += 1
                                task = self.process_signal(session, symbol, signal)
                                tasks.append(task)
                        except:
                            need_update_count += 1
                            task = self.process_signal(session, symbol, signal)
                            tasks.append(task)
                    else:
                        need_update_count += 1
                        task = self.process_signal(session, symbol, signal)
                        tasks.append(task)

            print(f"总信号数: {signal_count}, 需要更新: {need_update_count}")

            if not tasks:
                print("没有需要更新的信号")
                return []

            # 分批处理，避免一次性太多任务
            batch_size = 20
            successful_results = []

            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)

                for r in batch_results:
                    if isinstance(r, Exception):
                        print(f"任务执行异常: {r}")
                    elif r is not None:
                        successful_results.append(r)

                # 批次间暂停一下
                if i + batch_size < len(tasks):
                    await asyncio.sleep(0.5)

            # 更新数据
            updated_count = 0
            for res in successful_results:
                symbol = res['_symbol']
                for signal in data[symbol]["signals"]:
                    if signal["open_time"] == res["open_time"]:
                        signal.update({
                            "after_high_price": res["after_high_price"],
                            "after_low_price": res["after_low_price"],
                            "rate_of_up_change": res["rate_of_up_change"],
                            "rate_of_down_change": res["rate_of_down_change"],
                            "update_time": res["update_time"]
                        })
                        updated_count += 1
                        break

            # 自动保存到原文件
            with open(current_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            print(f"\n✅ 分析完成！")
            print(f"成功更新: {updated_count}/{need_update_count}")
            print(f"数据已保存到 {current_file}")

            # 生成精简报告 - 按L和S分开排序
            if successful_results:
                print("\n" + "=" * 80)
                print("📈 信号分析精简报告")
                print("=" * 80)

                # 分离L和S信号
                l_signals = []
                s_signals = []

                for res in successful_results:
                    signal_data = {
                        "symbol": res['_symbol'],
                        "position": res['_position_side'],
                        "open_time": res["open_time"],
                        "open_price": res["open_price"],
                        "after_high": res["after_high_price"],
                        "after_low": res["after_low_price"],
                        "up_rate": res["rate_of_up_change"],
                        "down_rate": res["rate_of_down_change"]
                    }

                    if res['_position_side'].upper() == 'LONG' or res['_position_side'].upper() == 'L':
                        l_signals.append(signal_data)
                    else:
                        s_signals.append(signal_data)

                # 定义排序函数
                def up_rate_key(s):
                    try:
                        return float(s["up_rate"].rstrip('%'))
                    except:
                        return 0.0

                def down_rate_key(s):
                    try:
                        return float(s["down_rate"].rstrip('%'))
                    except:
                        return 0.0

                # 排序L信号（按上涨%从高到低）
                sorted_l = sorted(l_signals, key=up_rate_key, reverse=True)

                # 排序S信号（按下跌%从低到高，即跌幅最大的优先）
                sorted_s = sorted(s_signals, key=down_rate_key)

                # 打印表头
                print("\n{:<12} {:<8} {:<20} {:<10} {:<10} {:<10} {:<10} {:<10}".format(
                    "品种", "方向", "开盘时间", "开盘价", "最高价", "最低价", "上涨%", "下跌%"))
                print("-" * 100)

                # 打印L信号（做多）
                if sorted_l:
                    print("\n【LONG 信号 - 按上涨%从高到低】")
                    for sig in sorted_l:
                        print("{:<12} {:<8} {:<20} {:<10.6f} {:<10.6f} {:<10.6f} {:<10} {:<10}".format(
                            sig["symbol"],
                            sig["position"],
                            sig["open_time"],
                            sig["open_price"],
                            sig["after_high"],
                            sig["after_low"],
                            sig["up_rate"],
                            sig["down_rate"]
                        ))

                # 打印S信号（做空）
                if sorted_s:
                    print("\n【SHORT 信号 - 按下跌%从低到高（跌幅最大优先）】")
                    for sig in sorted_s:
                        print("{:<12} {:<8} {:<20} {:<10.6f} {:<10.6f} {:<10.6f} {:<10} {:<10}".format(
                            sig["symbol"],
                            sig["position"],
                            sig["open_time"],
                            sig["open_price"],
                            sig["after_high"],
                            sig["after_low"],
                            sig["up_rate"],
                            sig["down_rate"]
                        ))

                # 打印统计信息
                print(f"\n📊 统计信息")
                print(f"LONG信号数: {len(sorted_l)}")
                print(f"SHORT信号数: {len(sorted_s)}")
                print(f"总计: {len(successful_results)}")

            return successful_results

        except FileNotFoundError:
            print(f"错误: 找不到文件 {current_file}")
        except json.JSONDecodeError:
            print(f"错误: JSON文件格式不正确")
        except Exception as e:
            print(f"错误: {e}")
        finally:
            # 确保关闭session
            await self.close()

    async def test_proxy_connection(self):
        """测试代理连接是否正常"""
        test_url = "https://api.binance.com/api/v3/ping"
        try:
            print(2)
            session = await self.get_session()
            print(1)
            async with session.get(test_url, proxy=self.proxy, timeout=5) as response:
                if response.status == 200:
                    print("✅ 代理连接成功！")
                    return True
                else:
                    print(f"❌ 代理连接失败，状态码: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ 代理连接异常: {e}")
            return False


def main(json_file_name):
    """同步主函数"""
    # 设置Windows事件循环策略
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 创建新的事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    reporter = None
    try:
        reporter = AsyncReporter()

        loop.run_until_complete(reporter.test_proxy_connection())

        json_file = json_file_name
        loop.run_until_complete(reporter.analyze_json_file_async(json_file))

    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序执行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源
        if reporter:
            loop.run_until_complete(reporter.close())

        # 取消所有任务
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()

        # 运行事件循环一小段时间让任务取消
        if pending:
            loop.run_until_complete(asyncio.sleep(0.1))

        # 关闭事件循环
        loop.close()

        # Windows特定的修复：设置一个新的假事件循环避免警告
        if sys.platform == 'win32':
            try:
                asyncio.set_event_loop(asyncio.new_event_loop())
            except:
                pass

        print("程序退出")


if __name__ == '__main__':
    file = '2026-03-05.json'
    main(file)