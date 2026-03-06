"""Load models for slab-on-ground design.

ACI 360R-10, Chapter 5 identifies the following load types:
  - Vehicle / wheel loads   (§5.2)
  - Concentrated (rack post) loads  (§5.3)
  - Distributed / uniform loads     (§5.4)
  - Line and strip loads             (§5.5)
  - Construction loads               (§5.7)

All values in US customary units (lb, in, psi).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator


class WheelLoad(BaseModel, frozen=True):
    """Single-axle wheel load.

    The PCA method (§7.2.1) uses:
      - Axle load P_axle [lb]
      - Effective contact area per wheel A_c [in²]
      - Wheel spacing s [in] (center-to-center)

    The equivalent contact radius a = sqrt(A_c / π) is used in Westergaard
    equations.  For dual wheels, use effective_contact_area which accounts for
    the combined footprint.

    Args:
        axle_load_lb: Total axle load, lb.
        contact_area_in2: Effective contact area of ONE wheel, in².
        wheel_spacing_in: Center-to-center wheel spacing, in.
        is_dual_wheel: True if each end of axle has dual wheels.
    """

    axle_load_lb: float = Field(gt=0, description="Total axle load, lb")
    contact_area_in2: float = Field(
        gt=0, description="Effective contact area per wheel (single or dual), in²"
    )
    wheel_spacing_in: float = Field(
        gt=0, description="Center-to-center wheel spacing, in"
    )
    is_dual_wheel: bool = Field(default=False, description="True if dual wheels per end")

    @property
    def wheel_load_lb(self) -> float:
        """Load per wheel end, lb (half of axle load)."""
        return self.axle_load_lb / 2.0

    @property
    def contact_radius_in(self) -> float:
        """Equivalent circular contact radius for ONE wheel, in."""
        return math.sqrt(self.contact_area_in2 / math.pi)

    @classmethod
    def from_lift_truck(
        cls,
        capacity_lb: float,
        *,
        axle_load_lb: float,
        tire_pressure_psi: float = 100.0,
        wheel_spacing_in: float,
        is_dual_wheel: bool = False,
    ) -> "WheelLoad":
        """Construct from lift-truck parameters.

        Contact area = axle_load / (2 * tire_pressure) per wheel
        (ACI 360R-10 §7.2.1.1)
        """
        contact_area = axle_load_lb / (2.0 * tire_pressure_psi)
        return cls(
            axle_load_lb=axle_load_lb,
            contact_area_in2=contact_area,
            wheel_spacing_in=wheel_spacing_in,
            is_dual_wheel=is_dual_wheel,
        )

    @classmethod
    def from_si(
        cls,
        axle_load_kn: float,
        contact_area_mm2: float,
        wheel_spacing_mm: float,
    ) -> "WheelLoad":
        from slab_designer.units import KN_TO_LB, MM_TO_IN

        return cls(
            axle_load_lb=axle_load_kn * KN_TO_LB,
            contact_area_in2=contact_area_mm2 * (MM_TO_IN**2),
            wheel_spacing_in=wheel_spacing_mm * MM_TO_IN,
        )


class RackLoad(BaseModel, frozen=True):
    """Concentrated (rack post) load.

    ACI 360R-10 §5.3 and §7.2.1.2.
    Used for warehouse storage rack systems.

    Args:
        post_load_lb: Load per post, lb.
        base_plate_area_in2: Contact area of base plate, in².
        long_spacing_in: Long (y) spacing between posts in grid, in.
        short_spacing_in: Short (x) spacing between posts in grid, in.
    """

    post_load_lb: float = Field(gt=0, description="Post load, lb")
    base_plate_area_in2: float = Field(
        gt=0, description="Base plate contact area, in²"
    )
    long_spacing_in: float = Field(
        gt=0, description="Long (y) spacing between posts in grid, in"
    )
    short_spacing_in: float = Field(
        gt=0, description="Short (x) spacing between posts in grid, in"
    )

    @property
    def contact_radius_in(self) -> float:
        """Equivalent circular contact radius, in."""
        return math.sqrt(self.base_plate_area_in2 / math.pi)

    @classmethod
    def from_si(
        cls,
        post_load_kn: float,
        base_plate_area_mm2: float,
        long_spacing_mm: float,
        short_spacing_mm: float,
    ) -> "RackLoad":
        from slab_designer.units import KN_TO_LB, MM_TO_IN

        return cls(
            post_load_lb=post_load_kn * KN_TO_LB,
            base_plate_area_in2=base_plate_area_mm2 * MM_TO_IN**2,
            long_spacing_in=long_spacing_mm * MM_TO_IN,
            short_spacing_in=short_spacing_mm * MM_TO_IN,
        )


class UniformLoad(BaseModel, frozen=True):
    """Uniformly distributed load on partial area (warehouse storage).

    ACI 360R-10 §5.4.  The critical condition is tension at the TOP of the
    slab in the unloaded aisle between loaded bays.

    Args:
        intensity_psf: Load intensity, lb/ft² (psf).
        aisle_width_ft: Clear aisle width, ft.
        load_width_ft: Width of loaded zone on each side of aisle, ft.
    """

    intensity_psf: float = Field(gt=0, description="Load intensity, lb/ft²")
    aisle_width_ft: float = Field(
        gt=0, description="Clear aisle width, ft"
    )
    load_width_ft: float = Field(
        default=300.0 / 12.0,  # effectively infinite (25 ft)
        gt=0,
        description="Width of loaded zone on each side of aisle, ft",
    )

    @property
    def intensity_psi(self) -> float:
        """Load intensity in psi (lb/in²)."""
        return self.intensity_psf / 144.0

    @property
    def aisle_half_width_in(self) -> float:
        """Half-aisle width a, in (used in Rice/Hetenyi formula)."""
        return self.aisle_width_ft * 12.0 / 2.0


class LineLoad(BaseModel, frozen=True):
    """Line or strip load (e.g., partition wall, roll storage).

    ACI 360R-10 §5.5.  Treated as a line load when the strip width is less
    than ~1/3 of the radius of relative stiffness L.

    Args:
        load_per_unit_length_lb_ft: Load magnitude, lb/ft of length.
    """

    load_per_unit_length_lb_ft: float = Field(
        gt=0, description="Line load intensity, lb/ft"
    )

    @property
    def load_per_unit_length_lb_in(self) -> float:
        """Load per unit length in lb/in."""
        return self.load_per_unit_length_lb_ft / 12.0


class LoadLocation(str):
    """Load position relative to slab edges.

    Values:
        'interior' - load is far from edges (≥ 4L from edge)
        'edge'     - load is at a free edge, away from corners
        'corner'   - load is at a free corner
    """

    INTERIOR: str = "interior"
    EDGE: str = "edge"
    CORNER: str = "corner"


# Lift truck reference data from ACI 360R-10 Table 5.1
# (capacity_lb, axle_load_range_lb, wheel_spacing_range_in)
LIFT_TRUCK_TABLE: list[dict] = [
    {"capacity_lb": 2_000, "axle_load_lb": 6_400, "wheel_spacing_in": 28.0},
    {"capacity_lb": 3_000, "axle_load_lb": 8_600, "wheel_spacing_in": 30.0},
    {"capacity_lb": 5_000, "axle_load_lb": 12_700, "wheel_spacing_in": 33.0},
    {"capacity_lb": 8_000, "axle_load_lb": 18_000, "wheel_spacing_in": 36.0},
    {"capacity_lb": 10_000, "axle_load_lb": 22_000, "wheel_spacing_in": 41.0},
    {"capacity_lb": 15_000, "axle_load_lb": 31_500, "wheel_spacing_in": 45.0},
    {"capacity_lb": 20_000, "axle_load_lb": 41_700, "wheel_spacing_in": 44.5},
]
