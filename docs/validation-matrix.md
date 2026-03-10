# Validation Matrix

This document tracks the engineering basis, regression coverage, and known gaps for each major method in `slab-designer`.

## Status Labels

- `equation-based`: decoded ACI equations or direct Westergaard relationships.
- `digitized`: values interpolated from ACI figures after manual digitization.
- `fitted`: calibrated curve fit tied to a published appendix example.
- `approximate`: analytical shortcut intended to track chart behavior but not directly published as a standalone equation.

## Method Matrix

| Area | Entry point | Status | Basis | Regression coverage | Remaining gaps |
| --- | --- | --- | --- | --- | --- |
| Westergaard stress analysis | `westergaard_interior`, `westergaard_edge`, `westergaard_corner`, `westergaard_aisle`, CLI `analyze` | `equation-based` | Direct plate-on-elastic-foundation equations and decoded aisle relationship | [test_analysis.py](/home/sam/Projects/slab-designer/tests/test_analysis.py) | No major method gap; confidence depends on broader benchmark set |
| PCA wheel load thickness | `design_for_wheel_load(..., method=PCA)` | `approximate` | Westergaard interior stress with spacing-based secondary-wheel superposition to track PCA chart behavior | [test_unreinforced.py](/home/sam/Projects/slab-designer/tests/test_unreinforced.py), [test_cli.py](/home/sam/Projects/slab-designer/tests/test_cli.py) | Secondary-wheel interaction is still chart-tracking rather than a decoded published PCA equation |
| COE wheel/edge load thickness | `design_for_wheel_load(..., method=COE)` | `equation-based` | COE edge/joint procedure using Westergaard edge stress with impact and joint-transfer modifiers | [test_unreinforced.py](/home/sam/Projects/slab-designer/tests/test_unreinforced.py), [test_analysis.py](/home/sam/Projects/slab-designer/tests/test_analysis.py) | Additional published COE appendix examples would improve confidence |
| WRI wheel load thickness | `design_for_wheel_load(..., method=WRI)`, CLI `wheel --method wri` | `fitted` | Appendix A2.2 calibrated fit to WRI basic and additional wheel moment charts | [test_unreinforced.py](/home/sam/Projects/slab-designer/tests/test_unreinforced.py), [test_cli.py](/home/sam/Projects/slab-designer/tests/test_cli.py) | Still a chart-calibrated fit, not a direct digitized WRI chart lookup |
| PCA rack-post thickness | `design_for_rack_load` | `approximate` | Westergaard interior stress with spacing-based post-interaction superposition to track PCA rack charts | [test_unreinforced.py](/home/sam/Projects/slab-designer/tests/test_unreinforced.py) | Interaction model should be tightened against more published or hand-checked cases |
| Uniform/aisle loading | `design_for_uniform_load` | `equation-based` | Chapter 7 aisle-loading equation using the Rice/Hetenyi top-tension relationship | [test_analysis.py](/home/sam/Projects/slab-designer/tests/test_analysis.py), [test_unreinforced.py](/home/sam/Projects/slab-designer/tests/test_unreinforced.py) | More direct appendix-style examples would help document intended range |
| FRC elastic design | `design_frc_elastic`, CLI `frc --method elastic` | `equation-based` | Chapter 11 elastic method using Westergaard interior stress and `fb = fr * Re,3 / SF` | [test_frc.py](/home/sam/Projects/slab-designer/tests/test_frc.py), [test_cli.py](/home/sam/Projects/slab-designer/tests/test_cli.py) | Could use more published benchmark cases beyond the current Appendix 6 framing |
| FRC yield-line design | `design_frc_yield_line`, CLI `frc --method yield_line` | `equation-based` | Chapter 11 / Appendix 6 yield-line capacity equations for interior, edge, and corner loading | [test_frc.py](/home/sam/Projects/slab-designer/tests/test_frc.py) | More appendix-driven inverse checks and edge-transfer examples would tighten confidence |
| PT crack-control spacing | `design_post_tensioned`, CLI `pt` | `equation-based` | Eq. (10-1) and Eq. (10-2) strip-force balance for friction and residual precompression | [test_post_tensioned.py](/home/sam/Projects/slab-designer/tests/test_post_tensioned.py), [test_appendix_examples.py](/home/sam/Projects/slab-designer/tests/test_appendix_examples.py), [test_cli.py](/home/sam/Projects/slab-designer/tests/test_cli.py) | Additional PTI/ACI examples would improve confidence outside the Appendix A4.1 geometry |
| PT equivalent tensile stress check | `allowable_stress_with_precompression`, `PTWestergaardCheck` | `equation-based` | Allowable tensile stress increased by residual precompression | [test_post_tensioned.py](/home/sam/Projects/slab-designer/tests/test_post_tensioned.py), [test_appendix_examples.py](/home/sam/Projects/slab-designer/tests/test_appendix_examples.py) | Could be expanded into a dedicated end-to-end PT floor example |
| Shrinkage-compensating expansion and joint width | `design_shrinkage_compensating`, `isolation_joint_width` | `digitized` | Appendix 5 calibrated member-expansion lookup with digitized Fig. 9.3 and Fig. 9.4 interpolation surfaces | [test_shrinkage_compensating.py](/home/sam/Projects/slab-designer/tests/test_shrinkage_compensating.py), [test_appendix_examples.py](/home/sam/Projects/slab-designer/tests/test_appendix_examples.py) | Accuracy is bounded by chart digitization quality rather than equation decoding |

## Public Surface

| Surface | Coverage | Notes |
| --- | --- | --- |
| Top-level Python API | [test_public_api.py](/home/sam/Projects/slab-designer/tests/test_public_api.py) | Guards exported entry points and result/design types |
| CLI end-to-end workflows | [test_cli.py](/home/sam/Projects/slab-designer/tests/test_cli.py) | Covers PCA wheel, WRI wheel, FRC elastic, PT, and joint calculations |

## Before Interface Work

The core is now mostly complete. The remaining technical work before UI/API expansion is:

- Add more appendix-driven cases where ACI provides explicit numeric checkpoints.
- Expand validation around the approximate PCA interaction paths.
- Document practical input ranges and assumptions for each method.
- Decide whether the WRI implementation should remain a calibrated fit or move to a direct digitized chart lookup.
