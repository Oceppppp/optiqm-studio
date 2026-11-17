"""Hierarki exception aplikasi."""


class OptiQMError(Exception):
    """Basis semua error yang aman ditampilkan ke pengguna."""


class InputError(OptiQMError):
    """Data input tidak valid / tidak lengkap."""


class SolverError(OptiQMError):
    """Solver gagal (mis. infeasible, unbounded, tidak konvergen)."""


class ModuleNotFound(OptiQMError):
    """Modul yang diminta tidak terdaftar."""
