"""Concrete and reinforcement material models."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, field_validator, model_validator


class Concrete(BaseModel, frozen=True):
    """Concrete material properties.

    All values in US customary units (psi, lb/in³).

    ACI 360R-10 defaults:
      E = 4,000,000 psi (PCA and COE methods)
      ν = 0.15 (PCA method) or 0.20 (COE method)
    """

    fc: float = Field(gt=0, description="Compressive strength, psi")
    fr: float = Field(gt=0, description="Modulus of rupture (flexural strength), psi")
    E: float = Field(default=4_000_000.0, gt=0, description="Elastic modulus, psi")
    nu: float = Field(default=0.15, gt=0, lt=0.5, description="Poisson's ratio")
    unit_weight: float = Field(
        default=0.08681,  # 150 pcf in lb/in³
        gt=0,
        description="Unit weight, lb/in³ (default 150 pcf)",
    )

    @field_validator("fr")
    @classmethod
    def fr_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Modulus of rupture must be positive")
        return v

    @classmethod
    def from_fc_psi(
        cls,
        fc: float,
        *,
        E: float = 4_000_000.0,
        nu: float = 0.15,
        fr_factor: float = 7.5,
    ) -> "Concrete":
        """Create concrete with fr estimated from fc.

        ACI 318: fr = fr_factor * sqrt(fc), default fr_factor=7.5 (psi).
        Some references use 6.0 (lower bound) or 7.5 (normal weight).

        Args:
            fc: Compressive strength, psi.
            E: Elastic modulus, psi.
            nu: Poisson's ratio.
            fr_factor: Coefficient for fr = fr_factor * sqrt(fc). Default 7.5.
        """
        fr = fr_factor * math.sqrt(fc)
        return cls(fc=fc, fr=fr, E=E, nu=nu)

    @classmethod
    def from_si(
        cls,
        fc_mpa: float,
        fr_mpa: float,
        E_mpa: float = 28_000.0,
        nu: float = 0.15,
    ) -> "Concrete":
        """Create from SI units (MPa)."""
        from slab_designer.units import MPA_TO_PSI

        return cls(
            fc=fc_mpa * MPA_TO_PSI,
            fr=fr_mpa * MPA_TO_PSI,
            E=E_mpa * MPA_TO_PSI,
            nu=nu,
        )


class FiberProperties(BaseModel, frozen=True):
    """Steel fiber properties for FRC slabs.

    References:
      - ACI 360R-10, Chapter 11
      - JSCE SF4 and ASTM C1399 for Re,3 determination
    """

    re3: float = Field(
        ge=0,
        le=200,
        description=(
            "Residual strength factor Re,3 (%), determined per JSCE SF4 or ASTM C1399. "
            "Represents post-crack load-carrying ability as % of modulus of rupture. "
            "Typical range: 20–80% depending on fiber type and dosage."
        ),
    )
    fiber_content_lb_yd3: float | None = Field(
        default=None,
        ge=0,
        description="Fiber dosage, lb/yd³. Informational only.",
    )

    @model_validator(mode="after")
    def check_re3_reasonable(self) -> "FiberProperties":
        if self.re3 < 20:
            # ACI 360R-10 §11.3.3.3: Re,3 must be > 30% for yield-line method
            pass  # allow but note in design checks
        return self


class PostTensionTendon(BaseModel, frozen=True):
    """Post-tensioning tendon properties.

    ACI 360R-10, Chapter 10.
    """

    Pe: float = Field(
        gt=0,
        description=(
            "Effective prestress force per tendon after all losses "
            "(friction, elastic shortening, creep, shrinkage, relaxation), lb. "
            "Typical value for 0.5-in. monostrand: 25,000–33,000 lb."
        ),
    )


class Reinforcement(BaseModel, frozen=True):
    """Mild steel reinforcement properties."""

    fy: float = Field(default=60_000.0, gt=0, description="Yield strength, psi")
    Es: float = Field(default=29_000_000.0, gt=0, description="Elastic modulus, psi")
    rho: float = Field(
        default=0.0,
        ge=0,
        le=0.08,
        description="Steel ratio (As / gross concrete area)",
    )
