"""Soil / subgrade models.

The modulus of subgrade reaction k (pci = lb/in³) is the primary soil parameter
used in Westergaard analysis.  ACI 360R-10, Chapter 4 discusses soil support
systems and guidance on selecting k.

Typical values (from ACI 360R-10 Table 4.1 and commentary):
  - Very poor soils (SP, SM): k ≈ 25–50 pci
  - Poor soils (ML, CL):      k ≈ 50–100 pci
  - Medium soils (SM-SC):     k ≈ 100–200 pci
  - Good soils (GW, GP):      k ≈ 200–400 pci
  - Excellent soils / rock:   k ≈ 400+ pci

Subbase effect: a granular subbase increases the effective k.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SubgradeClass(str, Enum):
    """Qualitative soil classification for rough k estimation."""

    VERY_POOR = "very_poor"    # k ~ 25–50 pci
    POOR = "poor"              # k ~ 50–100 pci
    MEDIUM = "medium"          # k ~ 100–200 pci
    GOOD = "good"              # k ~ 200–400 pci
    EXCELLENT = "excellent"    # k ~ 400+ pci


_K_TYPICAL: dict[SubgradeClass, float] = {
    SubgradeClass.VERY_POOR: 37.5,
    SubgradeClass.POOR: 75.0,
    SubgradeClass.MEDIUM: 150.0,
    SubgradeClass.GOOD: 300.0,
    SubgradeClass.EXCELLENT: 500.0,
}


class SlipSheet(str, Enum):
    """Slip membrane type between slab and subgrade.

    Affects coefficient of friction used in post-tensioning and
    shrinkage-compensating concrete designs.  (ACI 360R-10 §9.3.1 and §10.3.2)
    """

    NONE = "none"                    # mu ≈ 0.75–1.00 (sand base)
    ONE_POLY = "one_poly"            # mu ≈ 0.50–0.75
    TWO_POLY = "two_poly"            # mu ≈ 0.30 (recommended for PT/SC slabs)


_MU_TYPICAL: dict[SlipSheet, float] = {
    SlipSheet.NONE: 0.875,     # midpoint of 0.75–1.00
    SlipSheet.ONE_POLY: 0.625,  # midpoint of 0.50–0.75
    SlipSheet.TWO_POLY: 0.30,
}


class Subgrade(BaseModel, frozen=True):
    """Subgrade (soil support) properties.

    Args:
        k: Modulus of subgrade reaction, lb/in³ (pci).
        slip_sheet: Slip membrane type (affects friction coefficient).
        mu: Override friction coefficient.  If None, derived from slip_sheet.
    """

    k: float = Field(gt=0, description="Modulus of subgrade reaction, lb/in³ (pci)")
    slip_sheet: SlipSheet = Field(
        default=SlipSheet.NONE,
        description="Slip membrane type between slab and subgrade",
    )
    mu: float | None = Field(
        default=None,
        ge=0,
        le=3.0,
        description="Friction coefficient (override).  If None, typical value from slip_sheet used.",
    )

    @property
    def friction_coefficient(self) -> float:
        """Coefficient of friction µ between slab and subgrade."""
        if self.mu is not None:
            return self.mu
        return _MU_TYPICAL[self.slip_sheet]

    @classmethod
    def from_class(
        cls,
        soil_class: SubgradeClass,
        slip_sheet: SlipSheet = SlipSheet.NONE,
    ) -> "Subgrade":
        """Create subgrade from qualitative soil classification."""
        return cls(k=_K_TYPICAL[soil_class], slip_sheet=slip_sheet)

    @classmethod
    def from_si(
        cls,
        k_knm3: float,
        slip_sheet: SlipSheet = SlipSheet.NONE,
    ) -> "Subgrade":
        """Create from SI unit (kN/m³)."""
        from slab_designer.units import KNM3_TO_PCI

        return cls(k=k_knm3 * KNM3_TO_PCI, slip_sheet=slip_sheet)
