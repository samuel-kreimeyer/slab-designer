"""Westergaard slab-on-ground analysis.

Implements the three Westergaard load cases for a slab-on-ground plus the
Rice aisle-moment formula for partial area loading.

References:
  - ACI 360R-10, §7.2 and Eq. (7-3) through (7-6)
  - Westergaard, H. M. (1923, 1925, 1926)
  - Portland Cement Association (PCA), "Slab Thickness Design for Industrial
    Concrete Floors on Grade" (IS195.01D, 1984)
  - Rice, P. F. (1957) for distributed/aisle loading

Unit system: US customary (psi, in, lb).

Westergaard equations used (PCA formulation for ν = 0.15):
  Radius of relative stiffness (Eq. 7-2):
    L = [E * h³ / (12 * (1 - ν²) * k)] ** 0.25

  Equivalent contact radius b (small-radius correction, Westergaard):
    if a/h < 0.36:  b = sqrt(1.6 * a² + h²) - 0.675 * h
    else:            b = a

  Case 2 – Interior load, tension at bottom (Eq. 7-4):
    fb = (0.316 * P / h²) * (4 * log10(L/b) + 1.069)
    Coefficient 0.316 = 3(1+ν) * ln(10) / (8π) for ν = 0.15.

  Case 3 – Edge load, tension at bottom (Eq. 7-5):
    fb = (0.572 * P / h²) * (4 * log10(L/b) + 0.359)
    Coefficient 0.572 is the Westergaard 1926 edge coefficient for ν = 0.15.

  Case 1 – Corner load, tension at top:
    ft = (3 * P / h²) * [1 - (a * sqrt(2) / L) ** 0.6]
    (Westergaard 1926 with Pickett correction – standard form in ACI literature)

  Case 4 – Aisle/partial uniform load, negative moment at aisle centre (Eq. 7-6):
    λ = (k / (4 * E * I)) ** 0.25   where I = h³/12 per unit width
    Mc = (w * a / λ) * exp(-λ * a)  [Rice 1957, simplified form]
    Note: The exact ACI 360R-10 Eq. (7-6) was not decoded from the PDF;
          this expression is consistent with Hetenyi beam-on-foundation theory.

Logarithms in Eq. (7-4) and (7-5) are base-10 per ACI 360R-10 §7.2 text.

Verification:
  ACI 360R-10 Appendix 4: P=15,000 lb, h=6 in, a=4.5 in, k=150 pci →
    L = 26.4 in, b = 4.5 in (a/h=0.75 > 0.36),
    fb = 0.316×15000/36 × (4×log10(26.4/4.5) + 1.069) ≈ 546 psi  ✓ (ACI: ~545 psi)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Core structural parameter
# ---------------------------------------------------------------------------

def radius_of_relative_stiffness(
    E: float,
    h: float,
    nu: float,
    k: float,
) -> float:
    """Radius of relative stiffness L, in.

    ACI 360R-10 Eq. (7-2):
      L = [E * h³ / (12 * (1 - ν²) * k)] ** 0.25

    Args:
        E:  Elastic modulus of concrete, psi.
        h:  Slab thickness, in.
        nu: Poisson's ratio.
        k:  Modulus of subgrade reaction, lb/in³.

    Returns:
        L in inches.
    """
    numerator = E * h**3
    denominator = 12.0 * (1.0 - nu**2) * k
    return (numerator / denominator) ** 0.25


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WestergaardStress:
    """Stresses computed by Westergaard analysis for a given slab section.

    All stresses in psi (positive = tension).
    """

    h: float
    """Slab thickness, in."""

    L: float
    """Radius of relative stiffness, in."""

    case: str
    """Load case: 'interior', 'edge', or 'corner'."""

    stress_psi: float
    """Computed flexural stress, psi (tension)."""

    P: float
    """Applied concentrated load, lb."""

    a: float
    """Equivalent contact radius, in."""

    def utilization(self, allowable_stress: float) -> float:
        """Ratio of computed stress to allowable stress (≤ 1.0 = OK)."""
        return self.stress_psi / allowable_stress

    def is_adequate(self, allowable_stress: float) -> bool:
        """True if computed stress ≤ allowable stress."""
        return self.stress_psi <= allowable_stress


# ---------------------------------------------------------------------------
# Westergaard Case 2 – Interior concentrated load
# ---------------------------------------------------------------------------

def westergaard_interior(
    P: float,
    h: float,
    a: float,
    k: float,
    E: float = 4_000_000.0,
    nu: float = 0.15,
) -> WestergaardStress:
    """Flexural tensile stress at slab bottom under interior concentrated load.

    ACI 360R-10 Eq. (7-4) — PCA formulation for ν = 0.15:
      b = sqrt(1.6a² + h²) - 0.675h  if a/h < 0.36,  else  b = a
      fb = (0.316 * P / h²) * (4 * log10(L/b) + 1.069)

    The coefficient 0.316 = 3(1+ν)·ln(10)/(8π) evaluated at ν = 0.15.
    Valid when load is ≥ 4L from any free edge.
    Stress is tension at the bottom of the slab, directly under the load.

    Args:
        P:  Concentrated load, lb.
        h:  Slab thickness, in.
        a:  Equivalent circular contact radius, in.
        k:  Modulus of subgrade reaction, lb/in³.
        E:  Elastic modulus, psi. Default 4,000,000 (ACI PCA/COE default).
        nu: Poisson's ratio. Default 0.15 (ACI PCA default).

    Returns:
        WestergaardStress with case='interior'.
    """
    L = radius_of_relative_stiffness(E, h, nu, k)
    # Corrected equivalent contact radius (Westergaard small-radius correction)
    b = math.sqrt(1.6 * a**2 + h**2) - 0.675 * h if a / h < 0.36 else a
    fb = (0.316 * P / h**2) * (4.0 * math.log10(L / b) + 1.069)
    return WestergaardStress(h=h, L=L, case="interior", stress_psi=fb, P=P, a=a)


# ---------------------------------------------------------------------------
# Westergaard Case 3 – Edge concentrated load
# ---------------------------------------------------------------------------

def westergaard_edge(
    P: float,
    h: float,
    a: float,
    k: float,
    E: float = 4_000_000.0,
    nu: float = 0.15,
) -> WestergaardStress:
    """Flexural tensile stress at slab bottom under edge concentrated load.

    ACI 360R-10 Eq. (7-5) — Westergaard (1926) for ν = 0.15:
      b = sqrt(1.6a² + h²) - 0.675h  if a/h < 0.36,  else  b = a
      fb = (0.572 * P / h²) * (4 * log10(L/b) + 0.359)

    Load applied at a free edge, well away from corners.
    Stress is tension at the bottom, directly under the load.
    Note: The COE method applies a joint-transfer coefficient of 0.75,
    effectively reducing the edge stress by 25% when load transfer exists.

    Args:
        P:  Concentrated load, lb.
        h:  Slab thickness, in.
        a:  Equivalent circular contact radius, in.
        k:  Modulus of subgrade reaction, lb/in³.
        E:  Elastic modulus, psi.
        nu: Poisson's ratio.

    Returns:
        WestergaardStress with case='edge'.
    """
    L = radius_of_relative_stiffness(E, h, nu, k)
    # Corrected equivalent contact radius (same as interior case)
    b = math.sqrt(1.6 * a**2 + h**2) - 0.675 * h if a / h < 0.36 else a
    fb = (0.572 * P / h**2) * (4.0 * math.log10(L / b) + 0.359)
    return WestergaardStress(h=h, L=L, case="edge", stress_psi=fb, P=P, a=a)


# ---------------------------------------------------------------------------
# Westergaard Case 1 – Corner concentrated load
# ---------------------------------------------------------------------------

def westergaard_corner(
    P: float,
    h: float,
    a: float,
    k: float,
    E: float = 4_000_000.0,
    nu: float = 0.15,
) -> WestergaardStress:
    """Flexural tensile stress at slab top near a free corner.

    Westergaard (1926) with Pickett correction (standard ACI usage):
      ft = (3 * P / h²) * [1 - (a * √2 / L) ** 0.6]

    The critical tension is at the top of the slab, at a distance
    approximately a√2 from the corner along the corner bisector.

    Note: The ACI 360R-10 Eq. (7-3) formula could not be decoded from the
    source PDF. This is the standard formulation from the engineering literature
    consistent with ACI design practice.

    Args:
        P:  Concentrated load, lb.
        h:  Slab thickness, in.
        a:  Equivalent circular contact radius, in.
        k:  Modulus of subgrade reaction, lb/in³.
        E:  Elastic modulus, psi.
        nu: Poisson's ratio.

    Returns:
        WestergaardStress with case='corner'.
    """
    L = radius_of_relative_stiffness(E, h, nu, k)
    ratio = (a * math.sqrt(2.0)) / L
    ft = (3.0 * P / h**2) * (1.0 - ratio**0.6)
    return WestergaardStress(h=h, L=L, case="corner", stress_psi=ft, P=P, a=a)


# ---------------------------------------------------------------------------
# Case 4 – Aisle / partial-area uniform load (Rice 1957)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AisleMoment:
    """Negative moment at aisle centre from symmetric uniform loads.

    Per ACI 360R-10 Eq. (7-6) / Rice (1957).
    """

    h: float
    """Slab thickness, in."""

    L: float
    """Radius of relative stiffness, in."""

    lambda_: float
    """Beam-foundation characteristic, in⁻¹."""

    half_aisle_in: float
    """Half-aisle width a, in."""

    Mc_inlb_per_in: float
    """Critical negative moment at aisle centre, in·lb / in of slab width."""

    def as_stress_psi(self) -> float:
        """Convert aisle moment to extreme-fibre flexural stress (top), psi."""
        S = self.h**2 / 6.0  # section modulus per unit width, in³/in
        return self.Mc_inlb_per_in / S


def westergaard_aisle(
    w: float,
    h: float,
    half_aisle_in: float,
    k: float,
    E: float = 4_000_000.0,
    nu: float = 0.15,
) -> AisleMoment:
    """Negative aisle moment from partial-area uniform loading (Rice 1957).

    ACI 360R-10, Case 4 – loads on both sides of a clear aisle.
    Produces tension at the TOP of the slab at the aisle centreline.

    Formula (Hetenyi / Rice, beam-on-elastic-foundation):
      λ = (k / (4EI)) ** 0.25  where I = h³/12 per unit width
      Mc = (w / λ) * a * exp(-λ * a)

    Note: This implements the simplified form. The exact ACI 360R-10 Eq. (7-6)
    was not decoded from the source PDF; tables A1.2 and A2 (based on Hetenyi
    1946) provide verified reference values for the PCA/WRI methods.

    Args:
        w:            Uniform load, psi (lb/in²).
        h:            Slab thickness, in.
        half_aisle_in: Half-aisle width a, in.
        k:            Modulus of subgrade reaction, lb/in³.
        E:            Elastic modulus, psi.
        nu:           Poisson's ratio (not used directly in Rice formula).

    Returns:
        AisleMoment with Mc in in·lb/in (positive = tension at top).
    """
    I = h**3 / 12.0  # per unit width, in³/in
    lam = (k / (4.0 * E * I)) ** 0.25  # in⁻¹
    a = half_aisle_in
    Mc = (w / lam) * a * math.exp(-lam * a)
    L = radius_of_relative_stiffness(E, h, nu, k)
    return AisleMoment(
        h=h,
        L=L,
        lambda_=lam,
        half_aisle_in=a,
        Mc_inlb_per_in=Mc,
    )


# ---------------------------------------------------------------------------
# Allowable stress calculation helpers
# ---------------------------------------------------------------------------

def allowable_stress(fr: float, safety_factor: float) -> float:
    """Allowable flexural tensile stress, psi.

    ACI 360R-10 §5.2: allowable = fr / SF
    Typical SF: 1.4–2.0 depending on load type (Table 5.2).
    """
    return fr / safety_factor


def allowable_stress_with_precompression(
    fr: float,
    safety_factor: float,
    precompression_psi: float,
) -> float:
    """Allowable stress for post-tensioned slab.

    ACI 360R-10 §10.2.1:
    The net precompression from post-tensioning is added to the permissible
    tensile stress:
      allowable = fr / SF + fp
    where fp is the effective residual precompression.

    Args:
        fr:                 Modulus of rupture, psi.
        safety_factor:      Factor of safety.
        precompression_psi: Residual precompression from post-tensioning, psi.

    Returns:
        Allowable tensile stress, psi.
    """
    return fr / safety_factor + precompression_psi


# ---------------------------------------------------------------------------
# Westergaard with COE joint transfer coefficient
# ---------------------------------------------------------------------------

COE_JOINT_TRANSFER = 0.75  # ACI 360R-10 §7.2.3
COE_IMPACT_FACTOR = 1.25   # 25% impact built into COE method
COE_POISSON = 0.20         # COE method assumes ν = 0.20


def westergaard_edge_coe(
    P: float,
    h: float,
    a: float,
    k: float,
    E: float = 4_000_000.0,
) -> WestergaardStress:
    """Edge stress using COE assumptions.

    COE method (ACI 360R-10 §7.2.3):
      - Based on Westergaard edge formula
      - Joint transfer coefficient: 0.75 (25% reduction in edge stress)
      - Impact factor: 25% (applied to load)
      - ν = 0.20 (COE default)
      - E = 4,000,000 psi (COE default)

    Effective load = P * impact_factor
    Effective stress = edge_stress * joint_transfer_coeff
    """
    P_eff = P * COE_IMPACT_FACTOR
    raw = westergaard_edge(P_eff, h, a, k, E=E, nu=COE_POISSON)
    effective_stress = raw.stress_psi * COE_JOINT_TRANSFER
    return WestergaardStress(
        h=h,
        L=raw.L,
        case="edge_coe",
        stress_psi=effective_stress,
        P=P,
        a=a,
    )
