"""Minimal ctypes driver for the shared ngspice library (libngspice.so.0, installed with KiCad)."""
import ctypes
from ctypes import CFUNCTYPE, POINTER, Structure, c_bool, c_char_p, c_double, c_int, c_short, c_void_p

import numpy as np


class _VectorInfo(Structure):
    _fields_ = [("v_name", c_char_p), ("v_type", c_int), ("v_flags", c_short),
                ("v_realdata", POINTER(c_double)), ("v_compdata", c_void_p), ("v_length", c_int)]


_SendChar = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
_SendStat = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
_ControlledExit = CFUNCTYPE(c_int, c_int, c_bool, c_bool, c_int, c_void_p)
_BGRunning = CFUNCTYPE(c_int, c_bool, c_int, c_void_p)


class NgSpice:
    def __init__(self, libname="libngspice.so.0", verbose=False):
        self.lib = ctypes.CDLL(libname)
        self.verbose = verbose
        self.log = []
        # keep references so the callbacks are not garbage collected
        self._cb = (_SendChar(self._on_char), _SendStat(lambda *_: 0),
                    _ControlledExit(self._on_exit), _BGRunning(lambda *_: 0))
        self.lib.ngSpice_Init.argtypes = [_SendChar, _SendStat, _ControlledExit, c_void_p, c_void_p,
                                          _BGRunning, c_void_p]
        self.lib.ngSpice_Circ.argtypes = [POINTER(c_char_p)]
        self.lib.ngSpice_Command.argtypes = [c_char_p]
        self.lib.ngGet_Vec_Info.argtypes = [c_char_p]
        self.lib.ngGet_Vec_Info.restype = POINTER(_VectorInfo)
        self.lib.ngSpice_Init(self._cb[0], self._cb[1], self._cb[2], None, None, self._cb[3], None)

    def _on_char(self, msg, _id, _user):
        text = msg.decode(errors="replace")
        self.log.append(text)
        if self.verbose:
            print(text)
        return 0

    def _on_exit(self, status, *_):
        raise RuntimeError(f"ngspice exited with status {status}")

    def cmd(self, command):
        if self.lib.ngSpice_Command(command.encode()) != 0:
            raise RuntimeError(f"ngspice command failed: {command}")

    def run(self, netlist: str):
        """Load and run a netlist; returns nothing, fetch results with vec()."""
        self.log.clear()
        self.cmd("destroy all")
        lines = [ln for ln in netlist.strip().splitlines()] + [".end"]
        arr = (c_char_p * (len(lines) + 1))(*[ln.encode() for ln in lines], None)
        if self.lib.ngSpice_Circ(arr) != 0:
            raise RuntimeError("ngspice rejected circuit:\n" + "".join(self.log[-20:]))
        self.cmd("run")
        errors = [ln for ln in self.log if "error" in ln.lower() and "stderr" in ln.lower()]
        if errors:
            raise RuntimeError("ngspice errors:\n" + "\n".join(errors))

    def vec(self, name: str) -> np.ndarray:
        """Real vectors come back as float arrays, AC vectors as complex arrays."""
        info = self.lib.ngGet_Vec_Info(name.encode())
        if not info:
            raise KeyError(name)
        n = info.contents.v_length
        if info.contents.v_realdata:
            return np.ctypeslib.as_array(info.contents.v_realdata, shape=(n,)).copy()
        if info.contents.v_compdata:
            raw = np.ctypeslib.as_array(ctypes.cast(info.contents.v_compdata, POINTER(c_double)), shape=(2 * n,))
            return raw[0::2] + 1j * raw[1::2]
        raise KeyError(name)


def rising_edges(t, v, level):
    """Linearly interpolated times where v crosses `level` upwards."""
    above = v >= level
    idx = np.nonzero(~above[:-1] & above[1:])[0]
    return t[idx] + (level - v[idx]) * (t[idx + 1] - t[idx]) / (v[idx + 1] - v[idx])
