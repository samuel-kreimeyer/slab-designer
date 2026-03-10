"""Appendix-style end-to-end regression tests through the public API."""

from slab_designer import (
    Concrete,
    PostTensionedDesign,
    PostTensionTendon,
    ShrinkageCompensatingDesign,
    Subgrade,
    allowable_stress_with_precompression,
    design_post_tensioned,
    design_shrinkage_compensating,
)
from slab_designer.soil import SlipSheet


class TestAppendix4Examples:
    def test_a41_post_tensioning_to_minimize_cracking(self):
        """Appendix A4.1: 500 ft strip, h=6 in, mu=0.5, Pe=26 kip, fp=250 psi."""
        result = design_post_tensioned(
            PostTensionedDesign(
                slab_length_ft=500.0,
                slab_thickness_in=6.0,
                tendon=PostTensionTendon(Pe=26_000.0),
                concrete=Concrete(fc=4000.0, fr=570.0),
                subgrade=Subgrade(k=150.0, slip_sheet=SlipSheet.ONE_POLY, mu=0.5),
                residual_prestress_psi=250.0,
            )
        )

        assert abs(result.Pr_lb_ft - 9_375.0) < 1e-6
        assert abs(result.required_force_lb_ft - 27_375.0) < 1e-6
        assert abs(result.tendon_spacing_ft - 0.9497716894977168) < 1e-12
        assert abs(result.tendon_spacing_in - 11.397260273972602) < 1e-12

    def test_a42_equivalent_tensile_stress_example(self):
        """Appendix A4.2: 150 psi residual compression increases allowable to 435 psi."""
        allowable = allowable_stress_with_precompression(
            fr=9.0 * (4000.0**0.5),
            safety_factor=2.0,
            precompression_psi=150.0,
        )
        assert abs(allowable - 434.60498941515414) < 1e-9
        assert abs(allowable - 435.0) < 0.5


class TestAppendix5Examples:
    def test_a52_member_expansion_anchor_no4_at_18in(self):
        """Appendix A5.2: rho=0.182%, prism=0.05% -> eps_slab=0.000454."""
        result = design_shrinkage_compensating(
            ShrinkageCompensatingDesign(
                slab_thickness_in=6.0,
                slab_length_ft=100.0,
                slab_width_ft=12.0,
                prism_expansion_pct=0.05,
                rho=0.00182,
                volume_surface_ratio=6.0,
                concrete=Concrete(fc=4000.0, fr=570.0),
                subgrade=Subgrade(k=100.0, slip_sheet=SlipSheet.TWO_POLY),
                expansion_at_one_end=True,
            )
        )

        assert abs(result.slab_expansion_strain - 0.000454) < 1e-9
        assert abs(result.isolation_joint_width_in - 1.0896) < 1e-9
        assert result.full_compensation_ok
        assert result.validation_status == "digitized"

    def test_a52_equivalent_restrained_anchor(self):
        """Appendix A5.2: equivalent rho=0.241%, prism=0.05% -> eps_slab=0.000413."""
        result = design_shrinkage_compensating(
            ShrinkageCompensatingDesign(
                slab_thickness_in=6.0,
                slab_length_ft=100.0,
                slab_width_ft=12.0,
                prism_expansion_pct=0.05,
                rho=0.00241,
                volume_surface_ratio=6.0,
                concrete=Concrete(fc=4000.0, fr=570.0),
                subgrade=Subgrade(k=100.0, slip_sheet=SlipSheet.TWO_POLY),
                expansion_at_one_end=True,
            )
        )

        assert abs(result.slab_expansion_strain - 0.000413) < 1e-9
        assert abs(result.isolation_joint_width_in - 0.9912) < 1e-9
        assert result.internal_compressive_stress_psi > 0
