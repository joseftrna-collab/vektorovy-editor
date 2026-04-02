# -*- coding: utf-8 -*-
"""Lehký event tracer.

Použití:
    from core.tracer import trace
    trace('SNAP', 'find', result='line_end', x=12.0, y=34.0)

Overhead při vypnutém traceru: jediná podmínka (if not _enabled: return).
Výstup: soubor trace.log + volitelný live UI panel.
"""
from __future__ import annotations
import time
from pathlib import Path
from typing import Optional, Callable

# --- Kategorie ---
CATEGORIES = ('TOOL', 'SNAP', 'MARKER', 'HV', 'CMD', 'MOVE')

# --- Runtime stav (mění se přes configure()) ---
_enabled: bool = False
_active: set[str] = set()          # povolené kategorie
_file_on: bool = True
_ui_on: bool = False
_ui_cb: Optional[Callable[[str], None]] = None   # callback → UI panel
_log_path: Path = Path('trace.log')
_file_handle = None


def configure(enabled: bool,
              categories: list[str] | None = None,
              file_out: bool = True,
              ui_out: bool = False,
              ui_callback: Callable[[str], None] | None = None,
              log_path: str = 'trace.log') -> None:
    """Nastaví tracer. Volat z App.__init__ nebo při změně configu."""
    global _enabled, _active, _file_on, _ui_on, _ui_cb, _log_path, _file_handle
    _enabled  = enabled
    _active   = set(categories) if categories else set(CATEGORIES)
    _file_on  = file_out
    _ui_on    = ui_out
    _ui_cb    = ui_callback
    _log_path = Path(log_path)
    # znovu otevřeme soubor
    if _file_handle is not None:
        try: _file_handle.close()
        except Exception: pass
        _file_handle = None
    if _enabled and _file_on:
        try:
            _file_handle = _log_path.open('a', encoding='utf-8')
            _file_handle.write(f'\n=== trace start {time.strftime("%Y-%m-%d %H:%M:%S")} ===\n')
            _file_handle.flush()
        except Exception:
            _file_handle = None


def trace(category: str, event: str, **kwargs) -> None:
    """Zaloguje událost. Nulový overhead pokud not _enabled."""
    if not _enabled:
        return
    if category not in _active:
        return
    ts = f'{time.time() % 1000:.3f}'
    kv = '  '.join(f'{k}={v!r}' for k, v in kwargs.items())
    line = f'[{ts}] {category:6s} {event}  {kv}'
    if _file_on and _file_handle is not None:
        try:
            _file_handle.write(line + '\n')
            _file_handle.flush()
        except Exception:
            pass
    if _ui_on and _ui_cb is not None:
        try:
            _ui_cb(line)
        except Exception:
            pass


def close() -> None:
    """Zavře log soubor — volat při ukončení aplikace."""
    global _file_handle
    if _file_handle is not None:
        try: _file_handle.close()
        except Exception: pass
        _file_handle = None
