"""串口转发模块：负责打开串口并写入 RTCM 二进制数据。

注意：LoRa 模块需设置为透明传输模式。过高的数据速率可能导致丢包。
"""
from __future__ import annotations
import serial  # type: ignore
import threading
from typing import Optional, Callable

LogCallback = Callable[[str], None]


class SerialForwarder:
    def __init__(self, port: str, baudrate: int = 57600, log: Optional[LogCallback] = None):
        self.port = port
        self.baudrate = baudrate
        self.log = log or (lambda m: None)
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self.bytes_sent = 0

    def open(self):
        if self._ser and self._ser.is_open:
            return
        self._ser = serial.Serial(self.port, self.baudrate, timeout=0)
        self.log(f"串口打开: {self.port} @ {self.baudrate}")

    def close(self):
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
