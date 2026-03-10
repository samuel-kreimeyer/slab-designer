# slab-designer

Concrete slab-on-ground design utilities and CLI built around ACI 360R-10 reference workflows.

## Status

This project is usable as an engineering prototype with most core methods now implemented.

- Core library and CLI are implemented.
- The automated test suite covers decoded equations, digitized charts, and appendix-style examples.
- The remaining risk is validation depth, not missing core method coverage.

Current high-confidence areas:

- Westergaard interior and edge stress checks
- COE edge/joint load checks
- FRC elastic and yield-line checks from Chapter 11 / Appendix 6
- Post-tensioned Eq. (10-1) / Eq. (10-2) friction and strip-force spacing balance
- Shrinkage-compensating joint-width, expansion, full-compensation, and compressive-stress lookups
- WRI wheel-load design calibrated to Appendix A2.2

Current limitations:

- Some PCA wheel and rack interaction effects remain chart-tracking approximations rather than fully decoded published equations.
- Shrinkage-compensating and WRI methods are implemented through digitized tables or calibrated fits, which matches practice but is not the same as a published closed-form equation.
- This should not be treated as sealed-for-issue design software without independent validation.

## Validation Basis

- `equation-based`: decoded ACI equations or direct Westergaard relationships.
- `digitized`: values interpolated from ACI figures after manual digitization.
- `fitted`: calibrated curve fit tied to a published appendix example.
- `approximate`: analytical shortcut intended to track chart behavior but not directly published as a standalone equation.

Method-by-method status lives in [docs/validation-matrix.md](/home/sam/Projects/slab-designer/docs/validation-matrix.md).

## Install

```bash
pip install -e .[dev]
```

## CLI

```bash
slab-designer --help
slab-designer wheel --axle 22400 --contact 25 --spacing 40 --k 200 --fr 570
slab-designer wheel --axle 14600 --contact 28 --spacing 45 --k 400 --fr 380 --sf 2.0 --method wri --e 3000000
slab-designer rack --post 15500 --plate 36 --long 100 --short 40 --k 100 --fr 570
slab-designer uniform --load 500 --aisle 10 --k 100 --fr 570
slab-designer frc --load 15000 --contact 24 --re3 55 --k 100 --fr 550
slab-designer pt --length 500 --thickness 6 --pe 26000 --k 150
slab-designer analyze --load 11200 --contact 25 --h 7.75 --k 200
```

## Development

```bash
ruff check .
mypy
pytest
```

## Roadmap

- Expand appendix-driven end-to-end validation coverage across the CLI and public API.
- Document method-by-method validation status and engineering assumptions in more detail.
- Add interface layers once the remaining validation set is broad enough to support them safely.
