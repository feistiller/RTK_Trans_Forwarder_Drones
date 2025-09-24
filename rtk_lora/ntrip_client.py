"""简单 NTRIP v1 客户端实现。

功能点：
- TCP 连接到 caster (host:port)
- 发送带 Basic Auth 的请求头 (MountPoint)
- 定期发送 GGA (外部提供经纬度) 以保持流数据
- 异步读取 RTCM 数据并回调处理（例如转发到串口）
- 简单重连策略（指数退避上限）

使用：
    client = NTRIPClient(host, port, mountpoint, user, password,
                         get_position=lambda: (lat, lon, alt),
                         on_rtcm=lambda b: serial_forwarder.send(b))
    client.start()
    ... 停止时 client.stop()
"""
from __future__ import annotations
import base64
import socket
import threading
import time
from typing import Callable, Optional

from .gga import build_gga

PositionProvider = Callable[[], tuple[float, float, float]]
RTCMCallback = Callable[[bytes], None]
LogCallback = Callable[[str], None]


class NTRIPClient:
    def __init__(self, host: str, port: int, mountpoint: str,
                 username: str, password: str,
                 get_position: PositionProvider,
                 on_rtcm: RTCMCallback,
                 log: Optional[LogCallback] = None,
                 send_gga_interval: float = 15.0,
                 reconnect_max_interval: float = 60.0,
                 timeout: float = 10.0):
        self.host = host
        self.port = port
        self.mountpoint = mountpoint.lstrip('/')
        self.username = username
        self.password = password
        self.get_position = get_position
        self.on_rtcm = on_rtcm
        self.log = log or (lambda m: None)
        self.send_gga_interval = send_gga_interval
        self.reconnect_max_interval = reconnect_max_interval
        self.timeout = timeout
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._last_gga = 0.0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.log("NTRIPClient 启动线程")

    def stop(self):
        self._stop_evt.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=2)
        self.log("NTRIPClient 已停止")

    # 内部方法
    def _build_request(self) -> bytes:
        auth_raw = f"{self.username}:{self.password}".encode('utf-8')
        auth_b64 = base64.b64encode(auth_raw).decode()
        req = (
            f"GET /{self.mountpoint} HTTP/1.0\r\n"
            f"Host: {self.host}\r\n"
            f"User-Agent: RTK-LoRa-Forwarder/0.1\r\n"
            f"Authorization: Basic {auth_b64}\r\n"
            f"Ntrip-Version: Ntrip/2.0\r\n"
            f"Connection: close\r\n\r\n"
        )
        return req.encode('ascii')

    def _connect_and_stream(self):
        self.log(f"连接 NTRIP {self.host}:{self.port} ...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect((self.host, self.port))
        s.sendall(self._build_request())
        resp = s.recv(4096)
        if b"ICY 200 OK" not in resp and b"HTTP/1.1 200" not in resp and b"HTTP/1.0 200" not in resp:
            raise ConnectionError(f"NTRIP 连接失败 响应: {resp[:100]!r}")
        # 去掉头部（简单处理：查找\r\n\r\n）
        header_end = resp.find(b"\r\n\r\n")
        leftover = b""
        if header_end != -1:
            leftover = resp[header_end+4:]
        self._sock = s
        self.log("NTRIP 建立成功")
        if leftover:
            self.on_rtcm(leftover)
        self._last_gga = 0
        while not self._stop_evt.is_set():
            now = time.time()
            if now - self._last_gga >= self.send_gga_interval:
                try:
                    lat, lon, alt = self.get_position()
                    gga = build_gga(lat, lon, alt)
                    s.sendall(gga)
                    self._last_gga = now
                    self.log("发送 GGA")
                except Exception as e:  # noqa
                    self.log(f"GGA 发送失败: {e}")
            try:
                s.settimeout(1.0)
                data = s.recv(4096)
                if not data:
                    raise ConnectionError("NTRIP 断开")
                self.on_rtcm(data)
            except socket.timeout:
                continue
        self.log("退出接收循环")

    def _run(self):
        backoff = 2.0
        while not self._stop_evt.is_set():
            try:
                self._connect_and_stream()
                backoff = 2.0  # 正常结束重置
            except Exception as e:  # noqa
                self.log(f"NTRIP 错误: {e}")
                if self._sock:
                    try:
                        self._sock.close()
                    except OSError:
                        pass
                    self._sock = None
                time.sleep(backoff)
                backoff = min(backoff * 1.7, self.reconnect_max_interval)
        self.log("NTRIP 线程退出")

__all__ = ["NTRIPClient"]
