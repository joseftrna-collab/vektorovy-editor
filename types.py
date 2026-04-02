
# -*- coding: utf-8 -*-
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional, Tuple


class DrawObject:
    """Společný základ pro všechny kreslené objekty.

    Povinné pro každý odvozený tvar:
      bbox()             -> (x_min, y_min, x_max, y_max)
      endpoints()        -> [(x,y), ...]  krajní body pro snap/handles
      snap_candidates()  -> [(x,y,kind), ...]  všechny snap body + projekce
      distance_to()      -> float  vzdálenost bodu od objektu (hit-test)
      render()           -> None   vykreslení na CanvasView
      trim_at()          -> [DrawObject, ...]  výsledek trimu
      get_state()        -> dict   kompletní stav pro undo
      apply_state()      -> None   obnova stavu z dict
      intersect_hv_ray() -> (x,y) | None  průsečík s HV poloosou
      kind               -> str   identifikátor typu
    """

    kind: str = 'base'

    # ------------------------------------------------------------------
    # Povinné — geometrie
    # ------------------------------------------------------------------

    def bbox(self) -> Tuple[float, float, float, float]:
        raise NotImplementedError

    def endpoints(self) -> list:
        """Krajní/charakteristické body — pro handles a snap endpoints."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Krok 1 — snap_candidates
    # ------------------------------------------------------------------

    def snap_candidates(self, x: float, y: float) -> list:
        """Vrátí seznam (px, py, kind) pro snap engine.

        kind hodnoty: 'line_end', 'line_mid', 'line_body', 'center', ...
        Každý tvar přidá body relevantní pro svou geometrii.
        """
        return []

    # ------------------------------------------------------------------
    # Krok 2 — distance_to
    # ------------------------------------------------------------------

    def distance_to(self, x: float, y: float) -> float:
        """Nejkratší vzdálenost bodu (x,y) od objektu.

        Používá se v hit-testu (nearest object) a selection.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Krok 3 — render
    # ------------------------------------------------------------------

    def render(self, view, viewport) -> None:
        """Vykreslí objekt na view v canvas-space přes viewport."""
        raise NotImplementedError

    def render_preview(self, view, viewport) -> None:
        """Vykreslí objekt jako preview (přerušovaná modrá čára)."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Krok 4 — trim_at
    # ------------------------------------------------------------------

    def trim_at(self, x: float, y: float,
                cutters: list) -> list:
        """Vrátí seznam DrawObject po trimu v bodě (x,y) s danými řezači.

        Výchozí implementace: objekt nelze trimnout → vrátí [self].
        Každý tvar přepíše tuto metodu pokud podporuje trim.
        """
        return [self]

    # ------------------------------------------------------------------
    # Krok 5 — get_state / apply_state  (pro generický undo/redo)
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Vrátí kompletní stav objektu jako dict (pro TransformCmd)."""
        raise NotImplementedError

    def apply_state(self, state: dict) -> None:
        """Obnoví stav objektu z dict (undo/redo)."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Krok 6 — intersect_hv_ray  (pro HV snap průsečíky)
    # ------------------------------------------------------------------

    def intersect_hv_ray(self, base_x: float, base_y: float,
                         hv: str, mx: float, my: float) -> Optional[Tuple[float, float]]:
        """Průsečík objektu s HV poloosou vycházející z (base_x, base_y).

        hv    — 'h' nebo 'v'
        mx,my — aktuální pozice myši (určuje směr poloosy)
        Vrátí (ix, iy) nebo None.
        """
        return None

    # ------------------------------------------------------------------
    # Serializace
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        raise NotImplementedError

    @staticmethod
    def from_json(data: dict) -> 'DrawObject':
        raise NotImplementedError


# ---------------------------------------------------------------------------
# LineSeg — implementace všech metod DrawObject
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class LineSeg(DrawObject):
    """Úsečka definovaná dvěma krajními body."""

    x1: float
    y1: float
    x2: float
    y2: float
    kind: str = field(default='line', init=False, repr=False)

    # --- geometrie ---

    def bbox(self) -> Tuple[float, float, float, float]:
        return (min(self.x1, self.x2), min(self.y1, self.y2),
                max(self.x1, self.x2), max(self.y1, self.y2))

    def endpoints(self) -> list:
        return [(self.x1, self.y1), (self.x2, self.y2)]

    # --- krok 1: snap_candidates ---

    def snap_candidates(self, x: float, y: float) -> list:
        """Koncové body, střed a kolmá projekce na tělo úsečky."""
        mx = (self.x1 + self.x2) / 2.0
        my = (self.y1 + self.y2) / 2.0
        results = [
            (self.x1, self.y1, 'line_end'),
            (self.x2, self.y2, 'line_end'),
            (mx, my, 'line_mid'),
        ]
        # kolmá projekce na tělo (vynecháme body blízko konců/středu)
        ddx = self.x2 - self.x1
        ddy = self.y2 - self.y1
        seg_len2 = ddx * ddx + ddy * ddy
        if seg_len2 > 0:
            t = max(0.0, min(1.0,
                ((x - self.x1) * ddx + (y - self.y1) * ddy) / seg_len2))
            if 0.01 < t < 0.99 and abs(t - 0.5) > 0.01:
                results.append((self.x1 + t * ddx, self.y1 + t * ddy, 'line_body'))
        return results

    # --- krok 2: distance_to ---

    def distance_to(self, x: float, y: float) -> float:
        """Vzdálenost bodu od úsečky (kolmá projekce nebo konec)."""
        ddx = self.x2 - self.x1
        ddy = self.y2 - self.y1
        seg_len2 = ddx * ddx + ddy * ddy
        if seg_len2 == 0:
            return math.hypot(x - self.x1, y - self.y1)
        t = max(0.0, min(1.0,
            ((x - self.x1) * ddx + (y - self.y1) * ddy) / seg_len2))
        px = self.x1 + t * ddx
        py = self.y1 + t * ddy
        return math.hypot(x - px, y - py)

    # --- krok 3: render ---

    def render(self, view, viewport) -> None:
        cx1, cy1 = viewport.to_canvas(self.x1, self.y1)
        cx2, cy2 = viewport.to_canvas(self.x2, self.y2)
        view.draw_line(cx1, cy1, cx2, cy2)

    def render_preview(self, view, viewport) -> None:
        cx1, cy1 = viewport.to_canvas(self.x1, self.y1)
        cx2, cy2 = viewport.to_canvas(self.x2, self.y2)
        view.draw_preview_line(cx1, cy1, cx2, cy2)

    # --- krok 4: trim_at ---

    def trim_at(self, x: float, y: float, cutters: list) -> list:
        """Rozdělí úsečku průsečíky s cutters, vrátí segmenty bez toho pod kurzorem.

        Vrací [self] pokud žádný průsečík, [] pokud zmizí celý segment.
        """
        from services.geom_split import intersect, split_line
        hits = []
        for cutter in cutters:
            if cutter is self:
                continue
            pt = intersect(self, cutter)
            if pt is not None:
                hits.append(pt)
        if not hits:
            return [self]
        segs = split_line(self, hits)
        if not segs:
            return [self]
        def mid_d2(s):
            return ((s.x1+s.x2)/2 - x)**2 + ((s.y1+s.y2)/2 - y)**2
        closest = min(segs, key=mid_d2)
        return [s for s in segs if s is not closest]

    # --- krok 5: get_state / apply_state ---

    def get_state(self) -> dict:
        return {'x1': self.x1, 'y1': self.y1,
                'x2': self.x2, 'y2': self.y2}

    def apply_state(self, state: dict) -> None:
        self.x1 = state['x1']; self.y1 = state['y1']
        self.x2 = state['x2']; self.y2 = state['y2']

    # --- krok 6: intersect_hv_ray ---

    def intersect_hv_ray(self, base_x: float, base_y: float,
                         hv: str, mx: float, my: float) -> Optional[Tuple[float, float]]:
        EPS = 1e-9
        if hv == 'h':
            dy = self.y2 - self.y1
            if abs(dy) < EPS:
                return None
            t = (base_y - self.y1) / dy
            if not (0.0 <= t <= 1.0):
                return None
            ix = self.x1 + t * (self.x2 - self.x1)
            if (mx >= base_x and ix < base_x) or (mx < base_x and ix > base_x):
                return None
            return (ix, base_y)
        else:  # 'v'
            dx = self.x2 - self.x1
            if abs(dx) < EPS:
                return None
            t = (base_x - self.x1) / dx
            if not (0.0 <= t <= 1.0):
                return None
            iy = self.y1 + t * (self.y2 - self.y1)
            if (my >= base_y and iy < base_y) or (my < base_y and iy > base_y):
                return None
            return (base_x, iy)

    # --- serializace ---

    def to_json(self) -> dict:
        return {'kind': 'line',
                'x1': self.x1, 'y1': self.y1,
                'x2': self.x2, 'y2': self.y2}

    @staticmethod
    def from_json(data: dict) -> 'LineSeg':
        return LineSeg(float(data['x1']), float(data['y1']),
                       float(data['x2']), float(data['y2']))


# ---------------------------------------------------------------------------
# Interní helper — průsečíky dvou DrawObject pro trim_at
# ---------------------------------------------------------------------------

def _line_intersections(a: LineSeg, b: DrawObject) -> list:
    """Průsečíky úsečky a s objektem b. Vrátí seznam (x, y)."""
    if not isinstance(b, LineSeg):
        return []
    # průsečík dvou úseček
    EPS = 1e-9
    dx1, dy1 = a.x2 - a.x1, a.y2 - a.y1
    dx2, dy2 = b.x2 - b.x1, b.y2 - b.y1
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < EPS:
        return []
    t = ((b.x1 - a.x1) * dy2 - (b.y1 - a.y1) * dx2) / denom
    u = ((b.x1 - a.x1) * dy1 - (b.y1 - a.y1) * dx1) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return [(a.x1 + t * dx1, a.y1 + t * dy1)]
    return []
