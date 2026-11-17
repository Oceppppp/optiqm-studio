"""Inti framework OptiQM: kontrak modul, format data & hasil, registry."""

from .base_module import BaseModule
from .errors import InputError, ModuleNotFound, OptiQMError, SolverError
from .registry import all_modules, discover, get, register
from .result import Chart, Metric, ModuleResult, Table
from .sheet import ParamSpec, SheetData

__all__ = [
    "BaseModule", "Chart", "InputError", "Metric", "ModuleNotFound", "ModuleResult",
    "OptiQMError", "ParamSpec", "SheetData", "SolverError", "Table",
    "all_modules", "discover", "get", "register",
]
