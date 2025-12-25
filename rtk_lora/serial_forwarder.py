"""串口转发模块：负责打开串口并写入 RTCM 二进制数据。

注意：LoRa 模块需设置为透明传输模式。过高的数据速率可能导致丢包。
"""
from __future__ import annotations
import serial  # type: ignore
import threading
import time
from typing import Optional, Callable

LogCallback = Callable[[str], None]
RxCallback = Callable[[bytes], None]


class SerialForwarder:
    def __init__(
        self,
        port: str,
        baudrate: int = 57600,
        log: Optional[LogCallback] = None,
        on_rx: Optional[RxCallback] = None,
        rx_read_size: int = 4096,
        rx_poll_interval: float = 0.02,
    ):
        self.port = port
        self.baudrate = baudrate
        self.log = log or (lambda m: None)
        self.on_rx = on_rx
        self.rx_read_size = rx_read_size
        self.rx_poll_interval = rx_poll_interval
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self.bytes_sent = 0
        self.bytes_received = 0
        self._rx_stop_evt = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None

    def open(self):
        if self._ser and self._ser.is_open:
            return
        # timeout 用于接收线程，避免忙等；写入不受影响
        self._ser = serial.Serial(self.port, self.baudrate, timeout=0.2)
        self.log(f"串口打开: {self.port} @ {self.baudrate}")

        if self.on_rx:
            self._start_rx_thread()

    def _start_rx_thread(self):
        if self._rx_thread and self._rx_thread.is_alive():
            return
        self._rx_stop_evt.clear()
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

    def _rx_loop(self):
        while not self._rx_stop_evt.is_set():
            ser = self._ser
            if not ser or not ser.is_open:
                break
            try:
                n_waiting = getattr(ser, "in_waiting", 0) or 0
                if n_waiting <= 0:
                    time.sleep(self.rx_poll_interval)
                    continue
                data = ser.read(min(self.rx_read_size, n_waiting))
                if not data:
                    continue
                self.bytes_received += len(data)
                if self.on_rx:
                    self.on_rx(data)
            except Exception as e:  # noqa
                self.log(f"串口接收异常(忽略): {e}")
                time.sleep(0.2)

    def close(self):
        self._rx_stop_evt.set()
        if self._rx_thread:
            self._rx_thread.join(timeout=1.0)
            self._rx_thread = None
        if self._ser:
            try:
                self._ser.close()
            except Exception:  # noqa
                pass
            self._ser = None
            self.log("串口已关闭")

    def send(self, data: bytes):
        with self._lock:
            if not self._ser or not self._ser.is_open:
                raise RuntimeError("串口未打开")
            try:
                n = self._ser.write(data)
                self.bytes_sent += n
            except Exception as e:  # noqa
                self.log(f"串口发送失败: {e}")
                raise

__all__ = ["SerialForwarder"]
