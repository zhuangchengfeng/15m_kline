# alert_manager.py - 修改部分

import threading
import logging
logger = logging.getLogger(__name__)
import time
import winsound
class AlertManager:
    """警报管理器"""

    def __init__(self):
        self.beep_thread: threading.Thread = None
        self.stop_beep_event = threading.Event()
        self.is_beeping = False
        self.lock = threading.Lock()  # 添加锁避免竞争
        logger.info('蜂鸣管理器启动')

    def beep_alert(self, duration=10, frequency=1000):
        """发出蜂鸣声"""
        # 如果正在蜂鸣，先停止
        with self.lock:
            if self.is_beeping:
                self._stop_beep_internal()

            # 清除事件标志，确保新的蜂鸣能开始
            self.stop_beep_event.clear()

            def _beep():
                self.is_beeping = True
                start_time = time.time()
                try:
                    while not self.stop_beep_event.is_set() and (time.time() - start_time) < duration:
                        try:
                            winsound.Beep(frequency, 500)
                            time.sleep(0.5)
                        except Exception as e:
                            logger.error(f"蜂鸣错误: {e}")
                            break
                finally:
                    self.is_beeping = False
                    self.stop_beep_event.clear()

            self.beep_thread = threading.Thread(target=_beep, daemon=True)
            self.beep_thread.start()
            return self.beep_thread

    def _stop_beep_internal(self):
        """内部停止蜂鸣方法"""
        self.stop_beep_event.set()
        if self.beep_thread and self.beep_thread.is_alive():
            self.beep_thread.join(timeout=0.5)

    def stop_beep(self):
        """停止蜂鸣"""
        with self.lock:
            self._stop_beep_internal()

if __name__ == '__main__':
    a = AlertManager()
    a.beep_alert()