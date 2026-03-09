"""Shrinkage-compensating concrete slab design.

ACI 360R-10, Chapter 9 and ACI 223.

Design considerations:
  1. Slab thickness: determined same as unreinforced (PCA/WRI/COE methods).
  2. Reinforcement:
       - Minimum ratio ρ = 0.0015 (each direction)  [§9.3.2]
       - Maximum ratio ρ ≤ 0.006 for full compensation [§9.3.4]
       - Position: 1/3 of slab depth from top        [§9.3.3]
  3. Prism expansion: minimum 0.03% per ASTM C878    [§9.3, §9.4.2]
  4. Isolation joint width (Eq. 9-1):
       joint_width = 2 × L_slab × 12 × ε_expansion   [§9.4.3]
       (for one-end expansion; halve for two-end expansion)
  5. Subgrade friction: use two sheets of polyethylene (µ = 0.30)
     to allow free expansion.

Figures 9.3 and 9.4 from ACI 360R-10 provide graphical relationships
between prism expansion, reinforcement ratio, and slab expansion strain /
internal compressive stress.  These cannot be digitised from the source PDF,
so this module implements the analytical approach from ACI 223 where possible
and notes where chart lookup is required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator

from slab_designer.materials import Concrete
from slab_designer.soil import Subgrade


class ShrinkageCompensatingDesign(BaseModel, frozen=True):
    """Input parameters for shrinkage-compensating concrete slab.

    Args:
        slab_thickness_in:   Slab thickness, in (from PCA/WRI/COE design).
        slab_length_ft:      Slab length (longest dimension), ft.
        slab_width_ft:       Slab width, ft.
        prism_expansion_pct: ASTM C878 restrained prism expansion, %.
                             Minimum recommended: 0.03%.
        rho:                 Reinforcement ratio (As/Ag) in each direction.
                             Range: 0.0015–0.006.
        volume_surface_ratio: Volume-to-surface ratio, in.
                              For 6-in. slab drying from top: V/S = 6.
        fy_psi:              Reinforcement yield strength, psi.
        concrete:            Concrete properties.
        subgrade:            Subgrade properties.
        expansion_at_one_end: True if slab can only expand at one end.
    """

    slab_thickness_in: float = Field(gt=0, description="Slab thickness, in")
    slab_length_ft: float = Field(gt=0, description="Slab length, ft")
    slab_width_ft: float = Field(gt=0, description="Slab width, ft")
    prism_expansion_pct: float = Field(
        ge=0.03,
        description="ASTM C878 restrained prism expansion, %. Min 0.03%.",
    )
    rho: float = Field(
        ge=0.0015,
        le=0.006,
        description="Reinforcement ratio (each direction), 0.0015–0.006",
    )
    volume_surface_ratio: float = Field(
        default=6.0,
        gt=0,
        description=(
            "Volume/surface ratio, in. "
            "= h for single-surface (top-only) drying. "
            "For a 6-in. slab: V/S = 6."
        ),
    )
    fy_psi: float = Field(default=60_000.0, gt=0, description="Steel yield strength, psi")
    concrete: Concrete
    subgrade: Subgrade
    expansion_at_one_end: bool = Field(
        default=True,
        description="True if slab can expand at only one end (conservative)",
    )

    @field_validator("prism_expansion_pct")
    @classmethod
    def check_min_prism(cls, v: float) -> float:
        if v < 0.03:
            raise ValueError(
                f"Prism expansion {v:.3f}% < 0.03% minimum per ACI 360R-10 §9.3."
            )
        return v

    @property
    def reinforcement_ok(self) -> bool:
        """True if 0.0015 ≤ ρ ≤ 0.006."""
        return 0.0015 <= self.rho <= 0.006


@dataclass(frozen=True)
class ShrinkageCompensatingResult:
    """Result of shrinkage-compensating concrete slab design.

    Based on ACI 360R-10 §9.3–§9.4 and ACI 223.
    """

    design: ShrinkageCompensatingDesign

    rho_ok: bool
    """True if reinforcement ratio is within 0.0015–0.006."""

    prism_ok: bool
    """True if prism expansion ≥ 0.03%."""

    isolation_joint_width_in: float
    """Required isolation joint width at slab perimeter, in.  Eq. (9-1)."""

    slab_expansion_strain: float
    """Estimated slab expansion strain ε_slab (from Fig. 9.3 simplified).

    This is a simplified estimate:
      ε_slab ≈ prism_expansion_pct / 100 × reduction_factor(ρ, V/S)

    The exact value requires Fig. 9.3 chart lookup in ACI 360R-10.
    Use this as a first approximation; verify with ACI 223 charts.
    """

    internal_compressive_stress_psi: float
    """Estimated internal compressive stress from expansion, psi.

    Simplified estimate: σ = ε_slab × E_s × ρ / (1 + n*ρ)
    The exact value requires Fig. 9.4 chart lookup in ACI 360R-10.
    """

    reinforcement_depth_in: float
    """Recommended steel depth from top = h/3, in.  (ACI 360R-10 §9.3.3)."""

    max_bar_spacing_in: float
    """Maximum bar spacing = min(3h, 14 in) for smooth wire per §9.3.5."""

    notes: list[str] = field(default_factory=list)


def _estimate_slab_expansion_strain(
    prism_expansion_pct: float,
    rho: float,
    volume_surface_ratio: float,
) -> float:
    """Simplified estimate of restrained slab expansion strain.

    This approximates the ACI 360R-10 Fig. 9.3 relationship.
    The actual design requires chart lookup.

    Based on the relationship between prism expansion and slab expansion:
      ε_slab ≈ ε_prism × C_vs × C_rho

    where:
      C_vs  = volume-surface correction (smaller V/S → more drying → less expansion)
      C_rho = reinforcement stiffness reduction

    Simplified linear approximation (NOT a substitute for Fig. 9.3):
      ε_slab ≈ ε_prism × (1 - rho / 0.012) × (1 - (V/S - 6) * 0.02)

    This is approximate. For design, use ACI 223 Fig. 9.3.
    """
    epsilon_prism = prism_expansion_pct / 100.0
    # Reduction due to reinforcement restraint (higher rho → less slab expansion)
    rho_factor = max(0.1, 1.0 - rho / 0.012)
    # Small V/S correction (thinner slabs lose expansion faster)
    vs_factor = max(0.5, 1.0 - (volume_surface_ratio - 6.0) * 0.02)
    return epsilon_prism * rho_factor * vs_factor


def _estimate_compressive_stress(
    slab_expansion_strain: float,
    rho: float,
    Es: float = 29_000_000.0,
    Ec: float = 4_000_000.0,
) -> float:
    """Simplified estimate of internal compressive stress, psi.

    Based on compatibility: concrete compressive stress from restrained expansion.
    σ_c = ε_slab × ρ × Es / (1 + n × ρ)
    where n = Es / Ec (modular ratio).

    This is a simplified estimate. Use ACI 360R-10 Fig. 9.4 for design.
    """
    n = Es / Ec
    sigma = slab_expansion_strain * rho * Es / (1.0 + n * rho)
    return sigma


def isolation_joint_width(
    slab_length_ft: float,
    expansion_strain: float,
    expansion_at_one_end: bool = True,
) -> float:
    """Required isolation joint width, in.

    ACI 360R-10 Eq. (9-1) / §9.4.3:
      joint_width = 2 × L × 12 × ε_expansion  (one-end expansion)
      joint_width = 1 × L × 12 × ε_expansion  (two-end expansion)

    where L is in ft and ε_expansion is the dimensionless slab expansion strain.

    Example (ACI 360R-10 §9.4.3):
      L = 120 ft, ε = 0.00035
      joint_width = 2 × 120 × 12 × 0.00035 = 1.008 in → use 1 in.

    Args:
        slab_length_ft:      Length of slab in direction of expansion, ft.
        expansion_strain:    Slab expansion strain ε (dimensionless).
        expansion_at_one_end: True if expansion occurs at one end only.

    Returns:
        Required joint width, in.
    """
    multiplier = 2.0 if expansion_at_one_end else 1.0
    return multiplier * slab_length_ft * 12.0 * expansion_strain


def design_shrinkage_compensating(
    design: ShrinkageCompensatingDesign,
) -> ShrinkageCompensatingResult:
    """Shrinkage-compensating concrete slab design checks.

    ACI 360R-10, Chapter 9 / ACI 223.

    Note: Slab thickness is determined separately using PCA/WRI/COE methods
    (Chapter 7).  This function checks reinforcement, expansion, and joint
    width for the shrinkage-compensating system.

    Args:
        design: ShrinkageCompensatingDesign input parameters.

    Returns:
        ShrinkageCompensatingResult with design checks and recommendations.
    """
    h = design.slab_thickness_in
    rho = design.rho
    L_ft = design.slab_length_ft
    prism = design.prism_expansion_pct

    # Reinforcement checks
    rho_ok = design.reinforcement_ok
    prism_ok = prism >= 0.03

    # Estimate expansion strain
    eps_slab = _estimate_slab_expansion_strain(
        prism, rho, design.volume_surface_ratio
    )

    # Estimate compressive stress
    sigma_c = _estimate_compressive_stress(
        eps_slab, rho, Es=29_000_000.0, Ec=design.concrete.E
    )

    # Isolation joint width
    jw = isolation_joint_width(L_ft, eps_slab, design.expansion_at_one_end)

    # Reinforcement placement per §9.3.3
    depth_from_top = h / 3.0

    # Maximum bar/wire spacing per §9.3.5
    max_spacing = min(3.0 * h, 14.0)

    notes = [
        f"Slab: {L_ft:.0f} ft × {design.slab_width_ft:.0f} ft × {h:.0f} in thick",
        (
            f"Prism expansion: {prism:.3f}% "
            f"({'OK' if prism_ok else 'NG - increase cement content/mix'})"
        ),
        (
            f"Reinforcement ratio ρ = {rho:.4f} "
            f"({'OK' if rho_ok else 'NG - check 0.0015–0.006 range'})"
        ),
        f"Estimated slab expansion strain: ε_slab ≈ {eps_slab:.5f}",
        "  (Approximate – verify with ACI 360R-10 Fig. 9.3 chart lookup)",
        f"Estimated internal compressive stress ≈ {sigma_c:.0f} psi",
        "  (Approximate – verify with ACI 360R-10 Fig. 9.4 chart lookup)",
        f"Isolation joint width = {jw:.3f} in "
        f"({'one end' if design.expansion_at_one_end else 'two ends'} expansion)",
        f"  Use {math.ceil(jw * 4) / 4:.2f} in (rounded up to nearest 1/4 in)",
        f"Steel location: {depth_from_top:.2f} in from top (= h/3 per §9.3.3)",
        f"Maximum bar/wire spacing: {max_spacing:.1f} in",
        "Minimum 0.15% steel (without trial batch data) per ACI SP-64",
        "Two polyethylene sheets recommended (µ = 0.30) per §9.3.1",
        "Allow 70% of max lab expansion before placing adjacent slab (§9.4.5)",
    ]

    return ShrinkageCompensatingResult(
        design=design,
        rho_ok=rho_ok,
        prism_ok=prism_ok,
        isolation_joint_width_in=jw,
        slab_expansion_strain=eps_slab,
        internal_compressive_stress_psi=sigma_c,
        reinforcement_depth_in=depth_from_top,
        max_bar_spacing_in=max_spacing,
        notes=notes,
    )
