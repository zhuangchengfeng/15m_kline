
"""
symbol_manager_fixed.py - 币安交易对管理器（修复版）
修复可能的bug，添加异常处理
"""

from binance.um_futures import UMFutures
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pytz
import time

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# 北京时间时区
BEIJING_TZ = pytz.timezone('Asia/Shanghai')


class SymbolManager:
    def __init__(self, min_volume: float = 10000000):
        """
        初始化币安交易分析器
        
        Args:
            proxies: 代理设置
            min_volume: 最小成交额筛选条件，默认1000万USDT
        """
        self.proxies = {
            "http": "http://127.0.0.1:7890",
            "https": "http://127.0.0.1:7890"
        }
        self.min_volume = min_volume
        
        try:
            self.client = UMFutures(proxies=self.proxies)
            logger.info(f"✅ 交易对管理器初始化成功,最小成交量为{min_volume}")
        except Exception as e:
            logger.error(f"❌ 交易对管理器初始化失败: {e}")
            raise
        
        self.trading_symbols = []
        self.filtered_symbols = []
        self.last_update_time = None
    def get_trading_symbols(self, max_retries: int = 3) -> List[str]:
        """
        获取所有可交易状态的USDT交易对
        
        Args:
            max_retries: 最大重试次数
            
        Returns:
            可交易状态的所有USDT交易对列表
        """
        self.trading_symbols = []
        
        for attempt in range(max_retries):
            try:
                exchange_info = self.client.exchange_info()
                symbols = exchange_info.get('symbols', [])
                
                for symbol_info in symbols:
                    try:
                        symbol = symbol_info.get('symbol', '')
                        status = symbol_info.get('status', '')
                        quote_asset = symbol_info.get('quoteAsset', '')
                        
                        # 检查是否为可交易的USDT交易对
                        if (status == 'TRADING' and 
                            symbol.endswith('USDT') and 
                            quote_asset == 'USDT'):
                            self.trading_symbols.append(symbol)
                    except Exception as e:
                        logger.debug(f"处理交易对信息时出错: {e}")
                        continue
                
                logger.info(f"✅ 获取到 {len(self.trading_symbols)} 个可交易USDT交易对")
                self.last_update_time = datetime.now(BEIJING_TZ)
                return self.trading_symbols
                
            except Exception as e:
                logger.warning(f"获取交易对信息失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避
                else:
                    logger.error(f"获取交易对信息最终失败: {e}")
                    return []
    
    def get_24hr_trading_data(self, max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        获取24小时交易数据，并筛选符合成交额条件的交易对
        
        Returns:
            筛选后的交易对数据列表，包含symbol、百分比、成交额
        """
        if not self.trading_symbols:
            self.get_trading_symbols()
        
        filtered_data = []
        for attempt in range(max_retries):
            try:
                tickers = self.client.ticker_24hr_price_change()  #x-mbx-used-weight-1m 40
                
                # 转换为字典便于快速查找
                ticker_dict = {ticker.get('symbol'): ticker for ticker in tickers}
                
                for symbol in self.trading_symbols:
                    ticker = ticker_dict.get(symbol)
                    if ticker:
                        try:
                            quote_volume = float(ticker.get('quoteVolume', 0))
                            
                            # 筛选成交额大于阈值的交易对
                            if quote_volume >= self.min_volume:
                                data = {
                                    'symbol': symbol,
                                    'price_change_percent': float(ticker.get('priceChangePercent', 0)),
                                    'quote_volume': quote_volume,
                                    'last_price': float(ticker.get('lastPrice', 0)),
                                    'high_price': float(ticker.get('highPrice', 0)),
                                    'low_price': float(ticker.get('lowPrice', 0)),
                                    'volume': float(ticker.get('volume', 0))
                                }
                                filtered_data.append(data)
                        except (ValueError, TypeError) as e:
                            logger.debug(f"处理交易对 {symbol} 数据时出错: {e}")
                            continue
                
                # 按成交额降序排序
                filtered_data.sort(key=lambda x: x['quote_volume'], reverse=True)
                
                logger.info(f"✅ 筛选到 {len(filtered_data)} 个成交额大于 {self.min_volume:,.0f} USDT的交易对")
                return filtered_data
                
            except Exception as e:
                logger.warning(f"获取24小时交易数据失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"获取24小时交易数据最终失败: {e}")
                    return []
    
    def get_filtered_symbols(self, min_volume: Optional[float] = None) -> List[str]:
        """
        获取筛选后的交易对符号列表
        
        Args:
            min_volume: 最小成交额，如果不指定则使用初始化时的设置
            
        Returns:
            筛选后的交易对符号列表
        """
        if min_volume is not None:
            self.min_volume = min_volume
        
        trading_data = self.get_24hr_trading_data()
        self.filtered_symbols = [item['symbol'] for item in trading_data]
        
        return self.filtered_symbols
    
    def get_symbols_with_volume(self, min_volume: Optional[float] = None) -> Dict[str, float]:
        """
        获取交易对及其成交额的字典
        
        Args:
            min_volume: 最小成交额
            
        Returns:
            {symbol: volume} 字典
        """
        if min_volume is not None:
            self.min_volume = min_volume
        
        trading_data = self.get_24hr_trading_data()
        return {item['symbol']: item['quote_volume'] for item in trading_data}
    
    def get_top_symbols(self, top_n: int = 50) -> List[str]:
        """
        获取成交额最高的N个交易对
        
        Args:
            top_n: 要获取的数量
            
        Returns:
            成交额最高的交易对列表
        """
        trading_data = self.get_24hr_trading_data()
        return [item['symbol'] for item in trading_data[:top_n]]
    
    def refresh(self):
        """刷新数据"""
        self.trading_symbols = []
        self.filtered_symbols = []
        self.get_trading_symbols()

    def get_top_gainers_symbols(self, start_rank: int = 10, end_rank: int = 19) -> List[str]:
        """
        获取涨幅榜指定排名区间的交易对名称列表
        """
        try:
            # 获取数据
            tickers = self.get_24hr_trading_data()
            # 筛选并排序
            usdt_tickers = []
            for ticker in tickers:
                symbol = ticker.get('symbol', '')
                if symbol.endswith('USDT'):
                    try:
                        price_change = float(ticker.get('price_change_percent', 0))
                        usdt_tickers.append((symbol, price_change))
                    except:
                        continue

            # 按涨幅排序
            usdt_tickers.sort(key=lambda x: x[1], reverse=True)
            # 提取指定排名区间的symbol
            start_idx = max(0, start_rank - 1)
            end_idx = min(end_rank, len(usdt_tickers))

            return [symbol for symbol, _ in usdt_tickers[start_idx:end_idx]]

        except Exception as e:
            logger.error(f"获取涨幅榜失败: {e}")
            return []
def get_current_beijing_time() -> str:
    """
    获取当前北京时间
    
    Returns:
        格式化的北京时间字符串: "2025-12-13 19:43:16"
    """
    now = datetime.now(BEIJING_TZ)
    return now.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    # 使用示例
    print("=" * 60)
    print("测试SymbolManager")
    print("=" * 60)
    
    manager = SymbolManager(min_volume=500)  # 1千万USDT
        
    gainers = (manager.get_top_gainers_symbols(5,15))
    print(gainers)
