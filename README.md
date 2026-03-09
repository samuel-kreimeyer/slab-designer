# slab-designer

Concrete slab-on-ground design utilities and CLI built around ACI 360R-10 reference workflows.

## Status

This project is usable as an engineering prototype.

- Core library and CLI are implemented.
- The automated test suite covers the current formulas and examples.
- Several methods still rely on approximations where the source PDF could not be fully decoded.

Current high-confidence areas:

- Westergaard interior and edge stress checks
- PCA-style wheel and rack-post thickness iteration
- COE edge/joint load checks
- Post-tensioned friction and strip-force spacing balance
- Shrinkage-compensating joint-width calculations

Current limitations:

- True WRI wheel-load chart design is not implemented.
- Some Chapter 7, 9, and 11 paths use documented approximations instead of exact ACI equations.
- This should not be treated as sealed-for-issue design software without independent validation.

## Install

```bash
pip install -e .[dev]
```

## CLI

```bash
slab-designer --help
slab-designer wheel --axle 22400 --contact 25 --spacing 40 --k 200 --fr 570
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

- Replace remaining approximate equations with validated ACI-backed implementations.
- Add true WRI wheel-load support or remove the claim entirely from public docs.
- Expand user-facing documentation with worked appendix examples and engineering assumptions.
