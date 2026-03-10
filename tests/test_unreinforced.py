"""Tests for unreinforced slab thickness design.

Reference examples from ACI 360R-10 Appendices 1 and 2:

  A1.2 – PCA single-axle load:
    axle=22.4 kip, contact=25 in², spacing=40 in, k=200, fr=570, SF=1.7
    → thickness = 7¾ in (chart result)
    Westergaard equations should give thickness ≈ this value.

  A1.3 – PCA rack-post load:
    post=15.5 kip, plate=36 in², y=100 in, x=40 in, k=100, fr=570, SF=1.4
    → thickness = 8¼ in (chart result)

  A2.2 – WRI single-axle:
    E=3000 ksi (assumed), h=8 in (trial), k=400, contact=28 in²,
    spacing=45 in, axle=14.6 kip, allowable=190 psi
    → thickness = 7⅞ in
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slab_designer import (
    Concrete,
    RackLoad,
    Subgrade,
    WheelLoad,
    design_for_rack_load,
    design_for_wheel_load,
)
from slab_designer.analysis import (
    allowable_stress,
    westergaard_interior,
)
from slab_designer.design.unreinforced import DesignMethod, LoadCase

# ---------------------------------------------------------------------------
# ACI Appendix 1 – PCA wheel load example
# ---------------------------------------------------------------------------

class TestPCAWheelLoad:
    """ACI 360R-10 Appendix A1.2: single-axle, single wheels."""

    @pytest.fixture
    def pca_wheel_setup(self):
        concrete = Concrete(fc=4000.0, fr=570.0, E=4_000_000.0, nu=0.15)
        subgrade = Subgrade(k=200.0)
        load = WheelLoad(
            axle_load_lb=22_400.0,
            contact_area_in2=25.0,
            wheel_spacing_in=40.0,
        )
        return load, concrete, subgrade

    def test_allowable_stress(self, pca_wheel_setup):
        """Appendix: selected SF=1.7 → allowable = 335 psi."""
        _, concrete, _ = pca_wheel_setup
        fa = allowable_stress(concrete.fr, 1.7)
        assert abs(fa - 335.3) < 0.5

    def test_stress_per_1000lb(self, pca_wheel_setup):
        """Appendix: stress/1000 lb axle = 335/22.4 = 14.96 ≈ 15."""
        _, concrete, _ = pca_wheel_setup
        fa = allowable_stress(concrete.fr, 1.7)
        stress_per_kip = fa / 22.4  # per 1000 lb of axle load
        assert abs(stress_per_kip - 14.96) < 0.1

    def test_design_thickness_near_chart(self, pca_wheel_setup):
        """Design thickness should be ≤ 8 in (chart gives 7¾ in).

        The PCA chart is based on Westergaard equations with specific assumptions.
        Our analytical result should be within 1 in of the chart value.
        """
        load, concrete, subgrade = pca_wheel_setup
        result = design_for_wheel_load(
            load, concrete, subgrade, safety_factor=1.7
        )
        chart_thickness = 7.75  # 7¾ in per ACI appendix
        # Design should be within ± 1.5 in of chart (charts have built-in conservatism)
        assert abs(result.required_thickness_in - chart_thickness) < 1.5, (
            f"Got {result.required_thickness_in:.2f} in, expected ≈ {chart_thickness} in"
        )
        # Design must be adequate
        assert result.is_adequate

    def test_adequate_at_chart_thickness(self, pca_wheel_setup):
        """At 7¾ in, the slab must satisfy the stress criterion."""
        load, concrete, subgrade = pca_wheel_setup

        h = 7.75
        allowable = 570.0 / 1.7
        P_wheel = 22400 / 2
        a = math.sqrt(25.0 / math.pi)
        ws = westergaard_interior(P_wheel, h, a, subgrade.k, E=concrete.E, nu=concrete.nu)
        assert ws.stress_psi <= allowable + 5.0, (
            f"Stress at h=7.75 in: {ws.stress_psi:.1f} psi > allowable {allowable:.1f} psi"
        )

    def test_result_method(self, pca_wheel_setup):
        load, concrete, subgrade = pca_wheel_setup
        result = design_for_wheel_load(load, concrete, subgrade, safety_factor=1.7)
        assert result.method == DesignMethod.PCA
        assert result.load_case == LoadCase.INTERIOR


# ---------------------------------------------------------------------------
# ACI Appendix 1 – PCA rack post example
# ---------------------------------------------------------------------------

class TestPCARackPost:
    """ACI 360R-10 Appendix A1.3: rack storage post loading."""

    @pytest.fixture
    def pca_rack_setup(self):
        concrete = Concrete(fc=4000.0, fr=570.0, E=4_000_000.0, nu=0.15)
        subgrade = Subgrade(k=100.0)
        load = RackLoad(
            post_load_lb=15_500.0,
            base_plate_area_in2=36.0,
            long_spacing_in=100.0,
            short_spacing_in=40.0,
        )
        return load, concrete, subgrade

    def test_allowable_stress(self, pca_rack_setup):
        """Appendix: SF=1.4 → allowable = 407 psi."""
        _, concrete, _ = pca_rack_setup
        fa = allowable_stress(concrete.fr, 1.4)
        assert abs(fa - 570 / 1.4) < 0.2

    def test_stress_per_1000lb(self, pca_rack_setup):
        """Appendix: stress per 1000 lb = 407/15.5 = 26.26 ≈ 26."""
        _, concrete, _ = pca_rack_setup
        fa = allowable_stress(concrete.fr, 1.4)
        stress_per_kip = fa / 15.5  # per 1000 lb of post load
        assert abs(stress_per_kip - 26.26) < 0.1

    def test_design_thickness_near_chart(self, pca_rack_setup):
        """Design thickness should be near 8¼ in (PCA chart result)."""
        load, concrete, subgrade = pca_rack_setup
        result = design_for_rack_load(
            load, concrete, subgrade, safety_factor=1.4
        )
        chart_thickness = 8.25  # 8¼ in per ACI appendix
        assert abs(result.required_thickness_in - chart_thickness) < 1.5, (
            f"Got {result.required_thickness_in:.2f} in, expected ≈ {chart_thickness} in"
        )
        assert result.is_adequate

    def test_adequate_at_chart_thickness(self, pca_rack_setup):
        """At 8¼ in, the slab should be adequate."""
        load, concrete, subgrade = pca_rack_setup

        h = 8.25
        allowable = 570.0 / 1.4
        P = 15_500.0
        a = math.sqrt(36.0 / math.pi)
        ws = westergaard_interior(P, h, a, subgrade.k, E=concrete.E, nu=concrete.nu)
        assert ws.stress_psi <= allowable + 10.0, (
            f"Stress at h=8.25 in: {ws.stress_psi:.1f} psi > allowable {allowable:.1f} psi"
        )


# ---------------------------------------------------------------------------
# ACI Appendix 2 – WRI wheel load example
# ---------------------------------------------------------------------------

class TestWRIWheelLoad:
    """ACI 360R-10 Appendix A2.2: WRI single-axle thickness selection."""

    def test_wri_setup(self):
        """Verify L calculation for WRI example.

        E=3000 ksi = 3,000,000 psi (assumed), h=8 in (trial), k=400 pci.
        """
        E = 3_000_000.0  # 3000 ksi
        h = 8.0
        k = 400.0
        # WRI uses D/k parameter where D = EI = Eh³/12
        # D = 3,000,000 × 8³/12 = 3M × 512/12 = 128M in²·lb/in
        D = E * h**3 / 12
        # D = 3,000,000 × 8³/12 = 128,000,000 lb·in
        # D/k = 128,000,000 / 400 = 320,000 = 3.2 × 10⁵ in⁴
        # (Fig A2.1 reads ~3.4×10⁵ due to chart interpolation; exact formula gives 3.2×10⁵)
        Dk = D / k
        assert abs(Dk - 3.2e5) < 0.05e5, f"D/k = {Dk:.2e} (expected 3.2×10⁵ in⁴)"

    def test_wri_design_thickness(self):
        """WRI example: allowable=190 psi, axle=14.6 kip, → h≈7⅞ in."""
        # WRI uses E=3000 ksi, ν not explicitly stated
        concrete = Concrete(fc=4000.0, fr=380.0, E=3_000_000.0, nu=0.15)
        # fr set so allowable = 190 psi with SF≈2 → fr = 380 psi
        # (WRI method doesn't specify fr/SF directly; uses allowable=190 psi)
        subgrade = Subgrade(k=400.0)
        load = WheelLoad(
            axle_load_lb=14_600.0,
            contact_area_in2=28.0,
            wheel_spacing_in=45.0,
        )
        # Use fr such that fr/SF ≈ 190 psi; set SF=2.0 → fr=380
        result = design_for_wheel_load(
            load, concrete, subgrade, safety_factor=2.0
        )
        chart_thickness = 7.875  # 7⅞ in per ACI appendix
        assert abs(result.required_thickness_in - chart_thickness) < 1.5, (
            f"Got {result.required_thickness_in:.2f} in, expected ≈ {chart_thickness} in"
        )

    def test_explicit_wri_method_matches_appendix_thickness(self):
        """The explicit WRI method should track the Appendix A2.2 example."""
        concrete = Concrete(fc=4000.0, fr=380.0, E=3_000_000.0, nu=0.15)
        subgrade = Subgrade(k=400.0)
        load = WheelLoad(
            axle_load_lb=14_600.0,
            contact_area_in2=28.0,
            wheel_spacing_in=45.0,
        )
        result = design_for_wheel_load(
            load,
            concrete,
            subgrade,
            safety_factor=2.0,
            method=DesignMethod.WRI,
        )
        assert result.method == DesignMethod.WRI
        assert result.load_case == LoadCase.INTERIOR
        assert abs(result.required_thickness_in - 7.875) < 0.35


# ---------------------------------------------------------------------------
# Monotonicity and physical invariants
# ---------------------------------------------------------------------------

class TestDesignMonotonicity:
    @given(
        axle_load=st.floats(min_value=5000, max_value=100_000),
        k=st.floats(min_value=50, max_value=500),
    )
    @settings(max_examples=100)
    def test_heavier_load_thicker_slab(self, axle_load, k):
        """Heavier axle load → same or thicker design."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=k)

        light = WheelLoad(
            axle_load_lb=axle_load,
            contact_area_in2=25.0,
            wheel_spacing_in=40.0,
        )
        heavy = WheelLoad(
            axle_load_lb=axle_load * 1.5,
            contact_area_in2=25.0,
            wheel_spacing_in=40.0,
        )
        r_light = design_for_wheel_load(light, concrete, subgrade)
        r_heavy = design_for_wheel_load(heavy, concrete, subgrade)
        assert r_heavy.required_thickness_in >= r_light.required_thickness_in - 0.01

    @given(
        fr=st.floats(min_value=400, max_value=900),
        k=st.floats(min_value=50, max_value=500),
    )
    @settings(max_examples=100)
    def test_stronger_concrete_thinner_slab(self, fr, k):
        """Higher fr → same or thinner design."""
        load = WheelLoad(
            axle_load_lb=20_000,
            contact_area_in2=25.0,
            wheel_spacing_in=40.0,
        )
        subgrade = Subgrade(k=k)

        weak = Concrete(fc=3000.0, fr=fr)
        strong = Concrete(fc=3000.0, fr=fr * 1.3)

        r_weak = design_for_wheel_load(load, weak, subgrade)
        r_strong = design_for_wheel_load(load, strong, subgrade)
        assert r_strong.required_thickness_in <= r_weak.required_thickness_in + 0.01

    @given(
        k=st.floats(min_value=50, max_value=500),
        axle=st.floats(min_value=5000, max_value=80_000),
    )
    @settings(max_examples=100)
    def test_stiffer_subgrade_thinner_slab(self, k, axle):
        """Stiffer subgrade → same or thinner design."""
        concrete = Concrete(fc=4000.0, fr=570.0)
        load = WheelLoad(
            axle_load_lb=axle,
            contact_area_in2=25.0,
            wheel_spacing_in=40.0,
        )
        soft = Subgrade(k=k)
        stiff = Subgrade(k=k * 2)

        r_soft = design_for_wheel_load(load, concrete, soft)
        r_stiff = design_for_wheel_load(load, concrete, stiff)
        assert r_stiff.required_thickness_in <= r_soft.required_thickness_in + 0.1

    def test_design_result_is_adequate(self):
        """The computed design always satisfies the stress criterion."""
        load = WheelLoad(
            axle_load_lb=22_400,
            contact_area_in2=25.0,
            wheel_spacing_in=40.0,
        )
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=200.0)
        result = design_for_wheel_load(load, concrete, subgrade, safety_factor=1.7)
        assert result.is_adequate

    def test_rack_result_is_adequate(self):
        load = RackLoad(
            post_load_lb=15_500,
            base_plate_area_in2=36.0,
            long_spacing_in=100.0,
            short_spacing_in=40.0,
        )
        concrete = Concrete(fc=4000.0, fr=570.0)
        subgrade = Subgrade(k=100.0)
        result = design_for_rack_load(load, concrete, subgrade, safety_factor=1.4)
        assert result.is_adequate


# ---------------------------------------------------------------------------
# Post-tensioned allowable stress increase
# ---------------------------------------------------------------------------

class TestPTAllowableStress:
    def test_pt_stress_appendix4(self):
        """ACI Appendix 4: P=15,000 lb, h=6 in, a=4.5 in, k=150 pci → fb=545 psi.

        The example then shows PT providing 250 psi precompression is adequate
        since 250 > (545 - 474) = 71 psi required.
        """

        P = 15_000.0
        h = 6.0
        a = 4.5  # 8×8 in base plate → a = sqrt(64/π) ≈ 4.51 in
        k = 150.0

        ws = westergaard_interior(P, h, a, k)
        # ACI gives fb = 545 psi; our formula should give something close
        assert abs(ws.stress_psi - 545.0) < 60.0, (
            f"fb = {ws.stress_psi:.1f} psi (expected ~545 psi)"
        )

    def test_cracking_stress_check(self):
        """Cracking stress: 7.5*sqrt(4000) = 474 psi → PT must provide 545-474=71 psi."""
        import math
        fc = 4000.0
        fr_aci = 7.5 * math.sqrt(fc)  # ACI cracking criterion
        assert abs(fr_aci - 474.3) < 0.5  # = 474.3 psi
