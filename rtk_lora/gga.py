"""生成 NMEA GGA 语句模块。

提供 build_gga(lat_deg, lon_deg, alt, fix_quality=4, num_sats=12, hdop=0.8) -> bytes
其中：
- lat_deg / lon_deg 使用十进制度（正北正东，南/西用负号）
- alt 为大地高（近似）米
- fix_quality: 0=Invalid 1=GPS Fix 2=DGPS 4=RTK Fixed 5=RTK Float (这里默认4，向 Caster 声明期望高质量)
返回含换行的完整 GGA 语句 bytes: b"$GPGGA,...*CS\r\n"
"""
from __future__ import annotations
import datetime


def _checksum(nmea_body: str) -> str:
    c = 0
    for ch in nmea_body:
        c ^= ord(ch)
    return f"{c:02X}"


def _deg_to_nmea_lat(lat_deg: float) -> str:
    if lat_deg is None:
        raise ValueError("lat_deg 不能为空")
    hemi = 'N' if lat_deg >= 0 else 'S'
    lat = abs(lat_deg)
    deg = int(lat)
    minutes = (lat - deg) * 60.0
    return f"{deg:02d}{minutes:07.4f},{hemi}"


def _deg_to_nmea_lon(lon_deg: float) -> str:
    if lon_deg is None:
        raise ValueError("lon_deg 不能为空")
    hemi = 'E' if lon_deg >= 0 else 'W'
    lon = abs(lon_deg)
    deg = int(lon)
    minutes = (lon - deg) * 60.0
    return f"{deg:03d}{minutes:07.4f},{hemi}"


def build_gga(lat_deg: float, lon_deg: float, alt: float,
              fix_quality: int = 4, num_sats: int = 12, hdop: float = 0.8,
              geoid_sep: float = 0.0) -> bytes:
    """构造 GGA 语句。

    geoid_sep: 大地水准面分离 (近似)，默认0 可不影响 Caster。
    """
    now = datetime.datetime.utcnow()
    timestr = now.strftime('%H%M%S')
    lat_field = _deg_to_nmea_lat(lat_deg)
    lon_field = _deg_to_nmea_lon(lon_deg)
    # Age / diff station id 暂用空
    body = (
        f"GPGGA,{timestr},{lat_field},{lon_field},{fix_quality},{num_sats:02d},"
        f"{hdop:.1f},{alt:.2f},M,{geoid_sep:.1f},M,,"
    )
    cs = _checksum(body)
    sentence = f"${body}*{cs}\r\n"
    return sentence.encode('ascii')

__all__ = [
    'build_gga'
]
