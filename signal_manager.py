# signal_manager.py
import threading
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class SignalManager:
    """信号管理器"""

    def __init__(self):
        self.signal_symbols_list: List[str] = []
        self.current_index: int = 0
        self.lock = threading.Lock()
        self.executed_symbols = set()

    def update_signals(self, symbols: List[str]):
        with self.lock:
            self.signal_symbols_list = symbols
            self.current_index = -1
            self.executed_symbols.clear()

            logger.info(f"更新信号列表 (共{len(symbols)}个):")
            columns = 5
            row_count = (len(symbols) + columns - 1) // columns

            # 计算每列的最大宽度
            col_widths = []
            for col in range(columns):
                col_symbols = [symbols[i] for i in range(col, len(symbols), columns)]
                if col_symbols:
                    max_len = max(len(s) for s in col_symbols)
                    col_widths.append(max_len)

            # 输出表格
            for row in range(row_count):
                row_items = []
                for col in range(columns):
                    idx = row * columns + col
                    if idx < len(symbols):
                        item = symbols[idx]
                        # 对齐显示
                        padded_item = item.ljust(col_widths[col])
                        row_items.append(padded_item)

                if row_items:
                    logger.info("  " + " | ".join(row_items).rstrip())

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