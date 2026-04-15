import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyze import normalize_energy


def test_normalize_energy_empty():
    assert normalize_energy([]) == []


def test_normalize_energy_single():
    result = normalize_energy([0.5])
    assert result == [100.0]


def test_normalize_energy_scales_relative_to_max():
    result = normalize_energy([0.5, 0.25, 0.1])
    assert result[0] == 100.0
    assert abs(result[1] - 50.0) < 0.01
    assert abs(result[2] - 20.0) < 0.01


def test_normalize_energy_all_zero():
    result = normalize_energy([0.0, 0.0, 0.0])
    assert result == [0.0, 0.0, 0.0]
