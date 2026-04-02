# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from config import AppConfig


@dataclass
class AppState:
    """Centrální runtime stav aplikace.

    Drží hodnoty, které se mění za běhu a nejsou součástí dokumentu.
    Inicializuje se z AppConfig — přetrvávající nastavení se čtou
    z konfigurace, dočasné hodnoty (trim_mode, current_tool) mají
    pevné výchozí hodnoty.
    """

    # --- snap ---
    snap_enabled: bool = True
    hv_band_in_px: float = 10.0
    hv_band_out_px: float = 16.0

    # --- výběr ---
    select_tol_px: float = 6.0

    # --- mřížka ---
    grid_ox: float = 0.0
    grid_oy: float = 0.0

    # --- nástroje ---
    current_tool: str = 'selection'
    trim_mode: bool = False

    @staticmethod
    def from_config(cfg: AppConfig) -> 'AppState':
        """Vytvoří AppState načtením hodnot z AppConfig."""
        return AppState(
            snap_enabled=bool(cfg.flags.SNAP_ENABLED),
            hv_band_in_px=float(getattr(cfg.flags, 'HV_BAND_IN_PX', 10.0)),
            hv_band_out_px=float(getattr(cfg.flags, 'HV_BAND_OUT_PX', 16.0)),
        )
