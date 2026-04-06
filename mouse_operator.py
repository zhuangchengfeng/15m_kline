# mouse_operator.py
import pyautogui
import time
import logging
import pyperclip
from config import Config
import tools
logger = logging.getLogger(__name__)


class MouseOperator:
    """鼠标操作器"""

    def __init__(self):
        """
        初始化鼠标操作器

        Args:
            click_coordinates: 点击坐标配置字典
        """
        logger.info("🖱️ 鼠标操作器已初始化")

    def perform_operations(self, symbol: str) -> bool:
        try:
            current = tools.get_active_window_info()
            if current:
                pass
            else:
                logger.error(f"❌ 获取不到活跃的窗口")
                return False

            if current['title'] == 'Binance Desktop':
                coords = Config.CLICK_COORDINATES_BINANCE

                # 1. 双击位置
                pyautogui.moveTo(coords['first_double_click'], duration=0.05)
                pyautogui.doubleClick()
                time.sleep(0.1)

                # 2. 使用剪贴板复制粘贴
                pyperclip.copy(symbol)  # 复制到剪贴板

                # 3. 粘贴操作
                pyautogui.hotkey('ctrl', 'v')
                if Config.P5:
                    time.sleep(0.5)
                else:
                    time.sleep(0.2)


                # 4. 单击位置
                pyautogui.moveTo(coords['second_click'], duration=0.05)
                if Config.P5:
                    time.sleep(0.5)
                else:
                    time.sleep(0.2)
                pyautogui.click()

                logger.debug(f"✅ 剪贴板方式完成: {symbol}")
                return True
            elif '默认布局' in current['title']: #tradingview
                coords = Config.CLICK_COORDINATES_TRADING_VIEW

                # 2. 使用剪贴板复制粘贴
                pyperclip.copy(symbol)  # 复制到剪贴板
                pyautogui.hotkey('ctrl', 'a')
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.3)

                pyautogui.moveTo(coords['second_click'], duration=0.05)
                time.sleep(0.15)
                pyautogui.click()
                time.sleep(0.1)
                return True

        except Exception as e:
            logger.error(f"❌ 操作失败: {e}")
            return False

    def update_coordinates(self, new_coordinates: dict):
        """更新鼠标坐标配置"""
        self.click_coordinates = new_coordinates
        logger.info(f"🔄 更新鼠标坐标: {new_coordinates}")