"""Slab-on-ground design methods per ACI 360R-10."""

from slab_designer.design.frc import (
    FRCDesignResult,
    design_frc_elastic,
    design_frc_yield_line,
    find_re3_for_load,
)
from slab_designer.design.post_tensioned import (
    PostTensionedDesign,
    PostTensionedResult,
    design_post_tensioned,
)
from slab_designer.design.shrinkage_compensating import (
    ShrinkageCompensatingDesign,
    ShrinkageCompensatingResult,
    design_shrinkage_compensating,
    isolation_joint_width,
)
from slab_designer.design.unreinforced import (
    DesignResult,
    SafetyFactors,
    design_for_rack_load,
    design_for_uniform_load,
    design_for_wheel_load,
    find_required_thickness,
)

__all__ = [
    # Unreinforced
    "DesignResult",
    "SafetyFactors",
    "design_for_wheel_load",
    "design_for_rack_load",
    "design_for_uniform_load",
    "find_required_thickness",
    # Post-tensioned
    "PostTensionedDesign",
    "PostTensionedResult",
    "design_post_tensioned",
    # FRC
    "FRCDesignResult",
    "design_frc_elastic",
    "design_frc_yield_line",
    "find_re3_for_load",
    # Shrinkage-compensating
    "ShrinkageCompensatingDesign",
    "ShrinkageCompensatingResult",
    "design_shrinkage_compensating",
    "isolation_joint_width",
]
