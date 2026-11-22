"""Color math for Hue lights: CIE xy, gamut clamping, color temperature.

All RGB values here are floats in 0..1. The RGB <-> XYZ matrices are the
wide-gamut ones Philips documents for Hue, so the edge of the color wheel
maps onto the most saturated colors a lamp can actually produce.
"""

from __future__ import annotations

import colorsys
import math

XY = tuple[float, float]
RGB = tuple[float, float, float]
Gamut = tuple[XY, XY, XY]

# Gamut C covers all current color lamps; used when a light doesn't report one.
GAMUT_C: Gamut = ((0.6915, 0.3083), (0.17, 0.7), (0.1532, 0.0475))
WHITE_XY: XY = (0.3127, 0.3290)

MIREK_MIN = 153  # ~6500 K
MIREK_MAX = 500  # 2000 K


def _linearize(c: float) -> float:
    return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92


def _delinearize(c: float) -> float:
    return 1.055 * (c ** (1 / 2.4)) - 0.055 if c > 0.0031308 else 12.92 * c


def rgb_to_xy(r: float, g: float, b: float) -> XY:
    r, g, b = _linearize(r), _linearize(g), _linearize(b)
    x = r * 0.664511 + g * 0.154324 + b * 0.162028
    y = r * 0.283881 + g * 0.668433 + b * 0.047685
    z = r * 0.000088 + g * 0.072310 + b * 0.986039
    total = x + y + z
    if total <= 0:
        return WHITE_XY
    return x / total, y / total


def xy_to_rgb(x: float, y: float) -> RGB:
    """Full-brightness display color for a chromaticity."""
    if y <= 0:
        return 1.0, 1.0, 1.0
    big_y = 1.0
    big_x = (big_y / y) * x
    big_z = (big_y / y) * (1.0 - x - y)
    r = big_x * 1.656492 - big_y * 0.354851 - big_z * 0.255038
    g = -big_x * 0.707196 + big_y * 1.655397 + big_z * 0.036152
    b = big_x * 0.051713 - big_y * 0.121364 + big_z * 1.011530
    r, g, b = (max(0.0, c) for c in (r, g, b))
    peak = max(r, g, b)
    if peak > 0:
        r, g, b = r / peak, g / peak, b / peak
    return tuple(min(1.0, max(0.0, _delinearize(c))) for c in (r, g, b))  # type: ignore[return-value]


def _cross(o: XY, a: XY, b: XY) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def in_gamut(point: XY, gamut: Gamut) -> bool:
    r, g, b = gamut
    d1, d2, d3 = _cross(r, g, point), _cross(g, b, point), _cross(b, r, point)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def _closest_on_segment(p: XY, a: XY, b: XY) -> XY:
    ax, ay = b[0] - a[0], b[1] - a[1]
    length_sq = ax * ax + ay * ay
    t = 0.0 if length_sq == 0 else ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / length_sq
    t = max(0.0, min(1.0, t))
    return a[0] + ax * t, a[1] + ay * t


def clamp_to_gamut(point: XY, gamut: Gamut | None = None) -> XY:
    gamut = gamut or GAMUT_C
    if in_gamut(point, gamut):
        return point
    r, g, b = gamut
    candidates = [_closest_on_segment(point, *edge) for edge in ((r, g), (g, b), (b, r))]
    return min(candidates, key=lambda c: math.dist(c, point))


def hs_to_xy(hue: float, saturation: float, gamut: Gamut | None = None) -> XY:
    """Hue in degrees, saturation 0..1 -> xy inside the lamp's gamut."""
    r, g, b = colorsys.hsv_to_rgb((hue % 360) / 360, max(0.0, min(1.0, saturation)), 1.0)
    x, y = rgb_to_xy(r, g, b)
    return clamp_to_gamut((round(x, 4), round(y, 4)), gamut)


def xy_to_hs(x: float, y: float) -> tuple[float, float]:
    r, g, b = xy_to_rgb(x, y)
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    return h * 360, s


def mirek_to_kelvin(mirek: int) -> int:
    return round(1_000_000 / max(1, mirek))


def kelvin_to_mirek(kelvin: float) -> int:
    return round(1_000_000 / max(1.0, kelvin))


def kelvin_to_rgb(kelvin: float) -> RGB:
    """Approximate display color of a black-body light source (Tanner Helland)."""
    t = max(1000.0, min(40000.0, kelvin)) / 100
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
    else:
        r = 329.698727446 * (t - 60) ** -0.1332047592
        g = 288.1221695283 * (t - 60) ** -0.0755148492
    if t >= 66:
        b = 255.0
    elif t <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(t - 10) - 305.0447927307
    return tuple(max(0.0, min(255.0, c)) / 255 for c in (r, g, b))  # type: ignore[return-value]


def mirek_to_rgb(mirek: int) -> RGB:
    return kelvin_to_rgb(mirek_to_kelvin(mirek))


def mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(x + (y - x) * t for x, y in zip(a, b))  # type: ignore[return-value]
