"""Read-only views over raw CLIP v2 resources, shaped for the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import colors

Raw = dict[str, Any]


@dataclass(frozen=True)
class LightView:
    id: str
    name: str
    archetype: str
    on: bool
    brightness: float  # 0..100
    reachable: bool
    has_dimming: bool
    has_color: bool
    gamut: colors.Gamut | None
    has_ct: bool
    mirek: int | None
    mirek_min: int
    mirek_max: int
    xy: colors.XY | None
    mode: str  # "color" | "ct" | "plain"

    @property
    def rgb(self) -> colors.RGB:
        """Approximate color the light is emitting (ignoring brightness)."""
        if self.mode == "color" and self.xy:
            return colors.xy_to_rgb(*self.xy)
        if self.mode == "ct" and self.mirek:
            return colors.mirek_to_rgb(self.mirek)
        return colors.kelvin_to_rgb(2700)

    @classmethod
    def from_raw(cls, raw: Raw, reachable: bool = True) -> "LightView":
        color = raw.get("color") or {}
        ct = raw.get("color_temperature") or {}
        schema = ct.get("mirek_schema") or {}
        gamut_raw = color.get("gamut")
        gamut = None
        if gamut_raw:
            try:
                gamut = tuple((gamut_raw[k]["x"], gamut_raw[k]["y"]) for k in ("red", "green", "blue"))  # type: ignore[assignment]
            except (KeyError, TypeError):
                gamut = None
        xy_raw = color.get("xy")
        xy = (xy_raw["x"], xy_raw["y"]) if xy_raw else None
        has_color = "color" in raw
        has_ct = "color_temperature" in raw
        mirek = ct.get("mirek") if ct.get("mirek_valid", True) else None
        if has_ct and ct.get("mirek_valid") and mirek:
            mode = "ct"
        elif has_color:
            mode = "color"
        elif has_ct:
            mode = "ct"
        else:
            mode = "plain"
        return cls(
            id=raw["id"],
            name=(raw.get("metadata") or {}).get("name", "Light"),
            archetype=(raw.get("metadata") or {}).get("archetype", ""),
            on=bool((raw.get("on") or {}).get("on", False)),
            brightness=float((raw.get("dimming") or {}).get("brightness", 100.0)),
            reachable=reachable,
            has_dimming="dimming" in raw,
            has_color=has_color,
            gamut=gamut or (colors.GAMUT_C if has_color else None),
            has_ct=has_ct,
            mirek=mirek or ct.get("mirek"),
            mirek_min=int(schema.get("mirek_minimum", colors.MIREK_MIN)),
            mirek_max=int(schema.get("mirek_maximum", colors.MIREK_MAX)),
            xy=xy,
            mode=mode,
        )


@dataclass(frozen=True)
class GroupView:
    id: str
    kind: str  # "room" | "zone"
    name: str
    archetype: str
    light_ids: tuple[str, ...]
    grouped_light_id: str | None


@dataclass(frozen=True)
class SceneView:
    id: str
    name: str
    group_id: str
    actions: tuple[Raw, ...] = field(default_factory=tuple)
    palette_rgb: tuple[colors.RGB, ...] = field(default_factory=tuple)
    active: bool = False

    @property
    def preview_colors(self) -> list[colors.RGB]:
        result: list[colors.RGB] = []
        for entry in self.actions:
            action = entry.get("action", {})
            if not action.get("on", {}).get("on", True):
                continue
            if "color" in action and action["color"].get("xy"):
                xy = action["color"]["xy"]
                result.append(colors.xy_to_rgb(xy["x"], xy["y"]))
            elif "color_temperature" in action and action["color_temperature"].get("mirek"):
                result.append(colors.mirek_to_rgb(action["color_temperature"]["mirek"]))
            else:
                result.append(colors.kelvin_to_rgb(2700))
        if not result:
            result = list(self.palette_rgb)
        # Distinct colors, stable order: a gradient of 2-4 stops reads best.
        unique: list[colors.RGB] = []
        for rgb in result:
            if all(sum(abs(a - b) for a, b in zip(rgb, u)) > 0.12 for u in unique):
                unique.append(rgb)
        return unique[:4]

    @classmethod
    def from_raw(cls, raw: Raw) -> "SceneView":
        palette: list[colors.RGB] = []
        for item in (raw.get("palette") or {}).get("color", []):
            xy = (item.get("color") or {}).get("xy")
            if xy:
                palette.append(colors.xy_to_rgb(xy["x"], xy["y"]))
        status = (raw.get("status") or {}).get("active", "inactive")
        return cls(
            id=raw["id"],
            name=(raw.get("metadata") or {}).get("name", "Scene"),
            group_id=(raw.get("group") or {}).get("rid", ""),
            actions=tuple(raw.get("actions") or ()),
            palette_rgb=tuple(palette),
            active=status not in ("inactive", None),
        )
