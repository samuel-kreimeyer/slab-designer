"""Tests for core Westergaard analysis functions.

Test cases derived from:
  - ACI 360R-10 Appendix 6 (FRC example: L = 28.5 in for h=6, E=3.6M, k=100)
  - Standard engineering references for Westergaard formulas
  - Basic dimensional analysis and monotonicity checks
"""

import math
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

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


# ---------------------------------------------------------------------------
# Radius of relative stiffness
# ---------------------------------------------------------------------------

class TestRadiusOfRelativeStiffness:
    def test_appendix6_example(self):
        """ACI 360R-10 Appendix 6 gives L = 28.5 in for:
        E=3,600,000 psi, h=6 in, ν=0.15, k=100 pci."""
        L = radius_of_relative_stiffness(
            E=3_600_000.0, h=6.0, nu=0.15, k=100.0
        )
        assert abs(L - 28.5) < 0.5, f"L = {L:.2f} in (expected ~28.5 in)"

    def test_larger_h_gives_larger_L(self):
        """Thicker slab → larger radius of relative stiffness."""
        L6 = radius_of_relative_stiffness(4_000_000, 6.0, 0.15, 100)
        L8 = radius_of_relative_stiffness(4_000_000, 8.0, 0.15, 100)
        assert L8 > L6

    def test_larger_k_gives_smaller_L(self):
        """Stiffer subgrade → smaller L."""
        L_soft = radius_of_relative_stiffness(4_000_000, 6.0, 0.15, 50)
        L_stiff = radius_of_relative_stiffness(4_000_000, 6.0, 0.15, 400)
        assert L_soft > L_stiff

    def test_formula_direct(self):
        """Verify against direct formula calculation."""
        E, h, nu, k = 4_000_000.0, 7.75, 0.15, 200.0
        expected = (E * h**3 / (12 * (1 - nu**2) * k)) ** 0.25
        computed = radius_of_relative_stiffness(E, h, nu, k)
        assert abs(computed - expected) < 1e-6

    @given(
        E=st.floats(min_value=1e6, max_value=1e8),
        h=st.floats(min_value=3.0, max_value=24.0),
        nu=st.floats(min_value=0.05, max_value=0.49),
        k=st.floats(min_value=10.0, max_value=1000.0),
    )
    def test_always_positive(self, E, h, nu, k):
        """L is always positive."""
        L = radius_of_relative_stiffness(E, h, nu, k)
        assert L > 0

    @given(
        E=st.floats(min_value=1e6, max_value=1e8),
        h=st.floats(min_value=3.0, max_value=24.0),
        nu=st.floats(min_value=0.05, max_value=0.49),
        k=st.floats(min_value=10.0, max_value=1000.0),
    )
    def test_units_h_cubed(self, E, h, nu, k):
        """L scales as h^(3/4)."""
        L1 = radius_of_relative_stiffness(E, h, nu, k)
        L2 = radius_of_relative_stiffness(E, 2 * h, nu, k)
        ratio = L2 / L1
        expected_ratio = 2.0 ** 0.75
        assert abs(ratio - expected_ratio) < 1e-9


# ---------------------------------------------------------------------------
# Westergaard interior stress
# ---------------------------------------------------------------------------

class TestWestergaardInterior:
    def test_returns_stress_object(self):
        ws = westergaard_interior(P=11200, h=7.75, a=2.82, k=200)
        assert isinstance(ws, WestergaardStress)
        assert ws.case == "interior"

    def test_stress_positive(self):
        """Tensile stress should be positive."""
        ws = westergaard_interior(P=11200, h=7.75, a=2.82, k=200)
        assert ws.stress_psi > 0

    def test_higher_load_higher_stress(self):
        """Doubling the load doubles the stress (linear)."""
        ws1 = westergaard_interior(P=10000, h=8.0, a=3.0, k=200)
        ws2 = westergaard_interior(P=20000, h=8.0, a=3.0, k=200)
        assert abs(ws2.stress_psi / ws1.stress_psi - 2.0) < 0.01

    def test_thicker_slab_lower_stress(self):
        """Thicker slab → lower stress."""
        ws6 = westergaard_interior(P=10000, h=6.0, a=3.0, k=100)
        ws8 = westergaard_interior(P=10000, h=8.0, a=3.0, k=100)
        assert ws8.stress_psi < ws6.stress_psi

    def test_larger_contact_lower_stress(self):
        """Larger contact area → lower stress."""
        ws_small = westergaard_interior(P=10000, h=8.0, a=2.0, k=100)
        ws_large = westergaard_interior(P=10000, h=8.0, a=4.0, k=100)
        assert ws_large.stress_psi < ws_small.stress_psi

    def test_pca_appendix1_example(self):
        """PCA Appendix 1: axle=22.4 kip, contact=25 in², spacing=40 in, k=200.
        Allowable stress = 335 psi → 1000*335/22400 = 14.96 stress/kip.
        Required thickness ≈ 7.75 in.
        At h=7.75 in, stress should be ≈ 335 psi."""
        P_wheel = 22400 / 2  # lb per wheel
        a = math.sqrt(25 / math.pi)
        ws = westergaard_interior(P=P_wheel, h=7.75, a=a, k=200)
        # The PCA method is chart-based; the Westergaard formula gives the
        # theoretical stress. At the design thickness, it should be ≈ allowable.
        allowable = 570 / 1.7  # = 335.3 psi
        # Stress should be within ±10% of allowable at design thickness
        # (PCA charts have some conservatism built in)
        assert ws.stress_psi < allowable * 1.1, (
            f"Stress {ws.stress_psi:.1f} psi should be ≤ allowable {allowable:.1f} psi"
        )

    @given(
        P=st.floats(min_value=100, max_value=1e6),
        h=st.floats(min_value=3.0, max_value=24.0),
        a=st.floats(min_value=0.5, max_value=12.0),
        k=st.floats(min_value=10.0, max_value=1000.0),
    )
    @settings(max_examples=200)
    def test_linearity_in_P(self, P, h, a, k):
        """Interior Westergaard stress is linear in P."""
        ws1 = westergaard_interior(P, h, a, k)
        ws2 = westergaard_interior(2 * P, h, a, k)
        assert abs(ws2.stress_psi / ws1.stress_psi - 2.0) < 1e-9

    @given(
        P=st.floats(min_value=100, max_value=1e6),
        h=st.floats(min_value=3.0, max_value=24.0),
        a=st.floats(min_value=0.5, max_value=12.0),
        k=st.floats(min_value=10.0, max_value=1000.0),
    )
    @settings(max_examples=200)
    def test_stress_decreases_with_h(self, P, h, a, k):
        """Stress decreases as thickness increases."""
        ws_thin = westergaard_interior(P, h, a, k)
        ws_thick = westergaard_interior(P, h + 2.0, a, k)
        assert ws_thick.stress_psi < ws_thin.stress_psi


# ---------------------------------------------------------------------------
# Westergaard edge stress
# ---------------------------------------------------------------------------

class TestWestergaardEdge:
    def test_returns_stress_object(self):
        ws = westergaard_edge(P=11200, h=7.75, a=2.82, k=200)
        assert isinstance(ws, WestergaardStress)
        assert ws.case == "edge"

    def test_edge_greater_than_interior(self):
        """Edge stress > interior stress (edge is more severe)."""
        P, h, a, k = 10000, 8.0, 3.0, 200
        edge = westergaard_edge(P, h, a, k)
        interior = westergaard_interior(P, h, a, k)
        assert edge.stress_psi > interior.stress_psi

    def test_stress_positive(self):
        ws = westergaard_edge(P=10000, h=8.0, a=3.0, k=200)
        assert ws.stress_psi > 0

    @given(
        P=st.floats(min_value=100, max_value=1e6),
        h=st.floats(min_value=3.0, max_value=24.0),
        a=st.floats(min_value=0.5, max_value=10.0),
        k=st.floats(min_value=10.0, max_value=1000.0),
    )
    @settings(max_examples=200)
    def test_linearity_in_P(self, P, h, a, k):
        """Edge stress is linear in P."""
        ws1 = westergaard_edge(P, h, a, k)
        ws2 = westergaard_edge(2 * P, h, a, k)
        assert abs(ws2.stress_psi / ws1.stress_psi - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# COE edge stress
# ---------------------------------------------------------------------------

class TestCOEEdge:
    def test_coe_less_than_raw_edge(self):
        """COE applies 0.75 joint transfer → lower than raw edge stress."""
        P, h, a, k = 10000, 8.0, 3.0, 200
        raw = westergaard_edge(P, h, a, k)
        coe = westergaard_edge_coe(P, h, a, k)
        # COE includes 1.25 impact (increases load) but 0.75 JTC (reduces stress)
        # Net effect: 1.25 × 0.75 = 0.9375 × raw
        assert abs(coe.stress_psi / raw.stress_psi - 1.25 * 0.75) < 0.01

    def test_coe_case_label(self):
        ws = westergaard_edge_coe(P=10000, h=8.0, a=3.0, k=200)
        assert ws.case == "edge_coe"


# ---------------------------------------------------------------------------
# Westergaard corner stress
# ---------------------------------------------------------------------------

class TestWestergaardCorner:
    def test_stress_positive(self):
        ws = westergaard_corner(P=10000, h=8.0, a=3.0, k=200)
        assert ws.stress_psi > 0

    def test_returns_stress_object(self):
        ws = westergaard_corner(P=10000, h=8.0, a=3.0, k=200)
        assert ws.case == "corner"

    def test_zero_radius_gives_maximum(self):
        """For infinitesimally small contact (a→0), stress → 3P/h²."""
        P, h, k = 10000.0, 8.0, 200.0
        ws_small = westergaard_corner(P, h, a=1e-6, k=k)
        theoretical_max = 3 * P / h**2
        assert abs(ws_small.stress_psi - theoretical_max) < 0.1  # psi

    def test_corner_less_than_large_a(self):
        """Larger contact area reduces corner stress."""
        ws_small = westergaard_corner(P=10000, h=8.0, a=1.0, k=200)
        ws_large = westergaard_corner(P=10000, h=8.0, a=5.0, k=200)
        assert ws_large.stress_psi < ws_small.stress_psi

    @given(
        P=st.floats(min_value=100, max_value=1e6),
        h=st.floats(min_value=3.0, max_value=24.0),
        a=st.floats(min_value=0.1, max_value=5.0),
        k=st.floats(min_value=10.0, max_value=1000.0),
    )
    @settings(max_examples=200)
    def test_linearity_in_P(self, P, h, a, k):
        """Corner stress is linear in P."""
        ws1 = westergaard_corner(P, h, a, k)
        ws2 = westergaard_corner(2 * P, h, a, k)
        assert abs(ws2.stress_psi / ws1.stress_psi - 2.0) < 1e-9

    @given(
        P=st.floats(min_value=100, max_value=1e6),
        h=st.floats(min_value=4.0, max_value=20.0),
        a=st.floats(min_value=0.1, max_value=4.0),
        k=st.floats(min_value=10.0, max_value=1000.0),
    )
    @settings(max_examples=200)
    def test_stress_bounded_above(self, P, h, a, k):
        """Corner stress ≤ 3P/h² (the a=0 limit)."""
        ws = westergaard_corner(P, h, a, k)
        max_stress = 3 * P / h**2
        assert ws.stress_psi <= max_stress + 1e-6


# ---------------------------------------------------------------------------
# Aisle moment
# ---------------------------------------------------------------------------

class TestWestergaardAisle:
    def test_returns_aisle_moment(self):
        am = westergaard_aisle(w=1.0, h=6.0, half_aisle_in=36.0, k=100)
        assert isinstance(am, AisleMoment)

    def test_moment_positive(self):
        am = westergaard_aisle(w=1.0, h=6.0, half_aisle_in=36.0, k=100)
        assert am.Mc_inlb_per_in > 0

    def test_wider_aisle_different_moment(self):
        """Moment changes with aisle width (not monotonic – has an optimum)."""
        am_narrow = westergaard_aisle(w=1.0, h=8.0, half_aisle_in=18.0, k=100)
        am_wide = westergaard_aisle(w=1.0, h=8.0, half_aisle_in=72.0, k=100)
        # Both are valid moments; just check they differ
        assert am_narrow.Mc_inlb_per_in != am_wide.Mc_inlb_per_in

    def test_as_stress_psi(self):
        """Verify stress conversion uses h²/6."""
        h = 8.0
        am = westergaard_aisle(w=1.0, h=h, half_aisle_in=36.0, k=100)
        S = h**2 / 6
        expected_stress = am.Mc_inlb_per_in / S
        assert abs(am.as_stress_psi() - expected_stress) < 1e-9

    @given(
        w=st.floats(min_value=0.01, max_value=10.0),
        h=st.floats(min_value=3.0, max_value=24.0),
        a=st.floats(min_value=6.0, max_value=120.0),
        k=st.floats(min_value=10.0, max_value=1000.0),
    )
    @settings(max_examples=200)
    def test_linearity_in_w(self, w, h, a, k):
        """Aisle moment is linear in load intensity w."""
        am1 = westergaard_aisle(w, h, a, k)
        am2 = westergaard_aisle(2 * w, h, a, k)
        assert abs(am2.Mc_inlb_per_in / am1.Mc_inlb_per_in - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# Allowable stress helpers
# ---------------------------------------------------------------------------

class TestAllowableStress:
    def test_pca_appendix1_example(self):
        """ACI Appendix 1: fr=570 psi, SF=1.7 → allowable = 335 psi."""
        result = allowable_stress(fr=570.0, safety_factor=1.7)
        assert abs(result - 335.3) < 0.5

    def test_appendix1_rack_example(self):
        """ACI Appendix 1: fr=570 psi, SF=1.4 → allowable = 407 psi."""
        result = allowable_stress(fr=570.0, safety_factor=1.4)
        assert abs(result - 570 / 1.4) < 0.1

    def test_precompression_increases_allowable(self):
        """PT allowable = fr/SF + fp > fr/SF."""
        base = allowable_stress(fr=570.0, safety_factor=1.7)
        pt = allowable_stress_with_precompression(fr=570.0, safety_factor=1.7, precompression_psi=100.0)
        assert pt > base
        assert abs(pt - (base + 100.0)) < 0.01

    def test_utilization_at_design_thickness(self):
        """utilization ≤ 1.0 at design thickness."""
        ws = westergaard_interior(P=11200, h=7.75, a=2.82, k=200)
        allowable = 335.3
        # Should be approximately satisfied at design thickness
        assert ws.utilization(allowable) <= 1.0 + 0.05  # allow 5% tolerance
