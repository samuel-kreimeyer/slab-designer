"""Unit conversion utilities.

Internal calculations use US customary units:
  - Length: inches (in)
  - Force: pounds (lb)
  - Stress/Pressure: pounds per square inch (psi)
  - Subgrade modulus: pounds per cubic inch (pci = lb/in³)
  - Load per unit width: lb/in (= lb·in/in for moment)
  - Moment per unit width: in·lb/in
  - Distributed load: psi (= lb/in²)
  - Unit weight: lb/in³ (convert from lb/ft³ by dividing by 1728)

SI conversions provided as helpers.
"""

from __future__ import annotations

# Length
IN_TO_MM = 25.4
MM_TO_IN = 1.0 / IN_TO_MM
FT_TO_IN = 12.0
IN_TO_FT = 1.0 / FT_TO_IN
M_TO_IN = 39.3701
IN_TO_M = 1.0 / M_TO_IN

# Force
LB_TO_KN = 0.004448222
KN_TO_LB = 1.0 / LB_TO_KN
LB_TO_N = 4.448222
N_TO_LB = 1.0 / LB_TO_N
KIP_TO_LB = 1000.0
LB_TO_KIP = 0.001

# Stress / pressure
PSI_TO_MPA = 0.006894757
MPA_TO_PSI = 1.0 / PSI_TO_MPA
PSI_TO_KPA = 6.894757
KPA_TO_PSI = 1.0 / PSI_TO_KPA

# Subgrade modulus (lb/in³ → kN/m³)
PCI_TO_KNM3 = LB_TO_KN / (IN_TO_M**3)
KNM3_TO_PCI = 1.0 / PCI_TO_KNM3

# Unit weight
PCF_TO_PCI = 1.0 / 1728.0   # lb/ft³ → lb/in³
PCI_TO_PCF = 1728.0

# Moment per unit width
INLB_PER_IN_TO_KNM_PER_M = LB_TO_KN / IN_TO_M  # in·lb/in → kN·m/m

# Convenient constant
CONCRETE_UNIT_WEIGHT_PCF = 150.0  # lb/ft³  (normal weight concrete)
CONCRETE_UNIT_WEIGHT_PCI = CONCRETE_UNIT_WEIGHT_PCF * PCF_TO_PCI


def ft_to_in(value: float) -> float:
    return value * FT_TO_IN


def in_to_ft(value: float) -> float:
    return value * IN_TO_FT


def kip_to_lb(value: float) -> float:
    return value * KIP_TO_LB


def lb_to_kip(value: float) -> float:
    return value * LB_TO_KIP


def mpa_to_psi(value: float) -> float:
    return value * MPA_TO_PSI


def psi_to_mpa(value: float) -> float:
    return value * PSI_TO_MPA


def kn_to_lb(value: float) -> float:
    return value * KN_TO_LB


def mm_to_in(value: float) -> float:
    return value * MM_TO_IN


def in_to_mm(value: float) -> float:
    return value * IN_TO_MM


def pcf_to_pci(value: float) -> float:
    """Convert unit weight from lb/ft³ to lb/in³."""
    return value * PCF_TO_PCI
