# keyboard_handler.py
import queue
import threading
import logging
from pynput import keyboard

logger = logging.getLogger(__name__)


class KeyboardHandler:
    """键盘处理器"""

    def __init__(self):
        self.key_press_queue = queue.Queue()
        self.listener = None
        self.running = False

    def start(self):
        """启动键盘监听"""
        self.running = True
        thread = threading.Thread(target=self._listen, daemon=True)
        thread.start()
        logger.info("⌨️ 键盘监听器已启动")

    def _listen(self):
        """监听键盘事件"""

        def on_press(key):
            try:
                if hasattr(key, 'char'):
                    if key.char == '+':
                        # logger.info("➕ +键按下")
                        self.key_press_queue.put('execute_next')
                    elif key.char == '-':
                        # logger.info("➖ -键按下")
                        self.key_press_queue.put('execute_previous')
            except Exception as e:
                logger.error(f"按键处理错误: {e}")

        with keyboard.Listener(on_press=on_press) as listener:
            self.listener = listener
            listener.join()

    def stop(self):
        """停止监听"""
        if self.listener:
            self.listener.stop()