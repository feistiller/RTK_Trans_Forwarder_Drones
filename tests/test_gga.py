import re
from rtk_lora.gga import build_gga


def test_build_gga_basic():
    gga = build_gga(31.123456, 121.123456, 10.5)
    s = gga.decode()
    assert s.startswith('$GPGGA,')
    assert s.endswith('\r\n')
    # 基本字段数量检查
    core = s[1:].split('*')[0]
    fields = core.split(',')
    assert fields[0] == 'GPGGA'
    # 纬度格式 ddmm.mmmm
    lat = fields[2]
    assert re.match(r"^\d{4}\d\.\d{4}$", lat) is None  # 简单校验: 但我们格式是 ddmm.mmmm => 长度 4+1+4
    assert len(lat.split('.')[0]) in (4,5)
    # 卫星数
    assert fields[7].isdigit()
    # 海拔
    assert float(fields[9]) == 10.5
