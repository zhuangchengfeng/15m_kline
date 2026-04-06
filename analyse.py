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
        初始化异步报告器 - 优化版本
        """
        self.base_url = "https://fapi.binance.com"
        self.semaphore = asyncio.Semaphore(50)  # 提高并发数到50
        self.proxy = 'http://127.0.0.1:7890'  # 代理配置
        self._connector = None
        self._session = None
        self._request_count = 0  # 请求计数器

    async def get_session(self):
        """获取或创建session - 优化连接池配置"""
        if self._session is None or self._session.closed:
            # 优化连接池配置，启用连接复用
            self._connector = aiohttp.TCPConnector(
                ssl=False,
                force_close=False,  # 保持连接复用
                limit=100,  # 总连接池大小
                limit_per_host=50,  # 每个主机的最大连接数
                ttl_dns_cache=300,  # DNS缓存5分钟
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(
                total=30,
                connect=10,  # 连接超时10秒
                sock_read=15  # 读取超时15秒
            )
            # 添加请求头模拟浏览器
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Connection': 'keep-alive'
            }
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                headers=headers
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

    async def fetch_klines_range(self, session, symbol, interval, start_time, end_time):
        """获取指定时间范围的K线数据 - 优化版本，支持重试"""
        url = f"{self.base_url}/fapi/v1/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': start_time,
            'endTime': end_time,
            'limit': 1000  # 明确指定最大返回数量
        }

        async with self.semaphore:
            self._request_count += 1
            if self._request_count % 20 == 0:
                print(f"📡 已发送 {self._request_count} 个请求...")

            # 重试机制
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    async with session.get(url, params=params, proxy=self.proxy) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429:  # 限流
                            wait_time = 2 ** attempt  # 指数退避
                            print(f"⚠️ {symbol} 触发限流，等待 {wait_time} 秒后重试...")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            print(f"警告: {symbol} 请求失败，状态码: {response.status}")
                            return None
                except asyncio.TimeoutError:
                    print(f"⏱️ {symbol} 请求超时，尝试 {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                    else:
                        return None
                except Exception as e:
                    print(f"错误: {symbol} 请求异常 - {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                    else:
                        return None

            return None

    async def analyze_json_file_async(self, json_file_path):
        """异步分析JSON文件 - 优化版本，使用gather并发请求"""
        current_file = os.path.join('signal_data', json_file_path)

        try:
            with open(current_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            print(f"\n{'=' * 60}")
            print(f"📊 开始分析文件: {json_file_path}")
            print(f"{'=' * 60}")

            if self.proxy:
                print(f"🔧 使用代理: {self.proxy}")

            # ========== 第一步：收集需要更新的信号，按币种分组 ==========
            signals_by_symbol = defaultdict(list)
            signal_count = 0
            need_update_count = 0

            for symbol, symbol_data in data.items():
                for signal in symbol_data.get("signals", []):
                    signal_count += 1

                    after_close_time = signal.get("after_close_time")
                    update_time = signal.get("update_time")

                    need_update = False
                    if after_close_time and update_time:
                        try:
                            after_dt = self.time_str_to_dt(after_close_time)
                            update_dt = self.time_str_to_dt(update_time)
                            if update_dt <= after_dt:
                                need_update = True
                        except:
                            need_update = True
                    else:
                        need_update = True

                    if need_update:
                        need_update_count += 1
                        signals_by_symbol[symbol].append(signal)

            print(f"📈 总信号数: {signal_count}, 需要更新: {need_update_count}")
            print(f"🪙 涉及币种数: {len(signals_by_symbol)}")

            if not signals_by_symbol:
                print("✨ 没有需要更新的信号")
                return []

            # ========== 第二步：准备并发请求任务 ==========
            session = await self.get_session()

            # 创建任务列表
            tasks = []
            symbol_info_list = []

            for symbol, signals in signals_by_symbol.items():
                # 找出该币种所有信号的最早open_time和最晚after_close_time
                min_open_time = None
                max_after_close_time = None
                interval = signals[0]["interval"]  # 假设同一币种周期相同

                for signal in signals:
                    open_time = signal["open_time"]
                    after_close_time = signal["after_close_time"]

                    open_ms = self.time_to_ms(open_time)
                    after_ms = self.time_to_ms(after_close_time)

                    if min_open_time is None or open_ms < min_open_time:
                        min_open_time = open_ms
                    if max_after_close_time is None or after_ms > max_after_close_time:
                        max_after_close_time = after_ms

                # 创建请求任务
                task = self.fetch_klines_range(
                    session, symbol, interval, min_open_time, max_after_close_time
                )
                tasks.append(task)
                symbol_info_list.append({
                    'symbol': symbol,
                    'signals': signals,
                    'interval': interval,
                    'min_open_time': min_open_time,
                    'max_after_close_time': max_after_close_time
                })

            # ========== 第三步：并发执行所有请求 ==========
            print(f"\n🚀 开始并发请求 {len(tasks)} 个币种的K线数据...")
            print(f"⚡ 并发数限制: 50")
            start_time = datetime.now()

            klines_results = await asyncio.gather(*tasks, return_exceptions=True)

            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"✅ 所有请求完成，耗时: {elapsed:.2f} 秒")
            print(f"📡 总计发送请求: {self._request_count} 次")

            # ========== 第四步：处理所有K线数据 ==========
            print(f"\n🔄 开始处理K线数据...")
            successful_results = []
            processed_count = 0

            for i, klines in enumerate(klines_results):
                info = symbol_info_list[i]

                if klines and not isinstance(klines, Exception):
                    # 转换K线数据格式
                    kline_list = []
                    for k in klines:
                        kline_list.append({
                            "open_time": k[0],
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4])
                        })
                    kline_list.sort(key=lambda x: x["open_time"])

                    # 处理该币种的所有信号
                    for signal in info['signals']:
                        try:
                            open_time = signal["open_time"]
                            open_price = signal["open_price"]
                            after_close_time = signal["after_close_time"]
                            position_side = signal.get("position_side", "UNKNOWN")

                            start_ms = self.time_to_ms(open_time)
                            end_ms = self.time_to_ms(after_close_time)

                            # 从已获取的K线中筛选时间范围内的数据
                            filtered_klines = [
                                k for k in kline_list
                                if start_ms <= k["open_time"] < end_ms
                            ]

                            if filtered_klines:
                                max_high = max(k["high"] for k in filtered_klines)
                                min_low = min(k["low"] for k in filtered_klines)
                                up_rate, down_rate = self.calculate_rates(open_price, max_high, min_low)

                                result = {
                                    **signal,
                                    "after_high_price": max_high,
                                    "after_low_price": min_low,
                                    "rate_of_up_change": up_rate,
                                    "rate_of_down_change": down_rate,
                                    "update_time": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                                    "_symbol": info['symbol'],
                                    "_position_side": position_side
                                }
                                successful_results.append(result)
                                processed_count += 1

                                if processed_count % 50 == 0:
                                    print(f"   已处理 {processed_count}/{need_update_count} 个信号...")
                            else:
                                print(f"   ⚠️ {info['symbol']} {open_time} 时间范围内无K线数据")

                        except Exception as e:
                            print(f"   ❌ 处理异常 {info['symbol']}: {e}")
                            continue
                else:
                    print(f"   ⚠️ {info['symbol']} K线数据获取失败，跳过该币种所有信号")

            # ========== 第五步：更新原文件 ==========
            print(f"\n💾 更新JSON文件...")
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

            # 保存到原文件
            with open(current_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            print(f"\n{'=' * 60}")
            print(f"✅ 分析完成！")
            print(f"📊 成功更新: {updated_count}/{need_update_count}")
            print(f"🚀 实际请求次数: {len(klines_results)} (并发完成)")
            print(f"⏱️  总耗时: {elapsed:.2f} 秒")
            print(f"📁 数据已保存到 {current_file}")
            print(f"{'=' * 60}")

            # ========== 第六步：生成报告 ==========
            if successful_results:
                self.print_report(successful_results)

            return successful_results

        except FileNotFoundError:
            print(f"❌ 错误: 找不到文件 {current_file}")
        except json.JSONDecodeError:
            print(f"❌ 错误: JSON文件格式不正确")
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.close()

    def print_report(self, successful_results):
        """生成精简报告 - 按L和S分开排序"""
        if not successful_results:
            return

        print("\n" + "=" * 100)
        print("📈 信号分析精简报告")
        print("=" * 100)

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

            position = res['_position_side'].upper() if res['_position_side'] else ''
            if position in ['LONG', 'L']:
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
        print("\n{:<12} {:<8} {:<20} {:<12} {:<12} {:<12} {:<10} {:<10}".format(
            "品种", "方向", "开盘时间", "开盘价", "最高价", "最低价", "上涨%", "下跌%"))
        print("-" * 110)

        # 打印L信号（做多）
        if sorted_l:
            print("\n【LONG 信号 - 按上涨%从高到低】")
            for sig in sorted_l[:30]:  # 只显示前20个
                print("{:<12} {:<8} {:<20} {:<12.6f} {:<12.6f} {:<12.6f} {:<10} {:<10}".format(
                    sig["symbol"],
                    "LONG",
                    sig["open_time"],
                    sig["open_price"],
                    sig["after_high"],
                    sig["after_low"],
                    sig["up_rate"],
                    sig["down_rate"]
                ))
            if len(sorted_l) > 30:
                print(f"... 还有 {len(sorted_l) - 30} 个LONG信号未显示")

        # 打印S信号（做空）
        if sorted_s:
            print("\n【SHORT 信号 - 按下跌%从低到高（跌幅最大优先）】")
            for sig in sorted_s[:30]:  # 只显示前20个
                print("{:<12} {:<8} {:<20} {:<12.6f} {:<12.6f} {:<12.6f} {:<10} {:<10}".format(
                    sig["symbol"],
                    "SHORT",
                    sig["open_time"],
                    sig["open_price"],
                    sig["after_high"],
                    sig["after_low"],
                    sig["up_rate"],
                    sig["down_rate"]
                ))
            if len(sorted_s) > 30:
                print(f"... 还有 {len(sorted_s) - 30} 个SHORT信号未显示")

        # 打印统计信息
        print(f"\n📊 统计信息")
        print(f"LONG信号数: {len(sorted_l)}")
        print(f"SHORT信号数: {len(sorted_s)}")
        print(f"总计: {len(successful_results)}")

        # 打印最佳表现
        if sorted_l:
            best_long = sorted_l[0]
            print(f"\n🏆 最佳LONG信号: {best_long['symbol']} 上涨 {best_long['up_rate']}")
        if sorted_s:
            best_short = sorted_s[0]
            print(f"🏆 最佳SHORT信号: {best_short['symbol']} 下跌 {best_short['down_rate']}")

    async def test_proxy_connection(self):
        """测试代理连接是否正常"""
        test_url = "https://api.binance.com/api/v3/ping"
        try:
            session = await self.get_session()
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

        # 测试代理连接
        loop.run_until_complete(reporter.test_proxy_connection())

        # 执行分析
        json_file = json_file_name
        loop.run_until_complete(reporter.analyze_json_file_async(json_file))

    except KeyboardInterrupt:
        print("\n⚠️ 程序被用户中断")
    except Exception as e:
        print(f"❌ 程序执行出错: {e}")
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
            try:
                loop.run_until_complete(asyncio.sleep(0.1))
            except:
                pass

        # 关闭事件循环
        loop.close()

        # Windows特定的修复
        if sys.platform == 'win32':
            try:
                asyncio.set_event_loop(asyncio.new_event_loop())
            except:
                pass

        print("👋 程序退出")


if __name__ == '__main__':
    file = '2026-04-02.json'
    main(file)