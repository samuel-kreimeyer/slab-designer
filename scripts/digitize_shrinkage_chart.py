#!/usr/bin/env python3
"""Extract candidate digitization data from ACI 360R-10 Fig. 9.3 / Fig. A5.1.

This is an exploratory utility, not a production design routine.

The chart is effectively a nomograph, so the most useful first-pass dataset is:
  1. the chart bounds;
  2. the reinforcement ray angles; and
  3. candidate curve-crossing locations along each ray.

Those outputs are enough to iterate on an interpolation model without repeatedly
hand-reading the PDF. The labeled curve output is only a first-pass heuristic;
it is useful for debugging the chart geometry, not for direct design use.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIG93 = PROJECT_ROOT / (
    "docs/reference/aci-360r-10/images/"
    "image_000029_6f82283e86e909423b53d2c76ac4696efeb56a8f72fa1a706626ef8562daf6ae.png"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "digitized" / "shrinkage_chart"


@dataclass(frozen=True)
class ChartBounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class Ray:
    label: str
    angle_deg: float


@dataclass(frozen=True)
class Crossing:
    ray_label: str
    distance_px: float
    x_px: float
    y_px: float
    normal_score: int


@dataclass(frozen=True)
class LabeledCrossing:
    curve_label: str
    ray_label: str
    distance_px: float
    x_px: float
    y_px: float
    normal_score: int
    member_to_prism_ratio: float


def upscale_image(image: Image.Image, factor: int) -> Image.Image:
    return image.resize((image.width * factor, image.height * factor), Image.Resampling.NEAREST)


def detect_chart_bounds(gray: np.ndarray) -> ChartBounds:
    dark = gray < 120
    col_counts = dark.sum(axis=0)
    row_counts = dark.sum(axis=1)

    left = int(np.argmax(col_counts[: gray.shape[1] // 2]))
    right = int(np.argmax(col_counts[gray.shape[1] // 2 :]) + gray.shape[1] // 2)
    top = int(np.argmax(row_counts[: gray.shape[0] // 2]))
    bottom = int(np.argmax(row_counts[gray.shape[0] // 2 :]) + gray.shape[0] // 2)

    return ChartBounds(left=left, top=top, right=right + 1, bottom=bottom + 1)


def crop_chart(image: Image.Image, bounds: ChartBounds) -> Image.Image:
    return image.crop((bounds.left, bounds.top, bounds.right, bounds.bottom))


def detect_rays(chart_gray: np.ndarray) -> list[Ray]:
    _, binary = cv2.threshold(chart_gray, 180, 255, cv2.THRESH_BINARY_INV)
    lines = cv2.HoughLinesP(
        binary,
        rho=1,
        theta=np.pi / 180,
        threshold=120,
        minLineLength=200,
        maxLineGap=10,
    )
    if lines is None:
        return []

    candidates: list[float] = []
    for line in lines[:, 0]:
        x1, y1, x2, y2 = line
        angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
        # The reinforcement rays are the strong diagonal lines through the origin.
        if 35.0 <= angle <= 75.0:
            candidates.append(round(angle, 1))

    grouped: list[float] = []
    for angle in sorted(set(candidates), reverse=True):
        if not grouped or abs(angle - grouped[-1]) > 2.5:
            grouped.append(angle)

    labels = ["0.15%", "0.30%", "0.50%", "1.00%", "2.00%"]
    return [
        Ray(label=label, angle_deg=angle)
        for label, angle in zip(labels, grouped, strict=False)
    ]


def find_crossings(chart_gray: np.ndarray, rays: list[Ray]) -> list[Crossing]:
    dark = chart_gray < 180
    height, width = dark.shape
    origin = np.array([0.0, float(height - 1)])

    crossings: list[Crossing] = []
    for ray in rays:
        theta = math.radians(ray.angle_deg)
        direction = np.array([math.cos(theta), -math.sin(theta)])
        normal = np.array([math.sin(theta), math.cos(theta)])
        max_t = min(
            (width - 1 - origin[0]) / direction[0],
            origin[1] / max(1e-9, -direction[1]),
        )

        samples: list[tuple[float, int]] = []
        for t in np.linspace(120.0, max_t - 15.0, 900):
            p = origin + t * direction
            score = 0
            for s in np.linspace(-18.0, 18.0, 37):
                q = p + s * normal
                x = int(round(q[0]))
                y = int(round(q[1]))
                if 0 <= x < width and 0 <= y < height and dark[y, x]:
                    score += 1
            samples.append((t, score))

        peaks: list[tuple[float, int]] = []
        for i in range(1, len(samples) - 1):
            left = samples[i - 1][1]
            center = samples[i][1]
            right = samples[i + 1][1]
            if center >= left and center >= right and center >= 10:
                peaks.append(samples[i])

        selected: list[tuple[float, int]] = []
        for peak in sorted(peaks, key=lambda item: item[1], reverse=True):
            if all(abs(peak[0] - kept[0]) > 35.0 for kept in selected):
                selected.append(peak)

        for distance_px, score in sorted(selected[:6], key=lambda item: item[0]):
            point = origin + distance_px * direction
            crossings.append(
                Crossing(
                    ray_label=ray.label,
                    distance_px=round(distance_px, 2),
                    x_px=round(float(point[0]), 2),
                    y_px=round(float(point[1]), 2),
                    normal_score=int(score),
                )
            )

    return crossings


def label_crossings(chart: Image.Image, crossings: list[Crossing]) -> list[LabeledCrossing]:
    curve_labels = ["6.0", "4.5", "3.0", "1.5"]
    width = chart.width - 1
    height = chart.height - 1

    by_ray: dict[str, list[Crossing]] = {}
    for crossing in crossings:
        by_ray.setdefault(crossing.ray_label, []).append(crossing)

    labeled: list[LabeledCrossing] = []
    for ray_label, ray_crossings in by_ray.items():
        ordered = sorted(ray_crossings, key=lambda item: item.distance_px)[: len(curve_labels)]
        for curve_label, crossing in zip(curve_labels, ordered, strict=False):
            prism_pct = 0.10 * (crossing.x_px / width)
            member_pct = 0.06 * ((height - crossing.y_px) / height)
            ratio = member_pct / prism_pct if prism_pct > 0 else float("nan")
            labeled.append(
                LabeledCrossing(
                    curve_label=curve_label,
                    ray_label=ray_label,
                    distance_px=crossing.distance_px,
                    x_px=crossing.x_px,
                    y_px=crossing.y_px,
                    normal_score=crossing.normal_score,
                    member_to_prism_ratio=round(ratio, 4),
                )
            )

    return sorted(labeled, key=lambda item: (item.curve_label, item.distance_px))


def save_overlay(chart: Image.Image, rays: list[Ray], output_path: Path) -> None:
    overlay = chart.convert("RGB")
    draw = ImageDraw.Draw(overlay)
    origin = (0, chart.height - 1)
    colors = ["#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6"]

    for idx, ray in enumerate(rays):
        theta = math.radians(ray.angle_deg)
        dx = math.cos(theta)
        dy = -math.sin(theta)
        t = min((chart.width - 1) / dx, (chart.height - 1) / max(1e-9, -dy))
        end = (origin[0] + t * dx, origin[1] + t * dy)
        draw.line(
            (origin[0], origin[1], end[0], end[1]),
            fill=colors[idx % len(colors)],
            width=2,
        )
        draw.text(
            (end[0] - 80, max(0, end[1] + 10)),
            f"{ray.label} @ {ray.angle_deg:.1f}°",
            fill=colors[idx % len(colors)],
        )

    overlay.save(output_path)


def write_outputs(
    output_dir: Path,
    source_path: Path,
    bounds: ChartBounds,
    rays: list[Ray],
    crossings: list[Crossing],
    labeled_crossings: list[LabeledCrossing],
    chart: Image.Image,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    chart_path = output_dir / "fig93-chart-crop.png"
    chart.save(chart_path)
    save_overlay(chart, rays, output_dir / "fig93-rays.png")

    manifest = {
        "source": str(source_path.relative_to(PROJECT_ROOT)),
        "bounds": asdict(bounds),
        "rays": [asdict(ray) for ray in rays],
        "crossings": [asdict(crossing) for crossing in crossings],
        "labeled_crossings": [asdict(crossing) for crossing in labeled_crossings],
    }
    (output_dir / "fig93-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    with (output_dir / "fig93-crossings.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["ray_label", "distance_px", "x_px", "y_px", "normal_score"],
        )
        writer.writeheader()
        for crossing in crossings:
            writer.writerow(asdict(crossing))

    with (output_dir / "fig93-labeled-crossings.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "curve_label",
                "ray_label",
                "distance_px",
                "x_px",
                "y_px",
                "normal_score",
                "member_to_prism_ratio",
            ],
        )
        writer.writeheader()
        for crossing in labeled_crossings:
            writer.writerow(asdict(crossing))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_FIG93,
        help="Path to the extracted Fig. 9.3 image.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for diagnostics and CSV/JSON output.",
    )
    parser.add_argument(
        "--upscale",
        type=int,
        default=4,
        help="Nearest-neighbor scale factor applied before ray detection.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image = Image.open(args.source).convert("L")
    upscaled = upscale_image(image, factor=args.upscale)
    upscaled_np = np.array(upscaled)

    bounds = detect_chart_bounds(upscaled_np)
    chart = crop_chart(upscaled, bounds)
    chart_gray = np.array(chart)

    rays = detect_rays(chart_gray)
    crossings = find_crossings(chart_gray, rays)
    labeled_crossings = label_crossings(chart, crossings)
    write_outputs(
        args.output_dir,
        args.source,
        bounds,
        rays,
        crossings,
        labeled_crossings,
        chart,
    )

    print(f"Source: {args.source}")
    print(f"Chart bounds: {bounds}")
    print("Detected rays:")
    for ray in rays:
        print(f"  {ray.label:>5}  {ray.angle_deg:>5.1f} deg")
    print("Candidate crossings:")
    for crossing in crossings:
        print(
            f"  {crossing.ray_label:>5}  t={crossing.distance_px:>6.1f}  "
            f"x={crossing.x_px:>6.1f}  y={crossing.y_px:>6.1f}  "
            f"score={crossing.normal_score}"
        )
    print("Labeled crossings (heuristic):")
    for crossing in labeled_crossings:
        print(
            f"  V/SA={crossing.curve_label:>3}  rho={crossing.ray_label:>5}  "
            f"ratio={crossing.member_to_prism_ratio:>6.3f}  "
            f"x={crossing.x_px:>6.1f}  y={crossing.y_px:>6.1f}"
        )
    print(f"Outputs written to: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
