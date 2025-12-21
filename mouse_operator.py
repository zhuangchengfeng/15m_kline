# mouse_operator.py
import pyautogui
import time
import logging

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
        """
        执行鼠标操作序列

        Args:
            symbol: 要操作的交易对符号

        Returns:
            bool: 操作是否成功
        """
        try:
            coords = self.click_coordinates

            # 双击位置（复制）
            pyautogui.moveTo(coords['first_double_click'], duration=0.05)
            pyautogui.doubleClick()
            time.sleep(0.1)

            # 输入币种
            pyautogui.write(symbol, interval=0.03)
            time.sleep(0.1)

            # 单击位置
            pyautogui.moveTo(coords['second_click'], duration=0.05)
            pyautogui.click()
            time.sleep(0.1)

            logger.debug(f"✅ 鼠标操作完成: {symbol}")
            return True

        except Exception as e:
            logger.error(f"❌ 鼠标操作失败: {e}")
            return False

    def update_coordinates(self, new_coordinates: dict):
        """更新鼠标坐标配置"""
        self.click_coordinates = new_coordinates
        logger.info(f"🔄 更新鼠标坐标: {new_coordinates}")