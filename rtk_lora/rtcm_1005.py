"""RTCM 1005 解析与坐标转换。

说明：
- 仅解析 1005 的 ECEF (X,Y,Z)，单位 0.0001m。
- 不做 CRC 校验（由上层 RTCMParser 负责帧同步）。
- 将 ECEF 转换为 WGS84 (lat, lon, alt) 供发送 GGA 使用。
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional


@dataclass(frozen=True)
class Rtcm1005:
    reference_station_id: int
    ecef_x_m: float
    ecef_y_m: float
    ecef_z_m: float
    lat_deg: float
    lon_deg: float
    alt_m: float


class _BitReader:
    def __init__(self, data: bytes):
        self._data = data
        self._bitpos = 0

    def read_uint(self, nbits: int) -> int:
        if nbits <= 0:
            return 0
        value = 0
        for _ in range(nbits):
            byte_index = self._bitpos // 8
            bit_index = 7 - (self._bitpos % 8)
            if byte_index >= len(self._data):
                raise ValueError("payload too short")
            bit = (self._data[byte_index] >> bit_index) & 1
            value = (value << 1) | bit
            self._bitpos += 1
        return value

    def read_int(self, nbits: int) -> int:
        u = self.read_uint(nbits)
        sign_bit = 1 << (nbits - 1)
        if u & sign_bit:
            return u - (1 << nbits)
        return u


def parse_1005(payload: bytes) -> Optional[Rtcm1005]:
    """解析 RTCM 1005 payload（不含 D3 头、不含 CRC）。

    返回：解析成功 -> Rtcm1005；否则 None。
    """
    if len(payload) < 8:
        return None

    br = _BitReader(payload)
    msg_num = br.read_uint(12)
    if msg_num != 1005:
        return None

    ref_station_id = br.read_uint(12)
    _itrf_year = br.read_uint(6)
    _gps_ind = br.read_uint(1)
    _glo_ind = br.read_uint(1)
    _gal_ind = br.read_uint(1)
    _ref_station_ind = br.read_uint(1)

    # ECEF X/Y/Z: 38-bit signed, unit 0.0001m
    x = br.read_int(38) * 0.0001
    _single_rcv = br.read_uint(1)
    _reserved = br.read_uint(1)
    y = br.read_int(38) * 0.0001
    _quarter_cycle = br.read_uint(2)
    z = br.read_int(38) * 0.0001

    lat, lon, alt = ecef_to_lla(x, y, z)
    return Rtcm1005(
        reference_station_id=ref_station_id,
        ecef_x_m=x,
        ecef_y_m=y,
        ecef_z_m=z,
        lat_deg=lat,
        lon_deg=lon,
        alt_m=alt,
    )


def ecef_to_lla(x_m: float, y_m: float, z_m: float) -> tuple[float, float, float]:
    """ECEF(X,Y,Z) -> WGS84 (lat_deg, lon_deg, alt_m)。

    采用迭代法，足够用于生成 GGA 的位置。
    """
    # WGS84
    a = 6378137.0
    f = 1.0 / 298.257223563
    e2 = f * (2.0 - f)

    lon = math.atan2(y_m, x_m)
    p = math.hypot(x_m, y_m)

    # 特殊情况：接近极点
    if p < 1e-6:
        lat = math.copysign(math.pi / 2.0, z_m)
        alt = abs(z_m) - a * math.sqrt(1.0 - e2)
        return math.degrees(lat), math.degrees(lon), alt

    lat = math.atan2(z_m, p * (1.0 - e2))
    for _ in range(10):
        sin_lat = math.sin(lat)
        n = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
        alt = p / math.cos(lat) - n
        new_lat = math.atan2(z_m, p * (1.0 - e2 * (n / (n + alt))))
        if abs(new_lat - lat) < 1e-12:
            lat = new_lat
            break
        lat = new_lat

    sin_lat = math.sin(lat)
    n = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
    alt = p / math.cos(lat) - n

    return math.degrees(lat), math.degrees(lon), alt


__all__ = ["Rtcm1005", "parse_1005", "ecef_to_lla"]
