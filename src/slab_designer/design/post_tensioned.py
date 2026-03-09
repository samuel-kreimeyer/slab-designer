"""Post-tensioned slab-on-ground design.

ACI 360R-10, Chapter 10.

Two primary design approaches:
  1. Crack-control design (§10.3): minimum PT to overcome subgrade friction
     and maintain residual compression.
  2. Industrial floor design (§10.4): thickness per PCA/WRI/COE methods
     with increased allowable stress due to precompression.

Key equations (both decoded in ACI 360R-10 source):

  Eq. (10-1) – Subgrade friction force:
    Pr = µ * Wslab * L_slab / 2
    where:
      µ        = coefficient of friction (0.30–1.00)
      Wslab    = self-weight, lb/ft²
      L_slab   = slab length in direction considered, ft
      Pr       = post-tensioning force required to overcome friction, lb/ft

  Eq. (10-2) – Tendon spacing:
    Sten = Pe / (fp * W * H + Pr)
    where:
      Pe   = effective prestress force per tendon, lb
      fp   = minimum residual prestress, psi
      W    = unit strip width = 12 in/ft
      H    = slab thickness, in
      Pr   = from Eq. (10-1), lb/ft
      Sten = tendon spacing, ft

Recommended residual prestress levels (ACI 360R-10 Table 10.1):
  Residential:                  50–75 psi
  Industrial up to 100 ft:     75–100 psi
  Industrial up to 200 ft:    100–150 psi
  Industrial up to 300 ft:    150–200 psi
  Industrial up to 400 ft:    200–250 psi
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from slab_designer.analysis import (
    allowable_stress_with_precompression,
    radius_of_relative_stiffness,
    westergaard_interior,
)
from slab_designer.materials import Concrete, PostTensionTendon
from slab_designer.soil import Subgrade
from slab_designer.units import CONCRETE_UNIT_WEIGHT_PCF

# ---------------------------------------------------------------------------
# Recommended residual prestress (ACI 360R-10 Table 10.1)
# ---------------------------------------------------------------------------

def recommended_residual_prestress(slab_length_ft: float, industrial: bool = True) -> float:
    """Recommended minimum residual prestress fp, psi.

    ACI 360R-10 Table 10.1.

    Args:
        slab_length_ft: Slab length in the direction being considered, ft.
        industrial:     True for industrial floor; False for residential.

    Returns:
        Recommended fp, psi.
    """
    if not industrial:
        return 62.5  # midpoint of 50–75 psi
    if slab_length_ft <= 100:
        return 87.5   # midpoint of 75–100 psi
    if slab_length_ft <= 200:
        return 125.0  # midpoint of 100–150 psi
    if slab_length_ft <= 300:
        return 175.0  # midpoint of 150–200 psi
    return 225.0      # midpoint of 200–250 psi (up to 400 ft)


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class PostTensionedDesign(BaseModel, frozen=True):
    """Input parameters for post-tensioned slab design.

    Args:
        slab_length_ft:         Slab length in direction being considered, ft.
        slab_thickness_in:      Slab thickness, in.
        tendon:                 Post-tensioning tendon properties.
        concrete:               Concrete properties.
        subgrade:               Subgrade properties.
        residual_prestress_psi: Minimum average residual prestress fp, psi.
                                If None, computed from ACI Table 10.1.
        industrial:             True for industrial floor; affects fp selection.
    """

    slab_length_ft: float = Field(gt=0, description="Slab length, ft")
    slab_thickness_in: float = Field(gt=0, description="Slab thickness, in")
    tendon: PostTensionTendon
    concrete: Concrete
    subgrade: Subgrade
    residual_prestress_psi: float | None = Field(
        default=None,
        description="Override residual prestress fp, psi",
    )
    industrial: bool = Field(default=True)

    @property
    def fp(self) -> float:
        """Minimum residual prestress, psi."""
        if self.residual_prestress_psi is not None:
            return self.residual_prestress_psi
        return recommended_residual_prestress(self.slab_length_ft, self.industrial)

    @property
    def slab_self_weight_lb_ft2(self) -> float:
        """Slab self-weight per unit area, lb/ft²."""
        return (self.slab_thickness_in / 12.0) * CONCRETE_UNIT_WEIGHT_PCF


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PostTensionedResult:
    """Result of post-tensioned slab design (crack-control method).

    ACI 360R-10 §10.3.
    """

    design: PostTensionedDesign

    Pr_lb_ft: float
    """PT force required to overcome subgrade friction, lb/ft.  Eq. (10-1)."""

    fp_psi: float
    """Residual prestress used in design, psi."""

    required_force_lb_ft: float
    """Total PT force demand per foot of slab width, lb/ft."""

    tendon_spacing_ft: float
    """Required tendon spacing to maintain fp and overcome friction, ft.  Eq. (10-2)."""

    tendon_spacing_in: float
    """Tendon spacing in inches."""

    L_in: float
    """Radius of relative stiffness, in."""

    notes: list[str] = field(default_factory=list)

    @property
    def tendons_per_ft(self) -> float:
        """Number of tendons per foot of slab width."""
        return 1.0 / self.tendon_spacing_ft

    @property
    def net_precompression_psi(self) -> float:
        """Residual precompression maintained after friction losses, psi."""
        return self.fp_psi

    @property
    def gross_precompression_psi(self) -> float:
        """Gross average precompression from tendon force over a 1-ft slab strip, psi."""
        strip_area_in2 = 12.0 * self.design.slab_thickness_in
        return self.required_force_lb_ft / strip_area_in2


# ---------------------------------------------------------------------------
# Westergaard check for PT industrial floor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PTWestergaardCheck:
    """Check of a concentrated load on a PT industrial floor.

    ACI 360R-10 §10.4.1: use Westergaard interior formula with increased
    allowable stress (fr/SF + fp).
    """

    h_in: float
    P_lb: float
    a_in: float
    k_pci: float
    E_psi: float
    nu: float
    fr_psi: float
    safety_factor: float
    fp_psi: float

    @property
    def L_in(self) -> float:
        return radius_of_relative_stiffness(self.E_psi, self.h_in, self.nu, self.k_pci)

    @property
    def fb_psi(self) -> float:
        """Westergaard interior flexural stress, psi."""
        return westergaard_interior(
            self.P_lb, self.h_in, self.a_in, self.k_pci,
            E=self.E_psi, nu=self.nu
        ).stress_psi

    @property
    def allowable_psi(self) -> float:
        """Allowable stress = fr/SF + fp (ACI 360R-10 §10.2.1), psi."""
        return allowable_stress_with_precompression(
            self.fr_psi, self.safety_factor, self.fp_psi
        )

    @property
    def utilization(self) -> float:
        return self.fb_psi / self.allowable_psi

    @property
    def is_adequate(self) -> bool:
        return self.utilization <= 1.0


# ---------------------------------------------------------------------------
# Main design function
# ---------------------------------------------------------------------------

def design_post_tensioned(design: PostTensionedDesign) -> PostTensionedResult:
    """Post-tensioned slab crack-control design.

    ACI 360R-10 §10.3: crack-control design for lightly loaded slabs.

    Calculates:
    1. Subgrade friction force Pr (Eq. 10-1)
    2. Required tendon spacing Sten (Eq. 10-2)

    Args:
        design: PostTensionedDesign input parameters.

    Returns:
        PostTensionedResult with tendon spacing and design summary.
    """
    mu = design.subgrade.friction_coefficient
    Wslab = design.slab_self_weight_lb_ft2
    L_slab = design.slab_length_ft
    Pe = design.tendon.Pe
    fp = design.fp
    H = design.slab_thickness_in
    strip_width_in = 12.0

    # Eq. (10-1): Pr = µ * Wslab * L_slab / 2
    Pr = mu * Wslab * L_slab / 2.0

    # Force demand per foot of slab width:
    #   residual compression = fp * H * 12  [lb/ft]
    #   total PT demand      = residual compression + subgrade friction
    required_force_lb_ft = fp * H * strip_width_in + Pr

    # Tendon spacing in feet from tendon force divided by required strip force.
    Sten_ft = Pe / required_force_lb_ft
    Sten_in = Sten_ft * 12.0

    L_in = radius_of_relative_stiffness(
        design.concrete.E, H, design.concrete.nu, design.subgrade.k
    )

    notes = [
        f"Slab: {L_slab:.0f} ft × {H:.0f} in thick",
        f"Self-weight: {Wslab:.1f} lb/ft²",
        f"Friction µ = {mu:.2f} ({design.subgrade.slip_sheet.value})",
        f"Pr (Eq. 10-1) = {mu:.2f} × {Wslab:.1f} × {L_slab:.0f} / 2 = {Pr:.0f} lb/ft",
        f"Residual prestress fp = {fp:.0f} psi",
        f"Pe = {Pe:.0f} lb/tendon",
        f"Required strip force = fp × h × 12 + Pr = {required_force_lb_ft:.0f} lb/ft",
        f"Spacing = Pe / required strip force = {Pe:.0f} / {required_force_lb_ft:.0f}"
        f" = {Sten_ft:.3f} ft = {Sten_in:.1f} in",
    ]

    return PostTensionedResult(
        design=design,
        Pr_lb_ft=Pr,
        fp_psi=fp,
        required_force_lb_ft=required_force_lb_ft,
        tendon_spacing_ft=Sten_ft,
        tendon_spacing_in=Sten_in,
        L_in=L_in,
        notes=notes,
    )
