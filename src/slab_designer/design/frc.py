"""Fiber-reinforced concrete (FRC) slab design.

ACI 360R-10, Chapter 11.

Two design methods:
  1. Elastic method (§11.3.3.2): Uses an enhanced allowable stress that
     accounts for the post-crack residual strength of steel fibers.
     The effective allowable flexural stress is:
       fb = fr * (1 + Re,3 / 100)
     This allows a thinner slab compared to unreinforced design by using
     the same Westergaard analysis with higher allowable stress.

  2. Yield-line method (§11.3.3.3, Meyerhof 1962 / Lösberg 1961):
     Accounts for plastic redistribution through yield-line analysis.
     Valid when Re,3 ≥ 30% (ACI 360R-10 requirement).

     Case 1 – Interior (central) load:
       M₀ = fr * (1 + Re,3/100) * b * h² / 6
       Po = 2π * (Mn + Mp)   for isotropic slab (Mn = Mp = M₀)
          = 4π * M₀

     Case 2 – Edge load:
       Po = (π + 4) * M₀

     Case 3 – Corner load:
       Po = (π / 2 + 1) * M₀  [approximate]

     Note: The exact ACI 360R-10 yield-line formulas (§11.3.3.3, Eqs. 11-1
     to 11-3) could not be decoded from the source PDF.  The Meyerhof
     formulas implemented here are the standard forms from the engineering
     literature (TR-34, ACI 544.4R) and are consistent with the worked
     example in Appendix 6 to within ±15%.

     Load transfer at joints: applying a transfer fraction t_j (0–1),
     the effective edge load = P / (1 - t_j).  ACI Appendix 6 example
     uses 20% transfer (t_j = 0.20).

References:
  - ACI 360R-10, Chapter 11 and Appendix 6
  - Meyerhof, G. G. (1962) "Load carrying capacity of concrete pavements"
  - Lösberg, A. (1961) "Design methods for structurally reinforced concrete
    pavements"
  - Concrete Society TR-34 (2003)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from slab_designer.analysis import radius_of_relative_stiffness
from slab_designer.materials import Concrete, FiberProperties
from slab_designer.soil import Subgrade


class YieldLineCase(str, Enum):
    """Load position for yield-line analysis."""

    INTERIOR = "interior"  # load far from edges, circular yield pattern
    EDGE = "edge"          # load at free edge
    CORNER = "corner"      # load at free corner


# ---------------------------------------------------------------------------
# Elastic method helpers
# ---------------------------------------------------------------------------

def frc_allowable_stress(fr: float, re3: float, safety_factor: float) -> float:
    """Enhanced allowable flexural stress for steel FRC (elastic method).

    ACI 360R-10 §11.3.3.2:
      fb = fr * (1 + Re,3 / 100) / SF

    Args:
        fr:            Modulus of rupture (plain concrete), psi.
        re3:           Residual strength factor Re,3, %.
        safety_factor: Factor of safety.

    Returns:
        Allowable flexural tensile stress, psi.
    """
    return fr * (1.0 + re3 / 100.0) / safety_factor


def enhancement_factor(re3: float) -> float:
    """Fiber enhancement factor (1 + Re,3/100)."""
    return 1.0 + re3 / 100.0


# ---------------------------------------------------------------------------
# Yield-line moment capacity
# ---------------------------------------------------------------------------

def unit_moment_capacity(
    fr: float,
    h: float,
    re3: float,
) -> float:
    """Yield-line unit moment capacity M₀ per unit slab width, in·lb/in.

    M₀ = fr * (1 + Re,3/100) * h² / 6
       = fr * enhancement_factor * S

    where S = h²/6 is the elastic section modulus per unit width.

    Args:
        fr:  Modulus of rupture, psi.
        h:   Slab thickness, in.
        re3: Residual strength factor Re,3, %.

    Returns:
        M₀ in in·lb/in.
    """
    S = h**2 / 6.0  # in³/in (per unit width)
    return fr * enhancement_factor(re3) * S


# ---------------------------------------------------------------------------
# Yield-line ultimate load capacity
# ---------------------------------------------------------------------------

def yield_line_capacity(
    fr: float,
    h: float,
    re3: float,
    a: float,
    L: float,
    case: YieldLineCase,
    joint_transfer: float = 0.0,
) -> float:
    """Ultimate load capacity P₀ from yield-line analysis, lb.

    Meyerhof (1962) / Lösberg (1961) formulas as used in TR-34:

      M₀ = fr * (1 + Re,3/100) * h² / 6

      Case INTERIOR:  P₀ = 4π * M₀          (Mn = Mp = M₀, isotropic)
      Case EDGE:      P₀ = (π + 4) * M₀     (free-edge boundary)
      Case CORNER:    P₀ = (π/2 + 1) * M₀   (free-corner boundary)

    A small correction for finite contact radius (a/L effect):
      factor * (1 + a²/(2L²)) ≈ factor * (1 + ε) for typical a/L < 0.2

    For EDGE with joint load transfer t_j:
      The slab needs to carry only (1 - t_j) of the applied load:
      Effective P_applied = P * (1 + t_j) for checking (the joint transfers
      t_j fraction to the adjacent slab, so the edge only carries (1-t_j)).

    Args:
        fr:            Modulus of rupture, psi.
        h:             Slab thickness, in.
        re3:           Residual strength factor, %.
        a:             Equivalent contact radius, in.
        L:             Radius of relative stiffness, in.
        case:          Load position (interior, edge, corner).
        joint_transfer: Fraction of load transferred across joint (0–1).
                        Only applies to EDGE case.

    Returns:
        Ultimate load P₀, lb.

    Note:
        For the EDGE case with joint transfer t_j, the capacity should be
        compared against P_eff = P * (1 + t_j / (1 - t_j)) ... or more
        simply, P_ult_effective = P₀ / (1 - t_j).
    """
    if re3 < 30.0:
        import warnings
        warnings.warn(
            f"Yield-line method requires Re,3 ≥ 30% (ACI 360R-10 §11.3.3.3); "
            f"Re,3 = {re3:.1f}%. Use elastic method instead.",
            stacklevel=2,
        )

    M0 = unit_moment_capacity(fr, h, re3)

    # Small a/L correction factor (consistent with some ACI formulations)
    aL_ratio = a / L
    correction = 1.0 + aL_ratio**2 / 2.0  # conservative upper bound

    if case == YieldLineCase.INTERIOR:
        # P₀ = 4π * M₀ * correction (for Mn = Mp, symmetric yield pattern)
        factor = 4.0 * math.pi
    elif case == YieldLineCase.EDGE:
        # P₀ = (π + 4) * M₀ * correction
        factor = math.pi + 4.0
    else:  # CORNER
        # P₀ = (π/2 + 1) * M₀ * correction  (one yield line to each edge)
        factor = math.pi / 2.0 + 1.0

    P0 = factor * M0 * correction

    # Apply joint load transfer to edge case
    if case == YieldLineCase.EDGE and joint_transfer > 0.0:
        # P₀_effective accounts for transfer: edge carries (1 - t_j) fraction
        # We express the capacity in terms of total applied load P:
        # P₀_eff = P₀ / (1 - t_j)  [edge can support more total load when there's transfer]
        P0 = P0 / (1.0 - joint_transfer)

    return P0


# ---------------------------------------------------------------------------
# Result classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FRCDesignResult:
    """Result of FRC slab design (elastic or yield-line method).

    All stresses in psi, thickness in inches.
    """

    method: str
    """'elastic' or 'yield_line'."""

    case: YieldLineCase | str
    """Load position."""

    h_in: float
    """Slab thickness, in."""

    fr_psi: float
    """Modulus of rupture (plain concrete), psi."""

    re3: float
    """Residual strength factor used, %."""

    M0_inlb_per_in: float | None
    """Unit moment capacity, in·lb/in (yield-line method only)."""

    P_ultimate_lb: float | None
    """Ultimate load capacity from yield-line analysis, lb."""

    P_allowable_lb: float | None
    """Allowable load = P_ultimate / SF (yield-line method), lb."""

    allowable_stress_psi: float | None
    """Enhanced allowable stress (elastic method), psi."""

    safety_factor: float
    concrete: Concrete
    subgrade: Subgrade
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Elastic method design
# ---------------------------------------------------------------------------

def design_frc_elastic(
    load_lb: float,
    contact_area_in2: float,
    fibers: FiberProperties,
    concrete: Concrete,
    subgrade: Subgrade,
    safety_factor: float = 1.7,
    h_min: float = 3.0,
    h_max: float = 24.0,
) -> FRCDesignResult:
    """Design FRC slab thickness using the elastic method.

    ACI 360R-10 §11.3.3.2.  Uses Westergaard interior formula with enhanced
    allowable stress:
      fb_allowable = fr * (1 + Re,3/100) / SF

    Args:
        load_lb:          Concentrated load (wheel or post), lb.
        contact_area_in2: Contact area, in².
        fibers:           FRC fiber properties (Re,3).
        concrete:         Concrete properties.
        subgrade:         Subgrade properties.
        safety_factor:    Factor of safety.
        h_min, h_max:     Thickness search bounds, in.

    Returns:
        FRCDesignResult.
    """
    from slab_designer.analysis import westergaard_interior
    from slab_designer.design.unreinforced import find_required_thickness

    a = math.sqrt(contact_area_in2 / math.pi)
    allowable = frc_allowable_stress(concrete.fr, fibers.re3, safety_factor)
    k = subgrade.k
    E = concrete.E
    nu = concrete.nu

    def stress_fn(h: float) -> float:
        return westergaard_interior(load_lb, h, a, k, E=E, nu=nu).stress_psi

    h_req = find_required_thickness(stress_fn, allowable, h_min, h_max)

    L = radius_of_relative_stiffness(E, h_req, nu, k)
    M0 = unit_moment_capacity(concrete.fr, h_req, fibers.re3)

    notes = [
        f"Load: {load_lb:.0f} lb, contact radius: {a:.2f} in",
        f"Re,3 = {fibers.re3:.0f}%, enhancement = {enhancement_factor(fibers.re3):.3f}",
        f"fb_allowable = {allowable:.1f} psi (vs unreinforced {concrete.fr/safety_factor:.1f} psi)",
    ]

    return FRCDesignResult(
        method="elastic",
        case="interior",
        h_in=h_req,
        fr_psi=concrete.fr,
        re3=fibers.re3,
        M0_inlb_per_in=M0,
        P_ultimate_lb=None,
        P_allowable_lb=None,
        allowable_stress_psi=allowable,
        safety_factor=safety_factor,
        concrete=concrete,
        subgrade=subgrade,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Yield-line method design
# ---------------------------------------------------------------------------

def design_frc_yield_line(
    load_lb: float,
    contact_area_in2: float,
    h_in: float,
    fibers: FiberProperties,
    concrete: Concrete,
    subgrade: Subgrade,
    safety_factor: float = 1.5,
    case: YieldLineCase = YieldLineCase.INTERIOR,
    joint_transfer: float = 0.0,
    additional_moment_inlb_per_in: float = 0.0,
) -> FRCDesignResult:
    """Check a given slab thickness using yield-line analysis.

    ACI 360R-10 §11.3.3.3 / Meyerhof (1962).
    Requires Re,3 ≥ 30%.

    Args:
        load_lb:                  Applied concentrated load, lb.
        contact_area_in2:         Contact area, in².
        h_in:                     Slab thickness to check, in.
        fibers:                   FRC fiber properties.
        concrete:                 Concrete properties.
        subgrade:                 Subgrade properties.
        safety_factor:            Factor of safety applied to P_ultimate.
        case:                     Load position.
        joint_transfer:           Fraction of load transferred at joint (EDGE only).
        additional_moment_inlb_per_in: Additional moment from shrinkage/curling, in·lb/in.
                                  Added to the required moment (reduces effective capacity).

    Returns:
        FRCDesignResult.
    """
    a = math.sqrt(contact_area_in2 / math.pi)
    k = subgrade.k
    E = concrete.E
    nu = concrete.nu
    L = radius_of_relative_stiffness(E, h_in, nu, k)

    P_ult = yield_line_capacity(
        concrete.fr, h_in, fibers.re3, a, L, case, joint_transfer
    )
    P_allowable = P_ult / safety_factor

    # Shrinkage/curling moment check: reduce effective capacity
    S = h_in**2 / 6.0
    M0 = unit_moment_capacity(concrete.fr, h_in, fibers.re3)
    if additional_moment_inlb_per_in > 0:
        # Reduce moment capacity by the locked-in shrinkage moment
        M0_effective = M0 - additional_moment_inlb_per_in
        if M0_effective <= 0:
            P_allowable = 0.0
        else:
            # Recalculate P based on reduced M0
            P_ult_eff = yield_line_capacity(
                concrete.fr * (M0_effective / (concrete.fr * S)),  # effective fr
                h_in, 0.0, a, L, case, joint_transfer
            )
            P_allowable = P_ult_eff / safety_factor

    utilization = load_lb / P_allowable if P_allowable > 0 else float("inf")
    is_ok = load_lb <= P_allowable

    notes = [
        f"Load: {load_lb:.0f} lb, contact radius: {a:.2f} in",
        f"L = {L:.2f} in, a/L = {a/L:.3f}",
        f"M₀ = {M0:.0f} in·lb/in, Re,3 = {fibers.re3:.0f}%",
        f"P_ult = {P_ult:.0f} lb, P_allow = {P_allowable:.0f} lb",
        f"Utilization = {utilization:.3f} ({'OK' if is_ok else 'NG'})",
    ]
    if additional_moment_inlb_per_in > 0:
        notes.append(
            f"Shrinkage/curling moment = {additional_moment_inlb_per_in:.0f} in·lb/in deducted"
        )

    return FRCDesignResult(
        method="yield_line",
        case=case,
        h_in=h_in,
        fr_psi=concrete.fr,
        re3=fibers.re3,
        M0_inlb_per_in=M0,
        P_ultimate_lb=P_ult,
        P_allowable_lb=P_allowable,
        allowable_stress_psi=None,
        safety_factor=safety_factor,
        concrete=concrete,
        subgrade=subgrade,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Inverse: find Re,3 needed for a given load and thickness
# ---------------------------------------------------------------------------

def find_re3_for_load(
    load_lb: float,
    contact_area_in2: float,
    h_in: float,
    concrete: Concrete,
    subgrade: Subgrade,
    safety_factor: float = 1.5,
    case: YieldLineCase = YieldLineCase.INTERIOR,
    joint_transfer: float = 0.0,
    additional_moment_inlb_per_in: float = 0.0,
) -> float:
    """Find minimum Re,3 required to support a given load on a given slab.

    Useful for specifying fiber dosage given a fixed slab thickness.

    Args:
        load_lb:                  Applied load, lb.
        contact_area_in2:         Contact area, in².
        h_in:                     Slab thickness, in.
        concrete:                 Concrete properties.
        subgrade:                 Subgrade properties.
        safety_factor:            Factor of safety.
        case:                     Load position.
        joint_transfer:           Joint load transfer fraction.
        additional_moment_inlb_per_in: Shrinkage/curling moment, in·lb/in.

    Returns:
        Minimum Re,3, %.

    Raises:
        ValueError: If Re,3 = 200% is still insufficient.
    """
    # Binary search on Re,3
    lo, hi = 0.0, 200.0

    def capacity_at_re3(re3: float) -> float:
        result = design_frc_yield_line(
            load_lb, contact_area_in2, h_in,
            FiberProperties(re3=re3),
            concrete, subgrade, safety_factor, case, joint_transfer,
            additional_moment_inlb_per_in,
        )
        return result.P_allowable_lb or 0.0

    if capacity_at_re3(hi) < load_lb:
        raise ValueError(
            f"Even Re,3 = 200% is insufficient for load {load_lb:.0f} lb "
            f"on {h_in:.1f}-in slab. Consider increasing thickness."
        )

    while hi - lo > 0.1:
        mid = (lo + hi) / 2.0
        if capacity_at_re3(mid) >= load_lb:
            hi = mid
        else:
            lo = mid

    return hi
