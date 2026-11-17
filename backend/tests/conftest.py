"""Fixture & helper test bersama."""

import pytest

from optiqm.core import discover, get


@pytest.fixture(scope="session", autouse=True)
def _discover():
    discover()


def run_template(key: str):
    """Jalankan modul dengan data template-nya sendiri (smoke test)."""
    mod = get(key)
    return mod.solve(mod.template())


def metric(result, label: str):
    for m in result.summary:
        if m.label == label:
            return m.value
    raise KeyError(f"Metric '{label}' tidak ada: {[m.label for m in result.summary]}")
