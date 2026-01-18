from config import Config
import pandas as pd
class EmaAtrManager:
    def __init__(self):
        pass
    def calculate_ema(self, prices, period=60):
        """
        计算EMA60（指数移动平均线）

        Args:
            prices: 价格列表
            period: EMA周期，默认为60

        Returns:
            EMA60值的列表，前period-1个为None
        """
        if len(prices) < period:
            return []

        alpha = 2 / (period + 1)  # 平滑系数
        ema = [None] * len(prices)

        # 初始SMA
        sma_init = sum(prices[:period]) / period
        ema[period - 1] = sma_init

        # 递归计算EMA
        for i in range(period, len(prices)):
            ema[i] = prices[i] * alpha + ema[i - 1] * (1 - alpha)

        return ema

    def calculate_atr(self, klines, period=14):
        """
        计算ATR（平均真实波幅）

        Args:
            klines: K线数据列表
            period: ATR周期，默认为14

        Returns:
            ATR值的列表
        """
        if len(klines) < period + 1:
            return []

        tr_values = []
        # 计算每个K线的真实波幅（TR）
        for i in range(1, len(klines)):
            high = float(klines[i][2])
            low = float(klines[i][3])
            prev_close = float(klines[i - 1][4])

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)

        # 计算ATR（Wilder方法）
        atr = [None] * len(klines)

        # 初始ATR为前period个TR的简单平均
        atr[period] = sum(tr_values[:period]) / period

        # 递归计算后续ATR
        for i in range(period + 1, len(klines)):
            current_tr = tr_values[i - 1]
            atr[i] = ((period - 1) * atr[i - 1] + current_tr) / period

        return atr

    def get_current_ema60_atr(self, symbol=None, interval='1h',limit=499,klines=None):
        """
        获取当前EMA60和ATR值

        Args:
            symbol: 交易对
            interval: K线周期

        Returns:
            字典包含当前EMA60、ATR和收盘价
        """
        # 获取足够的数据：EMA60需要60条，ATR需要更多一些

        try:
            # 处理klines参数：支持list和DataFrame两种格式
            if klines is not None:
                if isinstance(klines, pd.DataFrame):
                    # DataFrame格式，检查是否有足够数据
                    if klines.empty or len(klines) < 61:
                        return {"error": f"DataFrame数据不足，需要至少60条K线，当前只有{len(klines)}条"}
                    # 从DataFrame提取收盘价
                    close_prices = klines['close'].astype(float).tolist()
                    # 转换为list格式供calculate_atr使用（如果需要）
                    klines_list = klines[['open_time','open', 'high', 'low', 'close']].values.tolist()
                else:
                    # 原始list格式
                    if len(klines) < 61:
                        return {"error": f"数据不足，需要至少60条K线，当前只有{len(klines)}条"}
                    close_prices = [float(k[4]) for k in klines]
                    klines_list = klines
            else:
                # 从API获取数据
                klines_raw = Config.UM_CLIENT.klines(
                    symbol=symbol,
                    interval=interval,
                    limit=limit
                )

                if len(klines_raw) < 61:
                    return {"error": f"API数据不足，需要至少60条K线，当前只有{len(klines_raw)}条"}

                close_prices = [float(k[4]) for k in klines_raw]
                klines_list = klines_raw

            # 计算EMA60
            ema60_values = self.calculate_ema(close_prices, 60)
            current_ema60 = ema60_values[-1] if ema60_values else None
            # 计算ATR
            atr_values = self.calculate_atr(klines_list, 14)
            current_atr = atr_values[-1] if atr_values else None

            # 当前价格
            current_price = close_prices[-1]
            latest_price = close_prices[-2]
            return {
                "symbol": symbol,
                "interval": interval,
                "current_price": current_price,
                "latest_price":latest_price,
                "ema60": current_ema60,
                "atr": current_atr,
                "price_vs_ema": "above" if current_ema60 and current_price > current_ema60 else "below",
                "timestamp": klines_list[-1][0]
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def run(self,symbol,klines=None,interval_check=None):
        """
        运行分析器
        """
        # 这里可以添加你想要分析的交易对
        if klines is not None:
            result = self.get_current_ema60_atr(symbol=symbol,klines=klines)
        else:
            result = self.get_current_ema60_atr(symbol=symbol)
        result: dict

        if "error" in result:
            print(f"  错误: {result['error']}")
            return False
        if Config.EMA_ATR_INFO:
            print(f"{result['symbol']}  {interval_check}:")
            print(f"  当前价格: ${result['current_price']:.2f}")
            print(f"  EMA60: ${result['ema60']:.2f}" if result['ema60'] else "  EMA60: 无法计算")
            print(f"  ATR: {result['atr']:.4f}" if result['atr'] else "  ATR: 无法计算")

        if result['ema60']:
            diff_percent = ((result['current_price'] - result['ema60']) / result['ema60']) * 100
            position = "\033[92m高于\033[0m" if diff_percent > 0 else "\033[91m低于\033[0m"
            # print(f"{symbol} {interval_check}:  价格{position}EMA60: {abs(diff_percent):.2f}%")
            # if abs(result['latest_price'] - result['ema60']) < 2 * result['atr']:
            if result['latest_price'] >= result['ema60']:

                return True
            else:
                return False

if __name__ == '__main__':
    import time

    start_time = time.time()

    manager = EmaAtrManager()

    # 方式1：分析多个交易对
    manager.run('BTCUSDT')

    end_time = time.time()
    print(f"\n执行时间: {end_time - start_time:.2f}秒")