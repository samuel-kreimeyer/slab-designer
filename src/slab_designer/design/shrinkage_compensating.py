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
internal compressive stress.

Appendix 5 provides two explicit Fig. A5.1 lookups for a 6 in. slab:
  - ρ = 0.182%  -> ε_exp = 0.0454% for 0.05% prism expansion
  - ρ = 0.241%  -> ε_exp = 0.0413% for 0.05% prism expansion

This module uses those published values to calibrate a monotone interpolation
table over the normal design range 0.15% to 0.60% reinforcement. Full
compensation and compressive stress checks are then completed with digitized
Fig. 9.3 and Fig. 9.4 interpolation surfaces.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator

from slab_designer.materials import Concrete
from slab_designer.soil import Subgrade

#
# Fig. A5.1 / Fig. 9.3 member-expansion calibration
#
# The two published Appendix 5 lookups are exact anchors. The remaining points
# extend those anchors with a monotone log-rho interpolation over the allowed
# design range 0.15% to 0.60% reinforcement.
#
_FIG_A51_MEMBER_EXPANSION_FACTOR_TABLE: tuple[tuple[float, float], ...] = (
    (0.00150, 0.964471),
    (0.00182, 0.908000),
    (0.00241, 0.826000),
    (0.00300, 0.762049),
    (0.00400, 0.678036),
    (0.00500, 0.612871),
    (0.00600, 0.559627),
)

_FIG_93_RHO_POINTS: tuple[float, ...] = (0.0010, 0.0015, 0.0050, 0.0100, 0.0200)
_FIG_93_VS_POINTS: tuple[float, ...] = (1.5, 3.0, 4.5, 6.0)

# Digitized from the Fig. 9.3 curve/ray intersections.
_FIG_93_REQUIRED_PRISM_EXPANSION_PCT: dict[float, tuple[float, ...]] = {
    1.5: (0.02904, 0.03663, 0.05201, 0.06163, 0.06575),
    3.0: (0.02445, 0.03090, 0.04431, 0.05765, 0.06087),
    4.5: (0.02032, 0.02541, 0.03715, 0.04734, 0.05368),
    6.0: (0.01835, 0.02313, 0.03062, 0.04100, 0.04815),
}

_FIG_93_REQUIRED_MEMBER_EXPANSION_PCT: dict[float, tuple[float, ...]] = {
    1.5: (0.03677, 0.03588, 0.03375, 0.02783, 0.02161),
    3.0: (0.03097, 0.03027, 0.02876, 0.02604, 0.02000),
    4.5: (0.02574, 0.02489, 0.02411, 0.02138, 0.01764),
    6.0: (0.02324, 0.02266, 0.01987, 0.01852, 0.01582),
}

_FIG_94_EXPANSION_PCT_POINTS: tuple[float, ...] = (0.00, 0.02, 0.04, 0.06, 0.08, 0.10)
_FIG_94_RHO_POINTS: tuple[float, ...] = (0.0015, 0.0025, 0.0050, 0.0100)

# Coarse manual digitization of Fig. 9.4 over the practical slab range.
_FIG_94_COMPRESSIVE_STRESS_PSI: dict[float, tuple[float, ...]] = {
    0.0015: (0.0, 8.0, 17.0, 25.0, 33.0, 41.0),
    0.0025: (0.0, 14.0, 27.0, 40.0, 51.0, 62.0),
    0.0050: (0.0, 24.0, 49.0, 73.0, 98.0, 124.0),
    0.0100: (0.0, 46.0, 94.0, 141.0, 150.0, 150.0),
}


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

    validation_status: str
    """Validation basis: digitized."""

    model_basis: str
    """Short description of the governing Appendix 5 / Fig. 9.3 / Fig. 9.4 lookups."""

    rho_ok: bool
    """True if reinforcement ratio is within 0.0015–0.006."""

    prism_ok: bool
    """True if prism expansion ≥ 0.03%."""

    isolation_joint_width_in: float
    """Required isolation joint width at slab perimeter, in.  Eq. (9-1)."""

    slab_expansion_strain: float
    """Estimated slab expansion strain ε_slab from the Fig. A5.1 lookup."""

    required_prism_expansion_pct: float
    """Digitized Fig. 9.3 prism-expansion threshold for full compensation, %."""

    required_member_expansion_strain: float
    """Digitized Fig. 9.3 member-expansion threshold for full compensation."""

    full_compensation_ok: bool
    """True if the estimated slab expansion exceeds the digitized threshold."""

    internal_compressive_stress_psi: float
    """Estimated internal compressive stress from the digitized Fig. 9.4 lookup, psi."""

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
    """Estimate slab expansion strain from the Fig. A5.1 calibrated lookup.

    ACI 360R-10 §9.4.2 states that slab expansion is determined from the known
    prism expansion and the percentage of slab reinforcement. Appendix 5 then
    provides explicit lookup values for ρ = 0.182% and ρ = 0.241% at 0.05%
    prism expansion. This function interpolates the corresponding
    member-expansion factor over the normal design range 0.15% to 0.60%.

    `volume_surface_ratio` is retained for API compatibility. It governs the
    shrinkage-compensation target, not this member-expansion lookup.
    """
    _ = volume_surface_ratio
    epsilon_prism = prism_expansion_pct / 100.0
    return epsilon_prism * _member_expansion_factor(rho)


def _member_expansion_factor(rho: float) -> float:
    """Return the Fig. A5.1 member-expansion factor for a reinforcement ratio.

    The factor is ε_member / ε_prism. Interpolation is linear in log(rho),
    which matches the spacing behavior of the calibrated chart anchors more
    closely than linear interpolation in rho.
    """
    table = _FIG_A51_MEMBER_EXPANSION_FACTOR_TABLE
    if rho <= table[0][0]:
        return table[0][1]
    if rho >= table[-1][0]:
        return table[-1][1]

    for (rho_lo, factor_lo), (rho_hi, factor_hi) in zip(table, table[1:], strict=False):
        if rho_lo <= rho <= rho_hi:
            if rho == rho_lo:
                return factor_lo
            if rho == rho_hi:
                return factor_hi
            t = (math.log(rho) - math.log(rho_lo)) / (math.log(rho_hi) - math.log(rho_lo))
            return factor_lo + t * (factor_hi - factor_lo)

    raise RuntimeError(f"Failed to interpolate member-expansion factor for rho={rho:.6f}")


def _interpolate_fig_93_surface(
    rho: float,
    volume_surface_ratio: float,
    surface: dict[float, tuple[float, ...]],
) -> float:
    """Bilinear interpolation on the digitized Fig. 9.3 threshold surface."""
    rho_points = _FIG_93_RHO_POINTS
    vs_points = _FIG_93_VS_POINTS

    rho = min(max(rho, rho_points[0]), rho_points[-1])
    vs = min(max(volume_surface_ratio, vs_points[0]), vs_points[-1])

    vs_lo = vs_points[0]
    vs_hi = vs_points[-1]
    for lo, hi in zip(vs_points, vs_points[1:], strict=False):
        if lo <= vs <= hi:
            vs_lo = lo
            vs_hi = hi
            break

    def interp_rho(values: tuple[float, ...]) -> float:
        if rho <= rho_points[0]:
            return values[0]
        if rho >= rho_points[-1]:
            return values[-1]
        lower_pairs = tuple(zip(rho_points, values, strict=False))
        upper_pairs = tuple(zip(rho_points[1:], values[1:], strict=False))
        for (rho_lo, value_lo), (rho_hi, value_hi) in zip(
            lower_pairs,
            upper_pairs,
            strict=False,
        ):
            if rho_lo <= rho <= rho_hi:
                if rho == rho_lo:
                    return value_lo
                if rho == rho_hi:
                    return value_hi
                t = (math.log(rho) - math.log(rho_lo)) / (math.log(rho_hi) - math.log(rho_lo))
                return value_lo + t * (value_hi - value_lo)
        raise RuntimeError("Failed to interpolate Fig. 9.3 rho coordinate")

    value_lo = interp_rho(surface[vs_lo])
    value_hi = interp_rho(surface[vs_hi])
    if vs_lo == vs_hi:
        return value_lo

    t_vs = (vs - vs_lo) / (vs_hi - vs_lo)
    return value_lo + t_vs * (value_hi - value_lo)


def _required_prism_expansion_pct(rho: float, volume_surface_ratio: float) -> float:
    """Return the digitized Fig. 9.3 prism-expansion threshold, %."""
    return _interpolate_fig_93_surface(
        rho=rho,
        volume_surface_ratio=volume_surface_ratio,
        surface=_FIG_93_REQUIRED_PRISM_EXPANSION_PCT,
    )


def _required_member_expansion_strain(rho: float, volume_surface_ratio: float) -> float:
    """Return the digitized Fig. 9.3 member-expansion threshold, strain."""
    required_pct = _interpolate_fig_93_surface(
        rho=rho,
        volume_surface_ratio=volume_surface_ratio,
        surface=_FIG_93_REQUIRED_MEMBER_EXPANSION_PCT,
    )
    return required_pct / 100.0


def _estimate_compressive_stress(
    slab_expansion_strain: float,
    rho: float,
    Es: float = 29_000_000.0,
    Ec: float = 4_000_000.0,
) -> float:
    """Estimate internal compressive stress from the digitized Fig. 9.4 table.

    The checked-in table is a coarse manual digitization over the practical
    shrinkage-compensating slab range. `Es` and `Ec` are retained for API
    compatibility but are not used by the chart-based estimate.
    """
    _ = Es, Ec
    expansion_pct = slab_expansion_strain * 100.0
    return _interpolate_fig_94_stress(expansion_pct=expansion_pct, rho=rho)


def _interpolate_fig_94_stress(expansion_pct: float, rho: float) -> float:
    """Bilinear interpolation on the digitized Fig. 9.4 stress surface."""
    expansion_points = _FIG_94_EXPANSION_PCT_POINTS
    rho_points = _FIG_94_RHO_POINTS

    x = min(max(expansion_pct, expansion_points[0]), expansion_points[-1])
    r = min(max(rho, rho_points[0]), rho_points[-1])

    def interp_expansion(values: tuple[float, ...]) -> float:
        if x <= expansion_points[0]:
            return values[0]
        if x >= expansion_points[-1]:
            return values[-1]
        for (x_lo, value_lo), (x_hi, value_hi) in zip(
            zip(expansion_points, values, strict=False),
            zip(expansion_points[1:], values[1:], strict=False),
            strict=False,
        ):
            if x_lo <= x <= x_hi:
                if x == x_lo:
                    return value_lo
                if x == x_hi:
                    return value_hi
                t = (x - x_lo) / (x_hi - x_lo)
                return value_lo + t * (value_hi - value_lo)
        raise RuntimeError("Failed to interpolate Fig. 9.4 expansion coordinate")

    if r <= rho_points[0]:
        return interp_expansion(_FIG_94_COMPRESSIVE_STRESS_PSI[rho_points[0]])
    if r >= rho_points[-1]:
        return interp_expansion(_FIG_94_COMPRESSIVE_STRESS_PSI[rho_points[-1]])

    lower_pairs = tuple(zip(rho_points, strict=False))
    upper_pairs = tuple(zip(rho_points[1:], strict=False))
    for (rho_lo,), (rho_hi,) in zip(lower_pairs, upper_pairs, strict=False):
        if rho_lo <= r <= rho_hi:
            stress_lo = interp_expansion(_FIG_94_COMPRESSIVE_STRESS_PSI[rho_lo])
            stress_hi = interp_expansion(_FIG_94_COMPRESSIVE_STRESS_PSI[rho_hi])
            if r == rho_lo:
                return stress_lo
            if r == rho_hi:
                return stress_hi
            t = (math.log(r) - math.log(rho_lo)) / (math.log(rho_hi) - math.log(rho_lo))
            return stress_lo + t * (stress_hi - stress_lo)

    raise RuntimeError("Failed to interpolate Fig. 9.4 rho coordinate")


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
    required_prism_pct = _required_prism_expansion_pct(rho, design.volume_surface_ratio)
    required_member_eps = _required_member_expansion_strain(rho, design.volume_surface_ratio)
    full_compensation_ok = eps_slab >= required_member_eps

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
        "  (Fig. A5.1 calibrated lookup; Appendix 5 anchors at ρ = 0.182% and 0.241%)",
        f"Digitized full-compensation prism threshold ≈ {required_prism_pct:.4f}%",
        f"Digitized full-compensation member threshold ≈ {required_member_eps:.5f}",
        (
            f"Full shrinkage compensation: {'OK' if full_compensation_ok else 'NG'} "
            f"for V/S = {design.volume_surface_ratio:.2f}"
        ),
        f"Estimated internal compressive stress ≈ {sigma_c:.0f} psi",
        "  (Digitized Fig. 9.4 interpolation table)",
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
        validation_status="digitized",
        model_basis=(
            "Appendix 5 calibrated member-expansion lookup with digitized "
            "ACI 360R-10 Fig. 9.3 and Fig. 9.4 interpolation surfaces"
        ),
        rho_ok=rho_ok,
        prism_ok=prism_ok,
        isolation_joint_width_in=jw,
        slab_expansion_strain=eps_slab,
        required_prism_expansion_pct=required_prism_pct,
        required_member_expansion_strain=required_member_eps,
        full_compensation_ok=full_compensation_ok,
        internal_compressive_stress_psi=sigma_c,
        reinforcement_depth_in=depth_from_top,
        max_bar_spacing_in=max_spacing,
        notes=notes,
    )
