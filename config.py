# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
CONFIG_FILE = Path(__file__).with_name('config.json')

@dataclass
class TraceConfig:
    enabled: bool = False
    file: bool = True
    ui_panel: bool = False
    ui_lines: int = 20
    categories: list = field(default_factory=lambda: ["TOOL", "SNAP", "MARKER", "HV", "CMD"])

@dataclass
class Flags:
    AXIS_GUIDES: bool = True
    HALF_AXES: bool = True
    SNAP_ENABLED: bool = True
    GRID_SNAP: bool = False
    NODES_SNAP: bool = True
    HV_BAND_IN_PX: float = 10.0
    HV_BAND_OUT_PX: float = 16.0
    CHAIN_LINE: bool = True

@dataclass
class Keymap:
    TOOL_SELECTION: str = 's'
    TOOL_LINE: str = 'l'
    SAVE: str = 'ctrl-s'
    LOAD: str = 'ctrl-o'
    SNAP_TOGGLE: str = 'f8'

@dataclass
class AppConfig:
    flags: Flags
    keymap: Keymap
    trace: TraceConfig = field(default_factory=TraceConfig)

    @staticmethod
    def load() -> 'AppConfig':
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
                tc_raw = data.get('trace', {})
                tc = TraceConfig(**{k: v for k, v in tc_raw.items()
                                    if k in TraceConfig.__dataclass_fields__})
                return AppConfig(
                    Flags(**data.get('flags', {})),
                    Keymap(**data.get('keymap', {})),
                    tc,
                )
            except Exception:
                pass
        return AppConfig(Flags(), Keymap())

    def save(self) -> None:
        try:
            d = {
                'flags':  asdict(self.flags),
                'keymap': asdict(self.keymap),
                'trace':  asdict(self.trace),
            }
            CONFIG_FILE.write_text(json.dumps(d, indent=2), encoding='utf-8')
        except Exception:
            pass

    @staticmethod
    def reset() -> 'AppConfig':
        cfg = AppConfig(Flags(), Keymap())
        cfg.save()
        return cfg
