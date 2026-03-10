"""Public API export tests."""

import slab_designer


def test_top_level_exports_cover_core_entry_points():
    assert callable(slab_designer.design_for_wheel_load)
    assert callable(slab_designer.design_for_rack_load)
    assert callable(slab_designer.design_for_uniform_load)
    assert callable(slab_designer.design_post_tensioned)
    assert callable(slab_designer.design_frc_elastic)
    assert callable(slab_designer.design_frc_yield_line)
    assert callable(slab_designer.design_shrinkage_compensating)
    assert callable(slab_designer.isolation_joint_width)
    assert slab_designer.PostTensionedDesign is not None
    assert slab_designer.ShrinkageCompensatingDesign is not None
    assert slab_designer.DesignResult is not None
    assert slab_designer.FRCDesignResult is not None
    assert slab_designer.PostTensionedResult is not None
    assert slab_designer.ShrinkageCompensatingResult is not None
