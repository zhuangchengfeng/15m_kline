# signal_manager.py
import threading
import logging
from typing import List, Optional, Dict
import pandas as pd
# logger = logging.getLogger(__name__)
import logging
import colorlog

# 1. 创建一个处理器 (Handler)
handler = logging.StreamHandler()

# 2. 创建并配置一个带颜色的格式化器 (ColoredFormatter)
#    这里我们只给整个消息(message)配置了颜色规则，你也可以按需配置更多
formatter = colorlog.ColoredFormatter(
    '%(asctime)s - %(levelname)s - %(message_log_color)s%(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    reset=True,
    log_colors={
        'INFO': 'green',      # INFO级别的日志，整行会显示为绿色
        'WARNING': 'yellow',
        'ERROR': 'red',
    },
    secondary_log_colors={
        'message': {          # 为消息内容(message)单独设置颜色规则
            'INFO': 'blue',  # 当级别为INFO时，消息主体为白色
            'WARNING': 'yellow',
            'ERROR': 'red',
        }
    }
)

handler.setFormatter(formatter)
logger_signal = colorlog.getLogger('__name__')
logger_signal.addHandler(handler)
logger_signal.setLevel(logging.INFO)
logger_signal.propagate = False  # 阻止传播到根logger

# 手动给数值部分添加颜色 (结合方案一和方案二)
GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[34m'


class SignalManager:
    """信号管理器"""

    def __init__(self):
        self.signal_symbols_list: List[str] = []
        self.current_index: int = 0
        self.lock = threading.Lock()
        self.executed_symbols = set()

    def update_signals(self, symbols: List,signal_d: Dict):
        data = pd.read_csv('price.csv')

        with self.lock:
            result = [list(d.values())[0] for d in symbols]

            self.signal_symbols_list = result
            self.current_index = -1
            self.executed_symbols.clear()

            logger_signal.info(f"更新信号列表 (共{len(symbols)}个):")
            columns = 5
            row_count = (len(symbols) + columns - 1) // columns

            # 计算每列的最大宽度
            col_widths = []
            for col in range(columns):
                col_symbols = [symbols[i].get('symbol') for i in range(col, len(symbols), columns)]
                if col_symbols:
                    max_len = max(len(s) for s in col_symbols)
                    col_widths.append(max_len)

            # 输出表格
            for row in range(row_count):
                row_items = []
                for col in range(columns):
                    idx = row * columns + col
                    if idx < len(symbols):
                        get_symbol = symbols[idx].get('symbol')
                        get_position_side = symbols[idx].get('position_side')
                        format_name = get_symbol.replace("USDT", "").lower()
                        pvalues = data[data['symbols'] == format_name]['price'].values
                        mode = data[data['symbols'] == format_name]['mode'].values
                        if len(pvalues) > 0:
                            key_price = float(pvalues[0])
                            if get_position_side == 'L' and mode =='l':
                                c_price = signal_d.get(get_symbol)[1].get('data').iloc[-1]['close']
                                percent = (c_price - key_price) / key_price * 100
                                color = GREEN if percent > 0 else RED
                                colored_percent_txt = f"{color}{percent:+.2f}%{RESET}"

                            elif get_position_side == 'S' and mode =='s':
                                c_price = signal_d.get(get_symbol)[1].get('data').iloc[-1]['close']
                                percent = (key_price - c_price) / key_price * 100
                                color = GREEN if percent < 0 else RED
                                colored_percent_txt = f"{color}{percent:+.2f}%{RESET}"
                            else:
                                colored_percent_txt = "..."
                        else:
                            colored_percent_txt = "..."
                        item = get_symbol + ' ' + get_position_side + " " +colored_percent_txt
                        # 对齐显示
                        padded_item = item.ljust(col_widths[col])
                        row_items.append(padded_item)

                if row_items:
                    logger_signal.info("  " + " | ".join(row_items).rstrip())

    def get_current_symbol(self) -> Optional[str]:
        with self.lock:
            if not self.signal_symbols_list:
                return None

            # 如果 current_index = -1，表示还未开始，可以返回第一个元素
            # 或者返回 None，取决于你想要的行为
            if self.current_index < 0:
                return None  # 或者 return self.signal_symbols_list[0] 如果你想显示第一个元素

            if self.current_index < len(self.signal_symbols_list):
                return self.signal_symbols_list[self.current_index]
            return None

    def execute_and_move_next(self) -> Optional[dict]:
        with self.lock:
            if not self.signal_symbols_list:
                return None

            # 如果已经是最后一个，不操作
            if self.current_index >= len(self.signal_symbols_list) - 1:
                return None

            # 移动到下一个元素
            self.current_index += 1
            ready_symbol = self.signal_symbols_list[self.current_index]

            # 标记为已执行
            self.executed_symbols.add(ready_symbol)

            # 检查是否有下一个元素
            next_index = self.current_index + 1
            if next_index >= len(self.signal_symbols_list):
                return {'executed': ready_symbol, 'next': None, 'moved': True, 'reason': "已是最后一个"}

            next_symbol = self.signal_symbols_list[next_index]
            return {'executed': ready_symbol, 'next': next_symbol, 'moved': True, 'reason': ""}

    def execute_and_move_previous(self) -> Optional[dict]:
        with self.lock:
            if not self.signal_symbols_list:
                return None

            # 如果已经是第一个，不操作
            if self.current_index <= 0:
                return None

            # 移动到上一个元素
            self.current_index -= 1
            ready_symbol = self.signal_symbols_list[self.current_index]

            # 标记为已执行
            self.executed_symbols.add(ready_symbol)

            # 检查是否有上一个元素
            prev_index = self.current_index - 1
            if prev_index < 0:
                return {'executed': ready_symbol, 'prev': None, 'moved': True, 'reason': "已是第一个"}

            prev_symbol = self.signal_symbols_list[prev_index]
            return {'executed': ready_symbol, 'prev': prev_symbol, 'moved': True, 'reason': ""}

    def get_current_position_info(self) -> str:
        with self.lock:
            if not self.signal_symbols_list:
                return "暂无信号"

            # 如果 current_index = -1，表示还未开始
            if self.current_index < 0:
                return f"[准备开始/{len(self.signal_symbols_list)}]"

            # 正常情况
            if 0 <= self.current_index < len(self.signal_symbols_list):
                current_symbol = self.signal_symbols_list[self.current_index]
                is_executed = current_symbol in self.executed_symbols
                executed_mark = "✅" if is_executed else "⏳"
                return f"[{self.current_index + 1}/{len(self.signal_symbols_list)}]{executed_mark}"

            # 其他情况
            return "暂无信号"

    def is_current_executed(self) -> bool:
        with self.lock:
            if not self.signal_symbols_list:
                return False
            if 0 <= self.current_index < len(self.signal_symbols_list):
                current_symbol = self.signal_symbols_list[self.current_index]
                return current_symbol in self.executed_symbols
            return False

    def has_signals(self) -> bool:
        with self.lock:
            return len(self.signal_symbols_list) > 0