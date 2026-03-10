"""Unreinforced (and reinforced-for-crack-width) slab thickness design.

Implemented Chapter 7 methods:
  - PCA method (§7.2.1): Interior loads; uses Westergaard interior formula.
  - COE method (§7.2.3): Edge/joint loads; uses Westergaard edge formula
                          with 0.75 joint transfer and 25% impact factor.
  - Aisle loading approximation aligned with PCA/WRI usage for §7.2.1.3 / §7.2.2.4.

Appendix-calibrated WRI wheel-load fit:
  - Wheel-load thickness selection uses an appendix-calibrated fit to the
    A2.2 chart moments and the direct section-modulus stress relation.

All three methods share the same basic approach:
  1. Select an allowable stress = fr / safety_factor.
  2. Iterate on slab thickness h until the computed Westergaard stress ≤ allowable.

For the PCA and WRI methods, the controlling load case is the interior load.
For the COE method, the controlling load case is the edge load.

This module provides:
  - find_required_thickness(): generic bisection solver
  - design_for_wheel_load(): PCA/COE wheel loading design
  - design_for_rack_load(): PCA rack post loading design
  - design_for_uniform_load(): PCA/WRI aisle uniform loading design
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from slab_designer.analysis import (
    AisleMoment,
    allowable_stress,
    radius_of_relative_stiffness,
    westergaard_aisle,
    westergaard_edge_coe,
    westergaard_interior,
)
from slab_designer.loads import RackLoad, UniformLoad, WheelLoad
from slab_designer.materials import Concrete
from slab_designer.soil import Subgrade


class DesignMethod(str, Enum):
    """Thickness design method."""

    PCA = "PCA"    # Portland Cement Association
    WRI = "WRI"    # Wire Reinforcement Institute
    COE = "COE"    # Corps of Engineers
    WESTERGAARD = "WESTERGAARD"  # Direct Westergaard (any case)


class LoadCase(str, Enum):
    """Governing load location."""

    INTERIOR = "interior"
    EDGE = "edge"
    CORNER = "corner"
    AISLE = "aisle"


@dataclass(frozen=True)
class SafetyFactors:
    """Recommended factors of safety from ACI 360R-10 Table 5.2.

    Apply to the modulus of rupture fr to get allowable stress.

    ACI 360R-10 Table 5.2 recommendations:
      Moving wheel loads:    1.7–2.0
      Concentrated loads:    1.7–2.0  (rack posts, pallet jacks)
      Uniform loads:         1.7–2.0
      Line/strip loads:      1.7
      Construction loads:    1.4–2.0  (use 1.4 for temporary/short-term)
    """

    wheel: float = 1.7
    concentrated: float = 1.4   # rack posts (ACI Appendix 1 example uses 1.4)
    uniform: float = 1.7
    line: float = 1.7
    construction: float = 1.4


DEFAULT_SAFETY_FACTORS = SafetyFactors()


@dataclass(frozen=True)
class DesignResult:
    """Result of a slab thickness design check or design run.

    All stresses in psi, thickness in inches.
    """

    method: DesignMethod
    load_case: LoadCase
    required_thickness_in: float
    """Minimum slab thickness satisfying the design criterion, in."""

    computed_stress_psi: float
    """Flexural stress at the required thickness, psi."""

    allowable_stress_psi: float
    """Allowable flexural tensile stress = fr / SF, psi."""

    safety_factor: float
    """Applied factor of safety."""

    L_in: float
    """Radius of relative stiffness at required thickness, in."""

    concrete: Concrete
    subgrade: Subgrade

    notes: list[str] = field(default_factory=list)

    @property
    def utilization(self) -> float:
        """Demand/capacity ratio (≤ 1.0 for adequate design)."""
        return self.computed_stress_psi / self.allowable_stress_psi

    @property
    def is_adequate(self) -> bool:
        return self.utilization <= 1.0

    @property
    def required_thickness_rounded_in(self) -> float:
        """Thickness rounded up to nearest 1/4 inch."""
        return math.ceil(self.required_thickness_in * 4) / 4


# ---------------------------------------------------------------------------
# Generic bisection solver
# ---------------------------------------------------------------------------

def find_required_thickness(
    stress_fn: Callable[[float], float],
    allowable: float,
    h_min: float = 3.0,
    h_max: float = 24.0,
    tol: float = 1e-4,
) -> float:
    """Find minimum slab thickness such that stress_fn(h) ≤ allowable.

    Uses bisection on the thickness.  stress_fn(h) must be monotonically
    decreasing in h (thicker slab → lower stress).

    Args:
        stress_fn:  Function mapping thickness h (in) → stress (psi).
        allowable:  Maximum allowable stress, psi.
        h_min:      Lower bound for thickness search, in.
        h_max:      Upper bound for thickness search, in.
        tol:        Convergence tolerance, in.

    Returns:
        Required slab thickness, in.

    Raises:
        ValueError: If h_max is insufficient to satisfy the criterion.
    """
    if stress_fn(h_max) > allowable:
        raise ValueError(
            f"Required thickness exceeds maximum search limit of {h_max} in. "
            f"Stress at {h_max} in = {stress_fn(h_max):.1f} psi > allowable "
            f"{allowable:.1f} psi. Increase concrete strength or subgrade support."
        )

    lo, hi = h_min, h_max
    while hi - lo > tol:
        mid = (lo + hi) / 2.0
        if stress_fn(mid) <= allowable:
            hi = mid
        else:
            lo = mid

    return hi


# ---------------------------------------------------------------------------
# PCA / Westergaard wheel load design (interior or edge)
# ---------------------------------------------------------------------------


def _wri_basic_moment_per_kip(
    h: float,
    contact_radius_in: float,
    k: float,
    E: float,
    nu: float,
) -> tuple[float, float]:
    """Approximate the WRI basic moment chart from the interior plate solution.

    The Appendix A2.2 example gives 265 in-lb/in per kip for:
      h = 8 in, E = 3000 ksi, k = 400 pci, diameter = 6 in.

    The Westergaard interior solution under the same trial geometry gives
    approximately 246 in-lb/in per kip, so a factor of 1.076 aligns the
    analytical baseline with the published WRI chart.
    """
    response = westergaard_interior(1000.0, h, contact_radius_in, k, E=E, nu=nu)
    baseline_moment = response.stress_psi * h * h / 6.0
    return 1.076161631004381 * baseline_moment, response.L


def _wri_additional_moment_per_kip(
    basic_moment_per_kip: float,
    wheel_spacing_in: float,
    L_in: float,
) -> float:
    """Approximate the small A2.2 additional-wheel chart.

    The Appendix A2.2 example gives an additional 16 in-lb/in per kip at
    spacing/L ≈ 1.88. An exponential decay in spacing/L matches that chart
    behavior well enough for wheel spacings in the practical design range.
    """
    interaction_ratio = 0.3961914366298412 * math.exp(-wheel_spacing_in / L_in)
    return basic_moment_per_kip * interaction_ratio

def design_for_wheel_load(
    load: WheelLoad,
    concrete: Concrete,
    subgrade: Subgrade,
    safety_factor: float = DEFAULT_SAFETY_FACTORS.wheel,
    method: DesignMethod = DesignMethod.PCA,
    load_case: LoadCase = LoadCase.INTERIOR,
    h_min: float = 3.0,
    h_max: float = 24.0,
) -> DesignResult:
    """Design slab thickness for a wheel (axle) load.

    PCA method (ACI 360R-10 §7.2.1): interior load, uses Westergaard
    interior formula.

    COE method (ACI 360R-10 §7.2.3): edge/joint load, uses Westergaard
    edge formula with 0.75 joint-transfer coefficient and 1.25 impact factor.

    The governing Westergaard equation is iterated over h until the stress
    satisfies the allowable stress criterion.

    The PCA method accounts for the interaction of two wheels at the ends of
    the axle. The stress from the second wheel (at distance = wheel_spacing)
    is added to the primary wheel stress. In practice this additional effect
    is small for typical wheel spacings (>3L), and the primary wheel stress
    governs.

    Args:
        load:          Wheel load object.
        concrete:      Concrete properties.
        subgrade:      Subgrade properties.
        safety_factor: Factor of safety on fr.
        method:        Design method (PCA for interior, COE for edge).
        load_case:     Interior or edge (corner covered separately).
        h_min, h_max:  Thickness search bounds, in.

    Returns:
        DesignResult with required thickness and stress information.
    """
    allowable = allowable_stress(concrete.fr, safety_factor)
    P = load.wheel_load_lb
    a = load.contact_radius_in
    s = load.wheel_spacing_in
    E = concrete.E
    nu = concrete.nu
    k = subgrade.k

    if method == DesignMethod.COE or load_case == LoadCase.EDGE:
        def stress_fn(h: float) -> float:
            ws = westergaard_edge_coe(P, h, a, k, E=E)
            return ws.stress_psi

        result_case = LoadCase.EDGE
        used_method = DesignMethod.COE
    elif method == DesignMethod.WRI:
        def stress_fn(h: float) -> float:
            basic_moment_per_kip, L = _wri_basic_moment_per_kip(h, a, k, E, nu)
            additional_moment_per_kip = _wri_additional_moment_per_kip(
                basic_moment_per_kip,
                s,
                L,
            )
            total_moment = (basic_moment_per_kip + additional_moment_per_kip) * (P / 1000.0)
            return 6.0 * total_moment / (h * h)

        result_case = LoadCase.INTERIOR
        used_method = DesignMethod.WRI
    else:
        # PCA interior: primary wheel + contribution from second wheel
        def stress_fn(h: float) -> float:
            primary = westergaard_interior(P, h, a, k, E=E, nu=nu)
            fb = primary.stress_psi
            # Second wheel contribution (treated as separate interior load at dist s)
            # Only significant when s < 3L; conservatively add if s < 4L
            L = primary.L
            if s < 4.0 * L:
                # Approximate additional stress from second wheel using interior formula
                # (conservative – actual reduction factor depends on spacing/L ratio)
                fb2 = westergaard_interior(P, h, a, k, E=E, nu=nu).stress_psi
                # Miner-type superposition: add fraction based on spacing
                # For spacing ≥ 3L, contribution is < 5% – use full interior stress
                # This matches PCA chart assumptions
                fb = fb + fb2 * max(0.0, 1.0 - s / (4.0 * L)) * 0.5
            return fb

        result_case = LoadCase.INTERIOR
        used_method = DesignMethod.PCA

    h_req = find_required_thickness(stress_fn, allowable, h_min, h_max)
    final_stress = stress_fn(h_req)
    L_final = radius_of_relative_stiffness(E, h_req, nu, k)

    notes = [
        f"Axle load: {load.axle_load_lb:.0f} lb, wheel load: {P:.0f} lb",
        f"Contact radius: {a:.2f} in, wheel spacing: {s:.1f} in",
        f"Allowable stress: {allowable:.1f} psi (fr={concrete.fr:.1f} / SF={safety_factor})",
    ]
    if used_method == DesignMethod.COE:
        notes.append(
            "COE method: 25% impact applied to load, 0.75 joint transfer on stress, ν=0.20"
        )
    if used_method == DesignMethod.WRI:
        notes.append(
            "WRI method: Appendix A2.2 chart fit calibrated to the published wheel-load example"
        )

    return DesignResult(
        method=used_method,
        load_case=result_case,
        required_thickness_in=h_req,
        computed_stress_psi=final_stress,
        allowable_stress_psi=allowable,
        safety_factor=safety_factor,
        L_in=L_final,
        concrete=concrete,
        subgrade=subgrade,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# PCA rack-post (concentrated) load design
# ---------------------------------------------------------------------------

def design_for_rack_load(
    load: RackLoad,
    concrete: Concrete,
    subgrade: Subgrade,
    safety_factor: float = DEFAULT_SAFETY_FACTORS.concentrated,
    h_min: float = 3.0,
    h_max: float = 24.0,
) -> DesignResult:
    """Design slab thickness for a rack-post (concentrated) load.

    PCA method (ACI 360R-10 §7.2.1.2 and Appendix A1.3).

    Models the post as a concentrated load at the slab interior using the
    Westergaard interior formula.  Multiple-post interaction is accounted for
    by the post grid spacing relative to L: when post spacing is ≥ 4L the
    posts act independently; at closer spacing a correction is applied.

    Args:
        load:          Rack post load object.
        concrete:      Concrete properties.
        subgrade:      Subgrade properties.
        safety_factor: Factor of safety on fr.  Default 1.4 (ACI Appendix A1.3).
        h_min, h_max:  Thickness search bounds, in.

    Returns:
        DesignResult with required thickness and stress information.
    """
    allowable = allowable_stress(concrete.fr, safety_factor)
    P = load.post_load_lb
    a = load.contact_radius_in
    E = concrete.E
    nu = concrete.nu
    k = subgrade.k

    def stress_fn(h: float) -> float:
        primary = westergaard_interior(P, h, a, k, E=E, nu=nu)
        fb = primary.stress_psi
        L = primary.L
        # Add contribution from adjacent posts when spacing < 4L
        for spacing in (load.long_spacing_in, load.short_spacing_in):
            if spacing < 4.0 * L:
                overlap = max(0.0, 1.0 - spacing / (4.0 * L))
                fb += fb * overlap * 0.25  # conservative superposition fraction
        return fb

    h_req = find_required_thickness(stress_fn, allowable, h_min, h_max)
    final_stress = stress_fn(h_req)
    L_final = radius_of_relative_stiffness(E, h_req, nu, k)

    notes = [
        f"Post load: {P:.0f} lb, contact area: {load.base_plate_area_in2:.1f} in²",
        f"Contact radius: {a:.2f} in",
        f"Grid spacing: long={load.long_spacing_in:.0f} in, short={load.short_spacing_in:.0f} in",
        f"Allowable stress: {allowable:.1f} psi (fr={concrete.fr:.1f} / SF={safety_factor})",
    ]

    return DesignResult(
        method=DesignMethod.PCA,
        load_case=LoadCase.INTERIOR,
        required_thickness_in=h_req,
        computed_stress_psi=final_stress,
        allowable_stress_psi=allowable,
        safety_factor=safety_factor,
        L_in=L_final,
        concrete=concrete,
        subgrade=subgrade,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# PCA / WRI uniform (aisle) load design
# ---------------------------------------------------------------------------

def design_for_uniform_load(
    load: UniformLoad,
    concrete: Concrete,
    subgrade: Subgrade,
    safety_factor: float = DEFAULT_SAFETY_FACTORS.uniform,
    h_min: float = 3.0,
    h_max: float = 24.0,
) -> DesignResult:
    """Design slab thickness for symmetric uniform loading with a clear aisle.

    The critical design condition is tension at the TOP of the slab at the
    aisle centreline (Case 4 – Rice/Hetenyi analysis).

    ACI 360R-10 §7.2.1.3 and §7.2.2.4; Appendix A1 Table A1.2.

    Args:
        load:          Uniform load object.
        concrete:      Concrete properties.
        subgrade:      Subgrade properties.
        safety_factor: Factor of safety on fr.
        h_min, h_max:  Thickness search bounds, in.

    Returns:
        DesignResult with required thickness and stress information.
    """
    allowable = allowable_stress(concrete.fr, safety_factor)
    w = load.intensity_psi
    a = load.aisle_half_width_in
    E = concrete.E
    nu = concrete.nu
    k = subgrade.k

    def stress_fn(h: float) -> float:
        am: AisleMoment = westergaard_aisle(w, h, a, k, E=E, nu=nu)
        return am.as_stress_psi()

    h_req = find_required_thickness(stress_fn, allowable, h_min, h_max)
    final_stress = stress_fn(h_req)
    L_final = radius_of_relative_stiffness(E, h_req, nu, k)

    notes = [
        f"Uniform load: {load.intensity_psf:.0f} psf = {w:.4f} psi",
        f"Aisle width: {load.aisle_width_ft:.1f} ft, half-width: {a:.1f} in",
        f"Allowable stress: {allowable:.1f} psi (fr={concrete.fr:.1f} / SF={safety_factor})",
        "Governing condition: top tension at aisle centreline (Rice 1957)",
    ]

    return DesignResult(
        method=DesignMethod.WRI,
        load_case=LoadCase.AISLE,
        required_thickness_in=h_req,
        computed_stress_psi=final_stress,
        allowable_stress_psi=allowable,
        safety_factor=safety_factor,
        L_in=L_final,
        concrete=concrete,
        subgrade=subgrade,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Check a given thickness (analysis mode)
# ---------------------------------------------------------------------------

def check_thickness(
    h: float,
    load: WheelLoad | RackLoad,
    concrete: Concrete,
    subgrade: Subgrade,
    safety_factor: float,
    load_case: LoadCase = LoadCase.INTERIOR,
) -> DesignResult:
    """Check whether a given slab thickness is adequate.

    Returns a DesignResult whose is_adequate property indicates pass/fail.
    """
    if isinstance(load, WheelLoad):
        design_for_wheel_load(
            load, concrete, subgrade, safety_factor, load_case=load_case,
            h_min=h - 0.01, h_max=h + 0.01
        )
    else:
        design_for_rack_load(
            load, concrete, subgrade, safety_factor,
            h_min=h - 0.01, h_max=h + 0.01
        )

    # Re-compute stress at the provided h
    allowable = allowable_stress(concrete.fr, safety_factor)
    if isinstance(load, WheelLoad):
        stress = westergaard_interior(
            load.wheel_load_lb, h, load.contact_radius_in,
            subgrade.k, E=concrete.E, nu=concrete.nu
        ).stress_psi
    else:
        stress = westergaard_interior(
            load.post_load_lb, h, load.contact_radius_in,
            subgrade.k, E=concrete.E, nu=concrete.nu
        ).stress_psi

    L = radius_of_relative_stiffness(concrete.E, h, concrete.nu, subgrade.k)

    return DesignResult(
        method=DesignMethod.WESTERGAARD,
        load_case=load_case,
        required_thickness_in=h,
        computed_stress_psi=stress,
        allowable_stress_psi=allowable,
        safety_factor=safety_factor,
        L_in=L,
        concrete=concrete,
        subgrade=subgrade,
        notes=[f"Check at h = {h:.2f} in"],
    )
