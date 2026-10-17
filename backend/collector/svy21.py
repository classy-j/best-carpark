"""SVY21 (Singapore, EPSG:3414) -> WGS84 latitude/longitude.

HDB carpark data gives x_coord/y_coord in SVY21 metres. This is the standard
inverse Transverse Mercator for SVY21 (no external dependency). Accuracy is
checked against pyproj in tests (well under 1 m across Singapore).
"""
import math

_a = 6378137.0
_f = 1 / 298.257223563
_ORIGIN_LAT = 1.366666
_ORIGIN_LON = 103.833333
_FALSE_N = 38744.572
_FALSE_E = 28001.642
_K = 1.0

_b = _a * (1 - _f)
_e2 = 2 * _f - _f * _f
_e4 = _e2 ** 2
_e6 = _e4 * _e2
_A0 = 1 - _e2 / 4 - 3 * _e4 / 64 - 5 * _e6 / 256
_A2 = 3 / 8 * (_e2 + _e4 / 4 + 15 * _e6 / 128)
_A4 = 15 / 256 * (_e4 + 3 * _e6 / 4)
_A6 = 35 * _e6 / 3072
_n = (_a - _b) / (_a + _b)
_n2, _n3, _n4 = _n ** 2, _n ** 3, _n ** 4
_G = _a * (1 - _n) * (1 - _n2) * (1 + 9 * _n2 / 4 + 225 * _n4 / 64) * (math.pi / 180)


def _meridian_distance(lat_deg: float) -> float:
    p = math.radians(lat_deg)
    return _a * (_A0 * p - _A2 * math.sin(2 * p) + _A4 * math.sin(4 * p) - _A6 * math.sin(6 * p))


_M0 = _meridian_distance(_ORIGIN_LAT)


def svy21_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """(x = easting, y = northing) in SVY21 metres -> (latitude, longitude) in degrees."""
    m_prime = _M0 + (y - _FALSE_N) / _K
    sigma = math.radians(m_prime / _G)

    lat_p = (sigma
             + (3 * _n / 2 - 27 * _n3 / 32) * math.sin(2 * sigma)
             + (21 * _n2 / 16 - 55 * _n4 / 32) * math.sin(4 * sigma)
             + (151 * _n3 / 96) * math.sin(6 * sigma)
             + (1097 * _n4 / 512) * math.sin(8 * sigma))

    s2 = math.sin(lat_p) ** 2
    rho = _a * (1 - _e2) / (1 - _e2 * s2) ** 1.5
    nu = _a / math.sqrt(1 - _e2 * s2)
    psi = nu / rho
    psi2, psi3, psi4 = psi ** 2, psi ** 3, psi ** 4
    sec = 1 / math.cos(lat_p)
    t = math.tan(lat_p)
    t2, t4, t6 = t ** 2, t ** 4, t ** 6

    e_prime = x - _FALSE_E
    q = e_prime / (_K * nu)
    q3, q5, q7 = q ** 3, q ** 5, q ** 7

    lat_factor = t / (_K * rho)
    l1 = lat_factor * (e_prime * q / 2)
    l2 = lat_factor * (e_prime * q3 / 24) * (-4 * psi2 + 9 * psi * (1 - t2) + 12 * t2)
    l3 = lat_factor * (e_prime * q5 / 720) * (
        8 * psi4 * (11 - 24 * t2) - 12 * psi3 * (21 - 71 * t2)
        + 15 * psi2 * (15 - 98 * t2 + 15 * t4) + 180 * psi * (5 * t2 - 3 * t4) + 360 * t4)
    l4 = lat_factor * (e_prime * q7 / 40320) * (1385 - 3633 * t2 + 4095 * t4 + 1575 * t6)
    lat = lat_p - l1 + l2 - l3 + l4

    g1 = q * sec
    g2 = (q3 * sec / 6) * (psi + 2 * t2)
    g3 = (q5 * sec / 120) * (-4 * psi3 * (1 - 6 * t2) + psi2 * (9 - 68 * t2) + 72 * psi * t2 + 24 * t4)
    g4 = (q7 * sec / 5040) * (61 + 662 * t2 + 1320 * t4 + 720 * t6)
    lon = math.radians(_ORIGIN_LON) + g1 - g2 + g3 - g4

    return math.degrees(lat), math.degrees(lon)
