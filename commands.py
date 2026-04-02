# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Tuple
from collections import deque

# ---------------------------------------------------------------------------
# Abstraktní základ
# ---------------------------------------------------------------------------

class Command:
    """Základ pro všechny příkazy. Každý příkaz musí implementovat do() a undo()."""

    def do(self) -> None:
        raise NotImplementedError

    def undo(self) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Konkrétní příkazy
# ---------------------------------------------------------------------------

class AddLineCmd(Command):
    """Přidá úsečku do dokumentu.

    Použití: LineTool (nová čára) i SelectionTool (Ctrl+drag = kopie).
    Undo: odstraní seg z doc.objects.
    Redo: vloží seg zpět.
    """

    def __init__(self, doc, seg):
        self._doc = doc
        self._seg = seg

    def do(self) -> None:
        self._doc.add_object(self._seg)

    def undo(self) -> None:
        self._doc.remove_object(self._seg)


class TransformLineCmd(Command):
    """Zpětně kompatibilní alias pro TransformCmd s LineSeg tuple stavy.

    Nový kód by měl používat TransformCmd přímo.
    """

    def __init__(self, seg, old_coords: Tuple, new_coords: Tuple):
        self._seg = seg
        self._old = {'x1': old_coords[0], 'y1': old_coords[1],
                     'x2': old_coords[2], 'y2': old_coords[3]}
        self._new = {'x1': new_coords[0], 'y1': new_coords[1],
                     'x2': new_coords[2], 'y2': new_coords[3]}

    def do(self) -> None:
        self._seg.apply_state(self._new)

    def undo(self) -> None:
        self._seg.apply_state(self._old)


class TransformCmd(Command):
    """Generický příkaz pro změnu stavu libovolného DrawObject.

    Používá DrawObject.get_state() / apply_state(dict).
    Příkaz se pushne v on_up — do() aplikuje new_state (pro redo),
    protože změna již proběhla živě během dragu.
    """

    def __init__(self, obj, old_state: dict, new_state: dict):
        self._obj = obj
        self._old = old_state
        self._new = new_state

    def do(self) -> None:
        self._obj.apply_state(self._new)

    def undo(self) -> None:
        self._obj.apply_state(self._old)


class TrimCmd(Command):
    """Zaznamená trim operaci: jedna čára nahrazena N úsečkami.

    orig  — původní LineSeg (byl v dokumentu)
    kept  — seznam LineSeg, které trim zachoval (nové objekty)
    index — pozice orig v doc.lines (pro vložení zpět na správné místo)
    """

    def __init__(self, doc, orig, kept: List, index: int):
        self._doc = doc
        self._orig = orig
        self._kept = kept
        self._index = index

    def do(self) -> None:
        """Odstraní orig, vloží kept na jeho místo v doc.objects."""
        objs = self._doc.objects
        if self._orig in objs:
            idx = objs.index(self._orig)
            self._doc.remove_object(self._orig)
            for seg in reversed(self._kept):
                objs.insert(idx, seg)
        else:
            # redo: orig není v doc, jen přidáme kept
            for seg in self._kept:
                if seg not in objs:
                    self._doc.add_object(seg)

    def undo(self) -> None:
        """Odstraní kept, vloží orig zpět na původní místo."""
        objs = self._doc.objects
        # zjisti pozici prvního kept segmentu
        idx = None
        for seg in self._kept:
            if seg in objs:
                idx = objs.index(seg)
                break
        for seg in self._kept:
            if seg in objs:
                self._doc.remove_object(seg)
        if idx is not None:
            objs.insert(idx, self._orig)
        else:
            self._doc.add_object(self._orig)


# ---------------------------------------------------------------------------
# Multi-select příkazy
# ---------------------------------------------------------------------------

class MoveSelectionCmd(Command):
    """Přesune skupinu objektů o (dx, dy).

    old_states — {obj: dict} snapshot get_state() před přesunem.
    Změna neproběhla živě (snap apply_for_move); do() ji aplikuje.
    """

    def __init__(self, objs: list, old_states: dict, dx: float, dy: float):
        self._objs = list(objs)
        self._old = dict(old_states)
        self._dx = dx
        self._dy = dy

    def do(self) -> None:
        for obj in self._objs:
            old = self._old[obj]
            new = {k: v + (self._dy if 'y' in k else self._dx)
                   for k, v in old.items()}
            obj.apply_state(new)

    def undo(self) -> None:
        for obj, state in self._old.items():
            obj.apply_state(state)


class CopySelectionCmd(Command):
    """Vytvoří kopie skupiny objektů a přidá je do dokumentu.

    Kopie jsou nové instance — originály zůstávají nedotčeny.
    copies je veřejný atribut — SelectionTool si po push() může
    přepnout výběr na nové kopie.
    """

    def __init__(self, doc, objs: list, dx: float, dy: float):
        self._doc = doc
        self._dx = dx
        self._dy = dy
        # kopie přes from_json — type(obj) má from_json jako staticmethod
        copies = []
        for obj in objs:
            copy = type(obj).from_json(obj.to_json())
            state = copy.get_state()
            copy.apply_state({k: v + (dy if 'y' in k else dx) for k, v in state.items()})
            copies.append(copy)
        self.copies = copies

    def do(self) -> None:
        for obj in self.copies:
            self._doc.add_object(obj)

    def undo(self) -> None:
        for obj in self.copies:
            self._doc.remove_object(obj)


class RotateSelectionCmd(Command):
    """Otočí skupinu objektů kolem pivotu o úhel angle (radiány).

    old_coords — {obj: (x1,y1,x2,y2)} snapshot před rotací.
    Změna už proběhla živě; do() ji zopakuje pro redo.
    """

    def __init__(self, objs: list, old_coords: dict,
                 px: float, py: float, angle: float):
        self._objs = list(objs)
        self._old = dict(old_coords)
        self._px = px
        self._py = py
        self._angle = angle

    def do(self) -> None:
        from services.transform import rotate_object
        for obj in self._objs:
            rotate_object(obj, self._px, self._py, self._angle)

    def undo(self) -> None:
        for obj, state in self._old.items():
            obj.apply_state(state)


class DeleteSelectionCmd(Command):
    """Odstraní skupinu objektů z dokumentu.

    Undo vloží objekty zpět na jejich původní pozice v doc.objects,
    aby byl výsledek deterministický při opakovaném undo/redo.
    """

    def __init__(self, doc, objs: list):
        self._doc = doc
        self._objs = list(objs)
        self._indices: list = []

    def do(self) -> None:
        self._indices = [
            self._doc.objects.index(obj)
            for obj in self._objs
            if obj in self._doc.objects
        ]
        for obj in self._objs:
            self._doc.remove_object(obj)

    def undo(self) -> None:
        # Vkládáme v obráceném pořadí, aby indexy zůstaly platné.
        for idx, obj in sorted(zip(self._indices, self._objs), reverse=True):
            self._doc.objects.insert(idx, obj)


# ---------------------------------------------------------------------------
# Historie
# ---------------------------------------------------------------------------

class CommandHistory:
    """Zásobník příkazů pro undo/redo.

    Použití:
        history.push(cmd)   — provede cmd.do() a uloží do undo zásobníku
        history.undo()      — provede cmd.undo() a přesune do redo zásobníku
        history.redo()      — provede cmd.do() a přesune zpět do undo zásobníku
    """

    def __init__(self, maxlen: int = 100):
        self._undo: deque[Command] = deque(maxlen=maxlen)
        self._redo: deque[Command] = deque(maxlen=maxlen)

    def push(self, cmd: Command) -> None:
        """Provede příkaz a uloží ho. Vymaže redo zásobník."""
        cmd.do()
        self._undo.append(cmd)
        self._redo.clear()

    def undo(self) -> bool:
        """Vrátí poslední příkaz. Vrací True při úspěchu."""
        if not self._undo:
            return False
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        return True

    def redo(self) -> bool:
        """Zopakuje poslední odvolaný příkaz. Vrací True při úspěchu."""
        if not self._redo:
            return False
        cmd = self._redo.pop()
        cmd.do()
        self._undo.append(cmd)
        return True

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)
