"""Shared fixtures for the slab_designer test suite."""

import pytest

from slab_designer import Concrete, Subgrade


@pytest.fixture
def concrete_4000psi():
    """Standard concrete per ACI Appendix 1 examples: fc=4000 psi, fr=570 psi."""
    return Concrete(fc=4000.0, fr=570.0, E=4_000_000.0, nu=0.15)


@pytest.fixture
def concrete_4000psi_coe():
    """COE method concrete: fc=4000 psi, fr=570 psi, ν=0.20."""
    return Concrete(fc=4000.0, fr=570.0, E=4_000_000.0, nu=0.20)


@pytest.fixture
def subgrade_200pci():
    """Subgrade k=200 pci."""
    return Subgrade(k=200.0)


@pytest.fixture
def subgrade_100pci():
    """Subgrade k=100 pci."""
    return Subgrade(k=100.0)


@pytest.fixture
def subgrade_400pci():
    """Subgrade k=400 pci."""
    return Subgrade(k=400.0)
