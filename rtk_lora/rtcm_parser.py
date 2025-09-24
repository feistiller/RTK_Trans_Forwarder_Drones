"""极简 RTCM3 消息号提取（流式）。

RTCM3 帧格式（简化）：
- Preamble: 0xD3
- 6bit 保留 + 10bit 长度 (len): 高位2字节部分
- 接着 len 字节的 payload
- 尾部 3 字节 CRC24Q

我们只做：
- 按 D3 帧同步
- 读取长度，拿到 payload 前2字节，从中提取 12bit 的 message number
- 不做 CRC 校验（仅用于日志统计）
- 以流式状态机方式处理分包

参考：RTCM 10403.x
"""
from __future__ import annotations
from typing import Dict, List, Tuple

D3 = 0xD3

class RTCMParser:
    def __init__(self):
        self.buf = bytearray()
        self.stats: Dict[int, int] = {}

    def feed(self, data: bytes) -> List[int]:
        """喂入数据，返回本次解析出的消息号列表。"""
        self.buf.extend(data)
        found: List[int] = []
        while True:
            # 寻找前导 0xD3
            start = self._find_preamble()
            if start < 0:
                # 没有头，清掉前面噪声
                self.buf.clear()
                break
            if start > 0:
                del self.buf[:start]
            if len(self.buf) < 3:
                break
            if self.buf[0] != D3:
                del self.buf[0]
                continue
            # 长度位于 buf[1:3] 的低 10 bit
            length = ((self.buf[1] & 0x03) << 8) | self.buf[2]
            total = 3 + length + 3  # 头(3) + payload(length) + CRC(3)
            if len(self.buf) < total:
                break
            payload = self.buf[3:3+length]
            msg_num = self._get_msg_num(payload)
            if msg_num is not None:
                self.stats[msg_num] = self.stats.get(msg_num, 0) + 1
                found.append(msg_num)
            # 丢弃一帧
            del self.buf[:total]
        return found

    def _find_preamble(self) -> int:
        for i, b in enumerate(self.buf):
            if b == D3:
                return i
        return -1

    def _get_msg_num(self, payload: bytes):
        if len(payload) < 2:
            return None
        # payload 前两字节的高 12 bit 为 message number
        b0 = payload[0]
        b1 = payload[1]
        msg_num = ((b0 << 4) | (b1 >> 4)) & 0x0FFF
        return msg_num

    def snapshot_stats(self) -> List[Tuple[int, int]]:
        return sorted(self.stats.items(), key=lambda x: x[0])

    def reset_stats(self):
        self.stats.clear()

__all__ = ["RTCMParser"]
