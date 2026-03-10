"""Tests for post-tensioned slab design.

Reference: ACI 360R-10 Appendix 4 – Post-tensioning design examples.

These tests validate the Appendix 4 force balance directly:

  Pr [lb/ft] = μ * Wslab [lb/ft²] * L [ft] / 2
  required strip force [lb/ft] = Pr [lb/ft] + fp [psi] * h [in] * 12 [in/ft]
  tendon spacing [ft] = Pe [lb] / required strip force [lb/ft]
"""

from hypothesis import given
from hypothesis import strategies as st

from slab_designer import (
    Concrete,
    PostTensionTendon,
    Subgrade,
    design_post_tensioned,
)
from slab_designer.design.post_tensioned import (
    PostTensionedDesign,
    PTWestergaardCheck,
    recommended_residual_prestress,
)
from slab_designer.soil import SlipSheet

# ---------------------------------------------------------------------------
# Recommended residual prestress
# ---------------------------------------------------------------------------

class TestRecommendedPrestress:
    def test_residential(self):
        fp = recommended_residual_prestress(80.0, industrial=False)
        assert 50.0 <= fp <= 75.0

    def test_industrial_100ft(self):
        fp = recommended_residual_prestress(100.0, industrial=True)
        assert 75.0 <= fp <= 100.0

    def test_industrial_200ft(self):
        fp = recommended_residual_prestress(200.0, industrial=True)
        assert 100.0 <= fp <= 150.0

    def test_industrial_300ft(self):
        fp = recommended_residual_prestress(300.0, industrial=True)
        assert 150.0 <= fp <= 200.0

    def test_industrial_400ft(self):
        fp = recommended_residual_prestress(400.0, industrial=True)
        assert 200.0 <= fp <= 250.0

    def test_longer_slab_more_prestress(self):
        """Longer slab → higher recommended fp (due to friction losses)."""
        fp_100 = recommended_residual_prestress(100.0)
        fp_300 = recommended_residual_prestress(300.0)
        assert fp_300 > fp_100


# ---------------------------------------------------------------------------
# Subgrade friction force (Eq. 10-1)
# ---------------------------------------------------------------------------

class TestEq10_1:
    def test_appendix4_friction_force(self):
        """A4.1: 500 ft slab, Wslab=75 lb/ft², µ=0.5 → Pr=9,375 lb/ft."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=150.0, slip_sheet=SlipSheet.ONE_POLY, mu=0.5)
        tendon = PostTensionTendon(Pe=26_000.0)
        design = PostTensionedDesign(
            slab_length_ft=500.0,
            slab_thickness_in=6.0,
            tendon=tendon,
            concrete=concrete,
            subgrade=subgrade,
            residual_prestress_psi=250.0,
        )
        result = design_post_tensioned(design)
        # Wslab = (6/12) × 150 = 75 lb/ft², and Eq. (A4-1) uses L / 2
        expected_Pr = 0.5 * 75.0 * 500.0 / 2.0  # = 9,375 lb/ft
        assert result.validation_status == "equation-based"
        assert "Eq. (10-1) and Eq. (10-2)" in result.model_basis
        assert abs(result.Pr_lb_ft - expected_Pr) < 10.0, (
            f"Pr = {result.Pr_lb_ft:.1f} lb/ft (expected {expected_Pr:.1f})"
        )

    def test_pr_scales_with_length(self):
        """Pr is proportional to slab length (Eq. 10-1)."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=150.0, mu=0.5)
        tendon = PostTensionTendon(Pe=26_000.0)

        d1 = PostTensionedDesign(
            slab_length_ft=200.0, slab_thickness_in=6.0,
            tendon=tendon, concrete=concrete, subgrade=subgrade,
        )
        d2 = PostTensionedDesign(
            slab_length_ft=400.0, slab_thickness_in=6.0,
            tendon=tendon, concrete=concrete, subgrade=subgrade,
        )
        r1 = design_post_tensioned(d1)
        r2 = design_post_tensioned(d2)
        assert abs(r2.Pr_lb_ft / r1.Pr_lb_ft - 2.0) < 0.01

    def test_two_poly_gives_lower_pr(self):
        """Two polyethylene sheets (µ=0.30) → lower friction force."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        t_one = PostTensionedDesign(
            slab_length_ft=200.0, slab_thickness_in=6.0,
            tendon=PostTensionTendon(Pe=26_000.0),
            concrete=concrete,
            subgrade=Subgrade(k=150.0, slip_sheet=SlipSheet.ONE_POLY),
        )
        t_two = PostTensionedDesign(
            slab_length_ft=200.0, slab_thickness_in=6.0,
            tendon=PostTensionTendon(Pe=26_000.0),
            concrete=concrete,
            subgrade=Subgrade(k=150.0, slip_sheet=SlipSheet.TWO_POLY),
        )
        r_one = design_post_tensioned(t_one)
        r_two = design_post_tensioned(t_two)
        assert r_two.Pr_lb_ft < r_one.Pr_lb_ft


# ---------------------------------------------------------------------------
# Tendon spacing (Eq. 10-2)
# ---------------------------------------------------------------------------

class TestEq10_2:
    def test_spacing_matches_force_balance(self):
        """Spacing equals tendon force divided by the required strip force."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=150.0, mu=0.5)
        design = PostTensionedDesign(
            slab_length_ft=500.0,
            slab_thickness_in=6.0,
            tendon=PostTensionTendon(Pe=26_000.0),
            concrete=concrete,
            subgrade=subgrade,
            residual_prestress_psi=250.0,
        )

        result = design_post_tensioned(design)

        expected_force = result.Pr_lb_ft + 250.0 * 6.0 * 12.0
        expected_spacing_ft = 26_000.0 / expected_force

        assert abs(result.required_force_lb_ft - expected_force) < 1e-6
        assert abs(result.tendon_spacing_ft - expected_spacing_ft) < 1e-9

    def test_appendix4_spacing_example(self):
        """A4.1: 26 kip tendon, fp=250 psi, h=6 in, Pr=9375 lb/ft → 0.95 ft."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=150.0, slip_sheet=SlipSheet.ONE_POLY, mu=0.5)
        design = PostTensionedDesign(
            slab_length_ft=500.0,
            slab_thickness_in=6.0,
            tendon=PostTensionTendon(Pe=26_000.0),
            concrete=concrete,
            subgrade=subgrade,
            residual_prestress_psi=250.0,
        )

        result = design_post_tensioned(design)
        assert abs(result.tendon_spacing_ft - 0.95) < 0.01
        assert abs(result.tendon_spacing_in - 11.4) < 0.2

    def test_larger_Pe_wider_spacing(self):
        """Stronger tendons → wider allowable spacing."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=150.0, mu=0.5)

        d_small = PostTensionedDesign(
            slab_length_ft=100.0, slab_thickness_in=6.0,
            tendon=PostTensionTendon(Pe=20_000.0),
            concrete=concrete, subgrade=subgrade,
        )
        d_large = PostTensionedDesign(
            slab_length_ft=100.0, slab_thickness_in=6.0,
            tendon=PostTensionTendon(Pe=30_000.0),
            concrete=concrete, subgrade=subgrade,
        )
        r_small = design_post_tensioned(d_small)
        r_large = design_post_tensioned(d_large)
        assert r_large.tendon_spacing_ft > r_small.tendon_spacing_ft

    def test_higher_fp_closer_spacing(self):
        """Higher residual prestress requirement → closer tendon spacing."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=150.0, mu=0.5)
        tendon = PostTensionTendon(Pe=26_000.0)

        d_low = PostTensionedDesign(
            slab_length_ft=100.0, slab_thickness_in=6.0,
            tendon=tendon, concrete=concrete, subgrade=subgrade,
            residual_prestress_psi=75.0,
        )
        d_high = PostTensionedDesign(
            slab_length_ft=100.0, slab_thickness_in=6.0,
            tendon=tendon, concrete=concrete, subgrade=subgrade,
            residual_prestress_psi=200.0,
        )
        r_low = design_post_tensioned(d_low)
        r_high = design_post_tensioned(d_high)
        assert r_high.tendon_spacing_ft < r_low.tendon_spacing_ft

    def test_spacing_positive(self):
        """Tendon spacing is always positive."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=150.0, mu=0.5)
        design = PostTensionedDesign(
            slab_length_ft=200.0, slab_thickness_in=6.0,
            tendon=PostTensionTendon(Pe=26_000.0),
            concrete=concrete, subgrade=subgrade,
        )
        result = design_post_tensioned(design)
        assert result.tendon_spacing_ft > 0
        assert result.tendon_spacing_in > 0

    def test_ft_in_consistent(self):
        """Spacing in ft and in should be consistent (×12)."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=150.0, mu=0.5)
        design = PostTensionedDesign(
            slab_length_ft=200.0, slab_thickness_in=6.0,
            tendon=PostTensionTendon(Pe=26_000.0),
            concrete=concrete, subgrade=subgrade,
        )
        result = design_post_tensioned(design)
        assert abs(result.tendon_spacing_in - result.tendon_spacing_ft * 12.0) < 1e-6

    def test_net_precompression_matches_design_fp(self):
        """Residual precompression property should report the design fp."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=150.0, mu=0.5)
        design = PostTensionedDesign(
            slab_length_ft=200.0,
            slab_thickness_in=6.0,
            tendon=PostTensionTendon(Pe=26_000.0),
            concrete=concrete,
            subgrade=subgrade,
            residual_prestress_psi=175.0,
        )

        result = design_post_tensioned(design)
        assert result.net_precompression_psi == 175.0

    def test_gross_precompression_exceeds_residual_when_friction_exists(self):
        """Gross strip compression includes both residual prestress and friction demand."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=150.0, mu=0.5)
        design = PostTensionedDesign(
            slab_length_ft=200.0,
            slab_thickness_in=6.0,
            tendon=PostTensionTendon(Pe=26_000.0),
            concrete=concrete,
            subgrade=subgrade,
            residual_prestress_psi=125.0,
        )

        result = design_post_tensioned(design)
        assert result.gross_precompression_psi > result.net_precompression_psi


# ---------------------------------------------------------------------------
# PT Westergaard check
# ---------------------------------------------------------------------------

class TestPTWestergaardCheck:
    def test_appendix4_stress_check(self):
        """A4.2: P=15,000 lb, h=6 in, k=150, a=4.5 in → fb≈545 psi.
        With fp=250 psi and fr=474 psi, PT is adequate (fb < fr + fp)."""
        check = PTWestergaardCheck(
            h_in=6.0,
            P_lb=15_000.0,
            a_in=4.5,
            k_pci=150.0,
            E_psi=4_000_000.0,
            nu=0.15,
            fr_psi=474.3,   # 7.5*sqrt(4000)
            safety_factor=1.0,  # just checking stress vs capacity
            fp_psi=250.0,
        )
        # fb ≈ 545 psi, allowable = 474.3 + 250 = 724.3 psi → adequate
        assert check.is_adequate, (
            f"fb = {check.fb_psi:.1f} psi, allowable = {check.allowable_psi:.1f} psi"
        )

    def test_without_pt_inadequate(self):
        """Without PT (fp=0), the slab would be inadequate at h=6 in."""
        check_no_pt = PTWestergaardCheck(
            h_in=6.0,
            P_lb=15_000.0,
            a_in=4.5,
            k_pci=150.0,
            E_psi=4_000_000.0,
            nu=0.15,
            fr_psi=474.3,
            safety_factor=1.0,
            fp_psi=0.0,
        )
        # fb ≈ 545 > fr = 474 → inadequate without PT
        assert not check_no_pt.is_adequate

    @given(
        fp=st.floats(min_value=0, max_value=500),
    )
    def test_more_pt_improves_check(self, fp):
        """More PT precompression → always improves utilization."""
        check = PTWestergaardCheck(
            h_in=6.0, P_lb=15_000.0, a_in=4.5, k_pci=150.0,
            E_psi=4_000_000.0, nu=0.15, fr_psi=474.3,
            safety_factor=1.0, fp_psi=fp,
        )
        check_more = PTWestergaardCheck(
            h_in=6.0, P_lb=15_000.0, a_in=4.5, k_pci=150.0,
            E_psi=4_000_000.0, nu=0.15, fr_psi=474.3,
            safety_factor=1.0, fp_psi=fp + 50.0,
        )
        assert check_more.utilization < check.utilization
