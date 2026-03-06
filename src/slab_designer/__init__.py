"""slab_designer – Concrete slab-on-ground design per ACI 360R-10.

Public API
----------
Materials
~~~~~~~~~
  Concrete            – concrete material properties
  FiberProperties     – FRC fiber properties (Re,3)
  PostTensionTendon   – post-tensioning tendon

Soil
~~~~
  Subgrade            – subgrade modulus and friction
  SubgradeClass       – qualitative soil classification
  SlipSheet           – slip membrane type

Loads
~~~~~
  WheelLoad           – single-axle wheel load
  RackLoad            – rack-post concentrated load
  UniformLoad         – partial-area distributed load
  LineLoad            – line / strip load

Analysis (Westergaard)
~~~~~~~~~~~~~~~~~~~~~~
  radius_of_relative_stiffness
  westergaard_interior
  westergaard_edge
  westergaard_corner
  westergaard_aisle
  westergaard_edge_coe
  WestergaardStress
  AisleMoment

Design
~~~~~~
  design_for_wheel_load          – PCA/COE wheel load
  design_for_rack_load           – PCA rack post
  design_for_uniform_load        – PCA/WRI aisle loading
  design_post_tensioned          – crack-control PT design
  design_frc_elastic             – FRC elastic method
  design_frc_yield_line          – FRC yield-line method
  find_re3_for_load              – inverse FRC Re,3 solver
  design_shrinkage_compensating  – shrinkage-compensating concrete
  isolation_joint_width          – SC joint width calculation
  DesignResult
  PostTensionedResult
  FRCDesignResult
  ShrinkageCompensatingResult

Utilities
~~~~~~~~~
  SafetyFactors       – recommended ACI safety factors
  find_required_thickness
"""

from slab_designer.analysis import (
    AisleMoment,
    WestergaardStress,
    allowable_stress,
    allowable_stress_with_precompression,
    radius_of_relative_stiffness,
    westergaard_aisle,
    westergaard_corner,
    westergaard_edge,
    westergaard_edge_coe,
    westergaard_interior,
)
from slab_designer.design import (
    DesignResult,
    FRCDesignResult,
    PostTensionedDesign,
    PostTensionedResult,
    SafetyFactors,
    ShrinkageCompensatingResult,
    design_for_rack_load,
    design_for_uniform_load,
    design_for_wheel_load,
    design_frc_elastic,
    design_frc_yield_line,
    design_post_tensioned,
    design_shrinkage_compensating,
    find_re3_for_load,
    find_required_thickness,
    isolation_joint_width,
)
from slab_designer.loads import LineLoad, RackLoad, UniformLoad, WheelLoad
from slab_designer.materials import Concrete, FiberProperties, PostTensionTendon
from slab_designer.soil import SlipSheet, Subgrade, SubgradeClass

__version__ = "0.1.0"

__all__ = [
    # Materials
    "Concrete",
    "FiberProperties",
    "PostTensionTendon",
    # Soil
    "Subgrade",
    "SubgradeClass",
    "SlipSheet",
    # Loads
    "WheelLoad",
    "RackLoad",
    "UniformLoad",
    "LineLoad",
    # Analysis
    "radius_of_relative_stiffness",
    "westergaard_interior",
    "westergaard_edge",
    "westergaard_corner",
    "westergaard_aisle",
    "westergaard_edge_coe",
    "WestergaardStress",
    "AisleMoment",
    "allowable_stress",
    "allowable_stress_with_precompression",
    # Design
    "design_for_wheel_load",
    "design_for_rack_load",
    "design_for_uniform_load",
    "design_post_tensioned",
    "design_frc_elastic",
    "design_frc_yield_line",
    "find_re3_for_load",
    "design_shrinkage_compensating",
    "isolation_joint_width",
    # Results
    "DesignResult",
    "PostTensionedResult",
    "FRCDesignResult",
    "ShrinkageCompensatingResult",
    # Helpers
    "SafetyFactors",
    "find_required_thickness",
    "PostTensionedDesign",
]
