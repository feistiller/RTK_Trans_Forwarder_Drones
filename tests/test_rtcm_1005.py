import math

from rtk_lora.rtcm_1005 import ecef_to_lla


def test_ecef_to_lla_equator_prime_meridian():
    # ECEF at equator, lon=0, altitude=0 => (a, 0, 0)
    a = 6378137.0
    lat, lon, alt = ecef_to_lla(a, 0.0, 0.0)
    assert abs(lat - 0.0) < 1e-6
    assert abs(lon - 0.0) < 1e-6
    assert abs(alt - 0.0) < 1e-3


def test_ecef_to_lla_lon_90():
    a = 6378137.0
    lat, lon, alt = ecef_to_lla(0.0, a, 0.0)
    assert abs(lat - 0.0) < 1e-6
    assert abs(lon - 90.0) < 1e-6
    assert abs(alt - 0.0) < 1e-3


def test_ecef_to_lla_pole():
    # Approx north pole on surface: z=b
    a = 6378137.0
    f = 1.0 / 298.257223563
    b = a * (1.0 - f)
    lat, lon, alt = ecef_to_lla(0.0, 0.0, b)
    assert abs(lat - 90.0) < 1e-6
    # lon is undefined at poles; our implementation returns atan2(0,0)=0
    assert abs(lon - 0.0) < 1e-6
    assert abs(alt - 0.0) < 1e-2
