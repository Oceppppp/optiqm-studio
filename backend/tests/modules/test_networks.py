"""Test modul jaringan: Shortest Route, Minimal Spanning Tree, Max Flow."""

import pytest

from conftest import metric, run_template


def test_shortest_route_template():
    r = run_template("shortest_route")
    # 1->2 (100) -> 3 (50) -> 5 (40) -> 6 (100) = 290
    assert metric(r, "Total Jarak Terpendek") == pytest.approx(290)


def test_mst_template():
    r = run_template("minimal_spanning_tree")
    # 1-2(2), 1-3(2), 3-4(1), 2-5(3), 3-6(4), 6-7(5), 7-8(3) = 20
    assert metric(r, "Total Panjang / Biaya Minimum") == pytest.approx(20)


def test_max_flow_template():
    r = run_template("max_flow")
    # Sisi keluar dari 1: (1->2:3, 1->3:10, 1->4:2). Ke 6: (2->6:2, 4->6:6, 5->6:2) = maks 10
    # Cek aliran masuk 6: 2->6 (2), 4->6 (6 via 1->4:2, 3->4:3, 2->4:1), 5->6 (2 via 3->5:2) = 10?
    # dari 3 ke 4+5 = 3+2 = 5; dari 2 ke 6+4 = 3; dari 1 ke 4 = 2. Total = 2+3+5 = 10 -> cek 2+6+2=10!
    assert metric(r, "Aliran Maksimum") == pytest.approx(10)
