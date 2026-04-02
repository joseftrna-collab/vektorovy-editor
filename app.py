# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from config import AppConfig
from app_state import AppState
from model.doc import Document
from services.file_service import FileService
from ui.view import CanvasView
from ui.router import EventRouter
from ui.app_ui import AppUI
from services.ldo import LDOService
from services.viewport import Viewport
from services.dim import DimService
from services.overlays import OverlaysService
from services.snap_marker_manager import SnapMarkerManager
from tools.selection import SelectionTool
from tools.line import LineTool
from tools.trim import TrimTool
from ui.snap import SnapManager
from core.commands import CommandHistory
from core import tracer


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('VE M9 Full')
        self.cfg = AppConfig.load()
        self.state = AppState.from_config(self.cfg)
        self.doc = Document()
        self.canvas = tk.Canvas(root, bg='white', width=1000, height=700)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.view     = CanvasView(self.canvas)
        self.viewport = Viewport()
        self.ldo      = LDOService(self.canvas, self.viewport)
        self.overlays = OverlaysService(self.canvas)
        self.router   = EventRouter(self)
        self.snap     = SnapManager(self, tol_px=10.0)
        self.snap.grid_enabled = bool(self.cfg.flags.GRID_SNAP)
        self.snap_marker = SnapMarkerManager(self.overlays, self.viewport)
        self.dim      = DimService(self.canvas)
        self.file_service = FileService(root)
        self.history  = CommandHistory()
        self.trim_tool = TrimTool(self)
        self.tools = {'selection': SelectionTool(self), 'line': LineTool(self)}
        self.tool  = self.tools[self.state.current_tool]
        self.canvas.bind('<Motion>',          lambda e: self.router.motion(*self._e2doc(e), e))
        self.canvas.bind('<Button-1>',        lambda e: self._on_canvas_click(e))
        self.canvas.bind('<ButtonRelease-1>', lambda e: self.router.up(*self._e2doc(e), e))
        self.canvas.bind('<Button-3>',        lambda e: self.router.right(*self._e2doc(e), e))
        # zoom kolečkem
        self.canvas.bind('<MouseWheel>',      self._on_mousewheel)      # Windows / macOS
        self.canvas.bind('<Button-4>',        lambda e: self._zoom(e, +1))  # Linux scroll up
        self.canvas.bind('<Button-5>',        lambda e: self._zoom(e, -1))  # Linux scroll down
        # pan středním tlačítkem
        self.canvas.bind('<Button-2>',        self._pan_start)
        self.canvas.bind('<B2-Motion>',       self._pan_move)
        self.canvas.bind('<ButtonRelease-2>', self._pan_end)
        self._pan_last: tuple[float, float] | None = None
        # Tab je Tkinterem interceptován jako focus-traversal dřív než bind_all('<Key>').
        # Explicitní binding na canvas s 'break' ho správně zachytí.
        self.canvas.bind('<Tab>', self._on_canvas_tab)
        self.canvas.focus_set()   # canvas dostane focus při startu
        self.ui = AppUI(self)
        # tracer — inicializace (UI callback přidá AppUI po svém buildu)
        self._init_tracer()
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _init_tracer(self, ui_cb=None):
        tc = self.cfg.trace
        tracer.configure(
            enabled=tc.enabled,
            categories=tc.categories,
            file_out=tc.file,
            ui_out=tc.ui_panel,
            ui_callback=ui_cb,
        )

    # ------------------------------------------------------------------
    # Veřejné metody — volá je AppUI
    # ------------------------------------------------------------------

    def set_tool(self, name: str):
        tracer.trace('TOOL', 'set_tool', name=name)
        self.state.current_tool = name
        self.state.trim_mode = False
        try: self.tool.cancel()
        except Exception: pass
        self.tool = self.tools[name]
        self.snap_marker.clear()
        self.view.clear()
        self.overlays.clear()
        self.ldo.clear_half_axis()
        for obj in self.doc.objects:
            obj.render(self.view, self.viewport)
        self.ui.refresh_status()

    def toggle_snap(self):
        self.state.snap_enabled = not self.state.snap_enabled
        self.cfg.flags.SNAP_ENABLED = bool(self.state.snap_enabled)
        self.cfg.save()
        tracer.trace('TOOL', 'toggle_snap', enabled=self.state.snap_enabled)
        if not self.state.snap_enabled:
            try: self.tool.cancel()
            except Exception: pass
            self.ldo.clear_half_axis()
        self.ui.refresh_status()

    def toggle_grid(self):
        self.snap.grid_enabled = not self.snap.grid_enabled
        self.cfg.flags.GRID_SNAP = bool(self.snap.grid_enabled)
        self.cfg.save()
        self.ui.refresh_status()

    def toggle_nodes(self):
        self.cfg.flags.NODES_SNAP = not bool(self.cfg.flags.NODES_SNAP)
        self.cfg.save()
        self.ui.refresh_status()

    def toggle_trace(self):
        """Přepne tracer on/off za běhu, uloží do configu."""
        self.cfg.trace.enabled = not self.cfg.trace.enabled
        self.cfg.save()
        self._init_tracer(ui_cb=getattr(self.ui, '_trace_cb', None))
        self.ui.refresh_status()

    def zoom_fit(self):
        """Přizpůsobí zoom tak, aby byly vidět všechny objekty."""
        cw = self.canvas.winfo_width()  or 1000
        ch = self.canvas.winfo_height() or 700
        self.viewport.fit(self.doc.lines, cw, ch)
        self._full_redraw()
        try: self.ui.refresh_status()
        except Exception: pass

    def zoom_reset(self):
        """Resetuje zoom na 1:1."""
        self.viewport.reset()
        self._full_redraw()
        try: self.ui.refresh_status()
        except Exception: pass

    def save(self):    self.file_service.save(self.doc)
    def save_as(self): self.file_service.save_as(self.doc)

    def undo(self):
        if self.history.undo():
            self._full_redraw()

    def redo(self):
        if self.history.redo():
            self._full_redraw()

    def _full_redraw(self):
        self.view.clear()
        self.overlays.clear()
        self.ldo.clear_half_axis()
        for obj in self.doc.objects:
            obj.render(self.view, self.viewport)
        if self.state.current_tool == 'selection':
            try: self.tools['selection']._show()
            except Exception: pass

    def load(self):
        self.file_service.load(self._on_document_loaded)

    def _on_document_loaded(self, doc: Document):
        self.doc = doc
        self.history.clear()
        cw = self.canvas.winfo_width()  or 1000
        ch = self.canvas.winfo_height() or 700
        self.viewport.fit(self.doc.lines, cw, ch)
        self._full_redraw()

    def _e2doc(self, e) -> tuple[float, float]:
        """Převede canvas-space souřadnice eventu do doc-space."""
        return self.viewport.to_doc(e.x, e.y)

    def _on_mousewheel(self, e):
        # Windows: e.delta = ±120 násobky; macOS: ±1
        direction = 1 if e.delta > 0 else -1
        self._zoom(e, direction)

    def _zoom(self, e, direction: int):
        self.viewport.zoom_step(e.x, e.y, direction)
        self._full_redraw()

    def _pan_start(self, e):
        self._pan_last = (e.x, e.y)

    def _pan_move(self, e):
        if self._pan_last is None:
            return
        dx = e.x - self._pan_last[0]
        dy = e.y - self._pan_last[1]
        self.viewport.pan_x += dx
        self.viewport.pan_y += dy
        self._pan_last = (e.x, e.y)
        self._full_redraw()

    def _pan_end(self, e):
        self._pan_last = None

    def _on_canvas_click(self, e):
        """Klik na canvas — canvas dostane focus a zpracuje event."""
        self.canvas.focus_set()
        self.router.down(*self._e2doc(e), e)

    def _on_canvas_tab(self, e):
        """Tab zachycený explicitně na canvas — deleguj na tool, zastav traversal."""
        if self.state.current_tool == 'line':
            tool_fn = getattr(self.tool, 'on_key', None)
            if callable(tool_fn):
                tool_fn('Tab', '')
        return 'break'

    def _on_close(self):
        tracer.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == '__main__':
    main()
