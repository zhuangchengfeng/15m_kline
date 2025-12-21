# alert_manager.py
import winsound
import threading
import time
import logging

logger = logging.getLogger(__name__)

class AlertManager:
    """警报管理器"""

    def __init__(self):
        self.beep_thread: threading.Thread = None
        self.stop_beep_event = threading.Event()
        self.is_beeping = False
        logger.info('蜂鸣管理器启动')

    def beep_alert(self, duration=10, frequency=1000):
        """发出蜂鸣声"""
        # 停止之前的蜂鸣
        self.stop_beep()

        def _beep():
            self.is_beeping = True
            start_time = time.time()
            while not self.stop_beep_event.is_set() and (time.time() - start_time) < duration:
                try:
                    winsound.Beep(frequency, 500)
                    time.sleep(0.5)
                except Exception as e:
                    logger.error(f"蜂鸣错误: {e}")
                    break
            self.stop_beep_event.clear()
            self.is_beeping = False

        self.beep_thread = threading.Thread(target=_beep, daemon=True)
        self.beep_thread.start()
        return self.beep_thread

    def stop_beep(self):
        """停止蜂鸣"""
        self.stop_beep_event.set()
        if self.beep_thread and self.beep_thread.is_alive():
            self.beep_thread.join(timeout=1)