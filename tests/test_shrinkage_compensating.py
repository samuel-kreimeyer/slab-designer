"""Tests for shrinkage-compensating concrete design.

Reference: ACI 360R-10 §9.4.3 worked example.

Eq. (9-1) example:
  Slab: 100 × 120 ft, expansion strain = 0.00035
  Expanding at one end → joint width = 2 × 120 × 12 × 0.00035 = 1.008 in
  Use 1 in joint at one end (or ½ in if both ends).
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from slab_designer import (
    Concrete,
    Subgrade,
    design_shrinkage_compensating,
    isolation_joint_width,
)
from slab_designer.design.shrinkage_compensating import (
    ShrinkageCompensatingDesign,
    _estimate_slab_expansion_strain,
    _interpolate_fig_94_stress,
    _member_expansion_factor,
    _required_member_expansion_strain,
    _required_prism_expansion_pct,
)
from slab_designer.soil import SlipSheet

# ---------------------------------------------------------------------------
# Isolation joint width (Eq. 9-1)
# ---------------------------------------------------------------------------

class TestIsolationJointWidth:
    def test_aci_example_one_end(self):
        """ACI §9.4.3: 120 ft slab, ε=0.00035, one end → 1.008 in."""
        jw = isolation_joint_width(
            slab_length_ft=120.0,
            expansion_strain=0.00035,
            expansion_at_one_end=True,
        )
        assert abs(jw - 1.008) < 0.01, f"Joint width = {jw:.4f} in (expected 1.008 in)"

    def test_aci_example_two_ends(self):
        """ACI §9.4.3: 120 ft slab, ε=0.00035, two ends → 0.504 in ≈ ½ in."""
        jw = isolation_joint_width(
            slab_length_ft=120.0,
            expansion_strain=0.00035,
            expansion_at_one_end=False,
        )
        assert abs(jw - 0.504) < 0.01, f"Joint width = {jw:.4f} in (expected 0.504 in)"

    def test_two_ends_half_of_one_end(self):
        """Two-end joint width should be exactly half of one-end width."""
        jw_one = isolation_joint_width(100.0, 0.0004, expansion_at_one_end=True)
        jw_two = isolation_joint_width(100.0, 0.0004, expansion_at_one_end=False)
        assert abs(jw_two - jw_one / 2.0) < 1e-9

    def test_longer_slab_wider_joint(self):
        """Longer slab → wider isolation joint."""
        jw_short = isolation_joint_width(100.0, 0.0004, True)
        jw_long = isolation_joint_width(200.0, 0.0004, True)
        assert jw_long > jw_short

    def test_higher_strain_wider_joint(self):
        """Higher expansion strain → wider isolation joint."""
        jw_low = isolation_joint_width(120.0, 0.0002, True)
        jw_high = isolation_joint_width(120.0, 0.0004, True)
        assert jw_high > jw_low

    @given(
        L=st.floats(min_value=10.0, max_value=500.0),
        eps=st.floats(min_value=0.0001, max_value=0.002),
    )
    def test_proportional_to_L_and_eps(self, L, eps):
        """Joint width is proportional to L × ε."""
        jw = isolation_joint_width(L, eps, True)
        assert abs(jw - 2.0 * L * 12.0 * eps) < 1e-6


# ---------------------------------------------------------------------------
# Shrinkage-compensating design
# ---------------------------------------------------------------------------

@pytest.fixture
def sc_design():
    """Typical SC slab design per ACI Appendix 5."""
    concrete = Concrete(fc=4000.0, fr=570.0)
    subgrade = Subgrade(k=100.0, slip_sheet=SlipSheet.TWO_POLY)
    return ShrinkageCompensatingDesign(
        slab_thickness_in=6.0,
        slab_length_ft=120.0,
        slab_width_ft=100.0,
        prism_expansion_pct=0.04,
        rho=0.0025,
        volume_surface_ratio=6.0,
        concrete=concrete,
        subgrade=subgrade,
        expansion_at_one_end=True,
    )


class TestShrinkageCompensatingDesign:
    def test_appendix_a5_unrestrained_lookup(self):
        """Appendix 5: ρ = 0.182%, prism = 0.05% -> ε_exp = 0.0454%."""
        eps = _estimate_slab_expansion_strain(
            prism_expansion_pct=0.05,
            rho=0.00182,
            volume_surface_ratio=6.0,
        )
        assert abs(eps - 0.000454) < 1e-6

    def test_appendix_a5_equivalent_restrained_lookup(self):
        """Appendix 5: ρ_eq = 0.241%, prism = 0.05% -> ε_exp = 0.0413%."""
        eps = _estimate_slab_expansion_strain(
            prism_expansion_pct=0.05,
            rho=0.00241,
            volume_surface_ratio=6.0,
        )
        assert abs(eps - 0.000413) < 1e-6

    def test_prism_expansion_check(self, sc_design):
        result = design_shrinkage_compensating(sc_design)
        assert result.validation_status == "digitized"
        assert "digitized ACI 360R-10 Fig. 9.3 and Fig. 9.4" in result.model_basis
        assert result.prism_ok  # 0.04% ≥ 0.03% minimum

    def test_rho_check_minimum(self, sc_design):
        result = design_shrinkage_compensating(sc_design)
        assert result.rho_ok  # 0.0025 within 0.0015–0.006

    def test_rho_below_minimum_fails(self):
        """Reinforcement below minimum should raise validation error."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=100.0)
        with pytest.raises(ValidationError):
            ShrinkageCompensatingDesign(
                slab_thickness_in=6.0,
                slab_length_ft=100.0,
                slab_width_ft=100.0,
                prism_expansion_pct=0.04,
                rho=0.0010,  # below minimum 0.0015
                concrete=concrete,
                subgrade=subgrade,
            )

    def test_prism_below_minimum_fails(self):
        """Prism expansion below 0.03% should raise validation error."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=100.0)
        with pytest.raises(ValidationError):
            ShrinkageCompensatingDesign(
                slab_thickness_in=6.0,
                slab_length_ft=100.0,
                slab_width_ft=100.0,
                prism_expansion_pct=0.02,  # below minimum
                rho=0.002,
                concrete=concrete,
                subgrade=subgrade,
            )

    def test_steel_depth_one_third(self, sc_design):
        """Reinforcement at 1/3 depth from top per ACI §9.3.3."""
        result = design_shrinkage_compensating(sc_design)
        expected = sc_design.slab_thickness_in / 3.0
        assert abs(result.reinforcement_depth_in - expected) < 1e-6

    def test_isolation_joint_reasonable(self, sc_design):
        """Joint width should be reasonable (< 3 in for typical slabs)."""
        result = design_shrinkage_compensating(sc_design)
        assert 0.1 < result.isolation_joint_width_in < 3.0

    def test_isolation_joint_matches_formula(self, sc_design):
        """Joint width matches Eq. (9-1) with computed expansion strain."""
        result = design_shrinkage_compensating(sc_design)
        expected = isolation_joint_width(
            sc_design.slab_length_ft,
            result.slab_expansion_strain,
            sc_design.expansion_at_one_end,
        )
        assert abs(result.isolation_joint_width_in - expected) < 1e-6

    def test_compressive_stress_positive(self, sc_design):
        """Estimated internal compressive stress is positive."""
        result = design_shrinkage_compensating(sc_design)
        assert result.internal_compressive_stress_psi > 0

    def test_full_compensation_thresholds_positive(self, sc_design):
        result = design_shrinkage_compensating(sc_design)
        assert result.required_prism_expansion_pct > 0
        assert result.required_member_expansion_strain > 0

    def test_typical_sc_design_meets_full_compensation(self, sc_design):
        result = design_shrinkage_compensating(sc_design)
        assert result.full_compensation_ok

    def test_max_bar_spacing(self, sc_design):
        """Max bar spacing = min(3h, 14) = min(18, 14) = 14 in."""
        result = design_shrinkage_compensating(sc_design)
        h = sc_design.slab_thickness_in
        expected = min(3 * h, 14.0)
        assert abs(result.max_bar_spacing_in - expected) < 1e-6

    def test_notes_not_empty(self, sc_design):
        result = design_shrinkage_compensating(sc_design)
        assert len(result.notes) > 0


class TestShrinkageCompensatingProperties:
    def test_member_expansion_factor_matches_appendix_anchors(self):
        assert abs(_member_expansion_factor(0.00182) - 0.908) < 1e-9
        assert abs(_member_expansion_factor(0.00241) - 0.826) < 1e-9

    def test_volume_surface_ratio_does_not_change_member_expansion_lookup(self):
        """ACI §9.4.2 uses prism expansion and reinforcement for slab expansion."""
        eps_6 = _estimate_slab_expansion_strain(0.05, 0.00241, 6.0)
        eps_3 = _estimate_slab_expansion_strain(0.05, 0.00241, 3.0)
        assert abs(eps_6 - eps_3) < 1e-12

    def test_required_prism_threshold_increases_with_higher_rho(self):
        low = _required_prism_expansion_pct(0.0015, 6.0)
        high = _required_prism_expansion_pct(0.0050, 6.0)
        assert high > low

    def test_required_member_threshold_increases_for_lower_vs_ratio(self):
        thin = _required_member_expansion_strain(0.0015, 6.0)
        thick = _required_member_expansion_strain(0.0015, 1.5)
        assert thick > thin

    def test_fig_94_stress_table_anchor_points(self):
        assert abs(_interpolate_fig_94_stress(0.04, 0.0015) - 17.0) < 1e-9
        assert abs(_interpolate_fig_94_stress(0.04, 0.0025) - 27.0) < 1e-9
        assert abs(_interpolate_fig_94_stress(0.04, 0.0050) - 49.0) < 1e-9

    def test_fig_94_stress_increases_with_expansion(self):
        low = _interpolate_fig_94_stress(0.02, 0.0025)
        high = _interpolate_fig_94_stress(0.06, 0.0025)
        assert high > low

    def test_fig_94_stress_increases_with_reinforcement(self):
        low = _interpolate_fig_94_stress(0.04, 0.0015)
        high = _interpolate_fig_94_stress(0.04, 0.0050)
        assert high > low

    def test_low_prism_design_can_fail_full_compensation(self):
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=100.0, slip_sheet=SlipSheet.TWO_POLY)
        design = ShrinkageCompensatingDesign(
            slab_thickness_in=6.0,
            slab_length_ft=120.0,
            slab_width_ft=100.0,
            prism_expansion_pct=0.03,
            rho=0.0060,
            volume_surface_ratio=1.5,
            concrete=concrete,
            subgrade=subgrade,
            expansion_at_one_end=True,
        )
        result = design_shrinkage_compensating(design)
        assert not result.full_compensation_ok

    @given(
        rho=st.floats(min_value=0.0015, max_value=0.006),
        prism=st.floats(min_value=0.03, max_value=0.10),
        L=st.floats(min_value=20.0, max_value=200.0),
    )
    @settings(max_examples=100)
    def test_higher_rho_lower_expansion(self, rho, prism, L):
        """Higher reinforcement ratio → lower slab expansion strain
        (more restraint reduces free expansion)."""
        eps_low = _estimate_slab_expansion_strain(prism, rho, 6.0)
        eps_high = _estimate_slab_expansion_strain(prism, min(rho * 1.5, 0.006), 6.0)
        assert eps_high <= eps_low

    @given(
        L=st.floats(min_value=20.0, max_value=300.0),
        eps=st.floats(min_value=0.0001, max_value=0.001),
    )
    @settings(max_examples=100)
    def test_joint_width_always_positive(self, L, eps):
        jw = isolation_joint_width(L, eps, True)
        assert jw > 0
