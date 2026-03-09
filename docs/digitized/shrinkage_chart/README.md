# Shrinkage Chart Digitization

This directory contains exploratory outputs for `ACI 360R-10` `Fig. 9.3 / Fig. A5.1`.

Files:
- `fig93-chart-crop.png`: detected chart crop from the extracted figure image
- `fig93-rays.png`: detected reinforcement rays overlaid on the crop
- `fig93-crossings.csv`: raw candidate crossing peaks detected along each ray
- `fig93-labeled-crossings.csv`: first-pass assignment of the nearest four peaks to `V/SA = 6.0, 4.5, 3.0, 1.5`
- `fig93-manifest.json`: combined machine-readable output
- `validated_member_expansion_table.csv`: the current member-expansion interpolation table used in code

Status:
- The ray detection is stable enough to reuse.
- The raw crossing peaks are useful.
- The labeled crossing table is still heuristic and should not yet be treated as validated design data.
- The validated member-expansion table is anchored to the two explicit Appendix 5 values at `ρ = 0.182%` and `ρ = 0.241%`.

Use:
```bash
python scripts/digitize_shrinkage_chart.py
```
