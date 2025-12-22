# mouse_operator.py
import pyautogui
import time
import logging
import pyperclip
logger = logging.getLogger(__name__)


class MouseOperator:
    """鼠标操作器"""

    def __init__(self, click_coordinates: dict):
        """
        初始化鼠标操作器

        Args:
            click_coordinates: 点击坐标配置字典
        """
        self.click_coordinates = click_coordinates
        logger.info("🖱️ 鼠标操作器已初始化")

    def perform_operations(self, symbol: str) -> bool:
        try:
            coords = self.click_coordinates

            # 1. 双击位置
            pyautogui.moveTo(coords['first_double_click'], duration=0.05)
            pyautogui.doubleClick()
            time.sleep(0.1)

            # 2. 使用剪贴板复制粘贴
            pyperclip.copy(symbol)  # 复制到剪贴板

            # 3. 粘贴操作
            # 方法A：使用快捷键 Ctrl+V
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.1)

            # 方法B：使用 pyautogui 的右键菜单（备用）
            # pyautogui.rightClick()
            # time.sleep(0.1)
            # pyautogui.press('p')  # 按P选择"粘贴"

            # 4. 单击位置
            pyautogui.moveTo(coords['second_click'], duration=0.05)
            pyautogui.click()
            time.sleep(0.1)

            logger.debug(f"✅ 剪贴板方式完成: {symbol}")
            return True

        except Exception as e:
            logger.error(f"❌ 操作失败: {e}")
            return False

    def update_coordinates(self, new_coordinates: dict):
        """更新鼠标坐标配置"""
        self.click_coordinates = new_coordinates
        logger.info(f"🔄 更新鼠标坐标: {new_coordinates}")