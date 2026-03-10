"""Fiber-reinforced concrete (FRC) slab design.

ACI 360R-10, Chapter 11.

Two design methods:
  1. Elastic method (§11.3.3.2): Uses an allowable flexural stress based
     on the equivalent flexural strength of the steel FRC:
       fb = fr * Re,3 / 100

  2. Yield-line method (§11.3.3.3): Accounts for plastic redistribution
     through yield-line analysis. Valid when Re,3 ≥ 30%.

     Case 1 – Interior (central) load:
       Po = 6 * (1 + 2a/L) * M₀
       M₀ = (1 + Re,3/100) * fr * b * h² / 6

     Case 2 – Edge load:
       Po = 3.5 * (1 + 3a/L) * M₀
       M₀ = (1 + Re,3/100) * fr * b * h² / 6

     Case 3 – Corner load:
       Po = 2 * (1 + 4a/L) * M₀
       M₀ = fr * b * h² / 6

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
    """Allowable flexural stress for steel FRC (elastic method).

    ACI 360R-10 §11.3.3.2:
      fb = fr * Re,3 / 100 / SF

    Args:
        fr:            Modulus of rupture (plain concrete), psi.
        re3:           Residual strength factor Re,3, %.
        safety_factor: Factor of safety.

    Returns:
        Allowable flexural tensile stress, psi.
    """
    return fr * (re3 / 100.0) / safety_factor


def enhancement_factor(re3: float) -> float:
    """Yield-line enhancement factor (1 + Re,3/100)."""
    return 1.0 + re3 / 100.0


# ---------------------------------------------------------------------------
# Yield-line moment capacity
# ---------------------------------------------------------------------------

def unit_moment_capacity(
    fr: float,
    h: float,
    re3: float,
) -> float:
    """Yield-line interior/edge unit moment capacity M₀ per unit slab width, in·lb/in.

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


def corner_unit_moment_capacity(fr: float, h: float) -> float:
    """Yield-line corner unit moment capacity M₀ per unit slab width, in·lb/in."""
    return fr * (h**2 / 6.0)


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

    ACI 360R-10 §11.3.3.3:

      Interior: P₀ = 6 * (1 + 2a/L) * M₀
      Edge:     P₀ = 3.5 * (1 + 3a/L) * M₀
      Corner:   P₀ = 2 * (1 + 4a/L) * M₀

    with:
      Interior/Edge: M₀ = (1 + Re,3/100) * fr * h² / 6
      Corner:        M₀ = fr * h² / 6

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

    if case == YieldLineCase.INTERIOR:
        M0 = unit_moment_capacity(fr, h, re3)
        P0 = 6.0 * (1.0 + (2.0 * a / L)) * M0
    elif case == YieldLineCase.EDGE:
        M0 = unit_moment_capacity(fr, h, re3)
        P0 = 3.5 * (1.0 + (3.0 * a / L)) * M0
    else:  # CORNER
        M0 = corner_unit_moment_capacity(fr, h)
        P0 = 2.0 * (1.0 + (4.0 * a / L)) * M0

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

    validation_status: str
    """Validation basis: equation-based or mixed."""

    model_basis: str
    """Short description of the governing Chapter 11 / Appendix 6 method."""

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

    ACI 360R-10 §11.3.3.2. Uses Westergaard interior formula with
    equivalent flexural strength:
      fb_allowable = fr * Re,3 / 100 / SF

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

    M0 = unit_moment_capacity(concrete.fr, h_req, fibers.re3)

    notes = [
        f"Load: {load_lb:.0f} lb, contact radius: {a:.2f} in",
        f"Re,3 = {fibers.re3:.0f}%",
        f"fb_allowable = {allowable:.1f} psi",
    ]

    return FRCDesignResult(
        method="elastic",
        case="interior",
        validation_status="equation-based",
        model_basis=(
            "ACI 360R-10 Chapter 11 elastic method using Westergaard interior "
            "stress and fb = fr * Re,3 / SF"
        ),
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
    M0 = (
        unit_moment_capacity(concrete.fr, h_in, fibers.re3)
        if case != YieldLineCase.CORNER
        else corner_unit_moment_capacity(concrete.fr, h_in)
    )
    if additional_moment_inlb_per_in > 0:
        # Reduce moment capacity by the locked-in shrinkage moment
        M0_effective = M0 - additional_moment_inlb_per_in
        if M0_effective <= 0:
            P_allowable = 0.0
        else:
            # Recalculate P based on reduced M0
            effective_re3 = fibers.re3 if case != YieldLineCase.CORNER else 0.0
            P_ult_eff = yield_line_capacity(
                concrete.fr * (M0_effective / (concrete.fr * S)),  # effective fr
                h_in,
                effective_re3,
                a,
                L,
                case,
                joint_transfer,
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
        validation_status="equation-based",
        model_basis=(
            "ACI 360R-10 Chapter 11 / Appendix 6 yield-line capacity equations "
            "for interior, edge, and corner loading"
        ),
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
    if case == YieldLineCase.CORNER:
        return 0.0

    # ACI 360R-10 §11.3.3.3 requires Re,3 > 30% for yield-line design.
    lo, hi = 30.0, 200.0

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
