# ruff: noqa: E501
"""Minimal web interface for slab_designer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from slab_designer import (
    Concrete,
    FiberProperties,
    PostTensionedDesign,
    PostTensionTendon,
    ShrinkageCompensatingDesign,
    Subgrade,
    WheelLoad,
    design_for_rack_load,
    design_for_uniform_load,
    design_for_wheel_load,
    design_frc_elastic,
    design_frc_yield_line,
    design_post_tensioned,
    design_shrinkage_compensating,
)
from slab_designer.design.frc import YieldLineCase
from slab_designer.design.unreinforced import DesignMethod
from slab_designer.loads import RackLoad, UniformLoad
from slab_designer.soil import SlipSheet


class WheelRequest(BaseModel):
    axle_load_lb: float
    contact_area_in2: float
    wheel_spacing_in: float = 40.0
    k: float
    fr: float = 570.0
    fc: float = 4000.0
    sf: float = 1.7
    E: float = 4_000_000.0
    nu: float = 0.15
    method: str = "pca"


class RackRequest(BaseModel):
    post_load_lb: float
    base_plate_area_in2: float
    long_spacing_in: float = 100.0
    short_spacing_in: float = 40.0
    k: float
    fr: float = 570.0
    fc: float = 4000.0
    sf: float = 1.4
    E: float = 4_000_000.0
    nu: float = 0.15


class UniformRequest(BaseModel):
    intensity_psf: float
    aisle_width_ft: float
    k: float
    fr: float = 570.0
    fc: float = 4000.0
    sf: float = 1.7
    E: float = 4_000_000.0
    nu: float = 0.15


class FRCRequest(BaseModel):
    load_lb: float
    contact_area_in2: float
    k: float
    re3: float
    fr: float = 550.0
    fc: float = 4000.0
    sf: float = 1.5
    E: float = 4_000_000.0
    nu: float = 0.15
    method: str = "elastic"
    case: str = "interior"
    h_in: float | None = None
    joint_transfer: float = 0.0
    additional_moment_inlb_per_in: float = 0.0


class PTRequest(BaseModel):
    slab_length_ft: float
    slab_thickness_in: float
    Pe: float
    k: float = 150.0
    fr: float = 570.0
    fc: float = 4000.0
    fp: float | None = None
    mu: float = 0.5
    slip_sheet: str = "none"
    industrial: bool = True


class ShrinkageRequest(BaseModel):
    slab_thickness_in: float
    slab_length_ft: float
    slab_width_ft: float
    prism_expansion_pct: float
    rho: float
    volume_surface_ratio: float = 6.0
    fc: float = 4000.0
    fr: float = 570.0
    k: float = 100.0
    slip_sheet: str = "two_poly"
    expansion_at_one_end: bool = True


def _concrete(fc: float, fr: float, E: float, nu: float) -> Concrete:
    return Concrete(fc=fc, fr=fr, E=E, nu=nu)


def _subgrade(k: float, slip_sheet: str = "none", mu: float | None = None) -> Subgrade:
    sheet = SlipSheet(slip_sheet)
    return Subgrade(k=k, mu=mu, slip_sheet=sheet)


def _metric(label: str, value: str) -> dict[str, str]:
    return {"label": label, "value": value}


def _serialize_design_result(result: Any, title: str) -> JSONResponse:
    return JSONResponse(
        {
            "title": title,
            "validation_status": result.validation_status,
            "model_basis": result.model_basis,
            "notes": result.notes,
            "metrics": [
                _metric("Method", result.method.value),
                _metric("Load case", result.load_case.value),
                _metric("Required thickness", f"{result.required_thickness_in:.2f} in"),
                _metric("Rounded thickness", f"{result.required_thickness_rounded_in:.2f} in"),
                _metric("Computed stress", f"{result.computed_stress_psi:.1f} psi"),
                _metric("Allowable stress", f"{result.allowable_stress_psi:.1f} psi"),
                _metric("Utilization", f"{result.utilization:.3f}"),
                _metric("Radius L", f"{result.L_in:.2f} in"),
            ],
        }
    )


def _serialize_frc_result(result: Any) -> JSONResponse:
    metrics = [
        _metric("Method", result.method),
        _metric("Case", str(result.case)),
        _metric("Re,3", f"{result.re3:.1f} %"),
        _metric("Thickness", f"{result.h_in:.2f} in"),
    ]
    if result.M0_inlb_per_in is not None:
        metrics.append(_metric("M0", f"{result.M0_inlb_per_in:.0f} in-lb/in"))
    if result.P_allowable_lb is not None:
        metrics.append(_metric("Allowable load", f"{result.P_allowable_lb:.0f} lb"))
    if result.allowable_stress_psi is not None:
        metrics.append(_metric("Allowable stress", f"{result.allowable_stress_psi:.1f} psi"))
    return JSONResponse(
        {
            "title": "FRC Slab Design",
            "validation_status": result.validation_status,
            "model_basis": result.model_basis,
            "notes": result.notes,
            "metrics": metrics,
        }
    )


def _serialize_pt_result(result: Any) -> JSONResponse:
    return JSONResponse(
        {
            "title": "Post-Tensioned Slab Design",
            "validation_status": result.validation_status,
            "model_basis": result.model_basis,
            "notes": result.notes,
            "metrics": [
                _metric("Residual prestress", f"{result.fp_psi:.0f} psi"),
                _metric("Friction force", f"{result.Pr_lb_ft:.0f} lb/ft"),
                _metric("Required strip force", f"{result.required_force_lb_ft:.0f} lb/ft"),
                _metric("Tendon spacing", f"{result.tendon_spacing_ft:.3f} ft"),
                _metric("Tendon spacing", f"{result.tendon_spacing_in:.1f} in"),
                _metric("Radius L", f"{result.L_in:.2f} in"),
            ],
        }
    )


def _serialize_shrinkage_result(result: Any) -> JSONResponse:
    return JSONResponse(
        {
            "title": "Shrinkage-Compensating Design",
            "validation_status": result.validation_status,
            "model_basis": result.model_basis,
            "notes": result.notes,
            "metrics": [
                _metric("Prism expansion", f"{result.design.prism_expansion_pct:.3f} %"),
                _metric("Reinforcement ratio", f"{result.design.rho:.4f}"),
                _metric("Slab expansion strain", f"{result.slab_expansion_strain:.5f}"),
                _metric(
                    "Required prism threshold",
                    f"{result.required_prism_expansion_pct:.4f} %",
                ),
                _metric(
                    "Required member threshold",
                    f"{result.required_member_expansion_strain:.5f}",
                ),
                _metric(
                    "Compressive stress",
                    f"{result.internal_compressive_stress_psi:.0f} psi",
                ),
                _metric(
                    "Isolation joint width",
                    f"{result.isolation_joint_width_in:.3f} in",
                ),
                _metric(
                    "Full compensation",
                    "OK" if result.full_compensation_ok else "NG",
                ),
            ],
        }
    )


def _error_response(exc: Exception) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=400)


async def homepage(_: Request) -> HTMLResponse:
    return HTMLResponse(_HTML)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def wheel_api(request: Request) -> JSONResponse:
    try:
        payload = WheelRequest.model_validate(await request.json())
        result = design_for_wheel_load(
            WheelLoad(
                axle_load_lb=payload.axle_load_lb,
                contact_area_in2=payload.contact_area_in2,
                wheel_spacing_in=payload.wheel_spacing_in,
            ),
            _concrete(payload.fc, payload.fr, payload.E, payload.nu),
            _subgrade(payload.k),
            safety_factor=payload.sf,
            method=DesignMethod(payload.method.upper()),
        )
        return _serialize_design_result(result, "Wheel Load Design")
    except Exception as exc:  # pragma: no cover - exercised by integration tests
        return _error_response(exc)


async def rack_api(request: Request) -> JSONResponse:
    try:
        payload = RackRequest.model_validate(await request.json())
        result = design_for_rack_load(
            RackLoad(
                post_load_lb=payload.post_load_lb,
                base_plate_area_in2=payload.base_plate_area_in2,
                long_spacing_in=payload.long_spacing_in,
                short_spacing_in=payload.short_spacing_in,
            ),
            _concrete(payload.fc, payload.fr, payload.E, payload.nu),
            _subgrade(payload.k),
            safety_factor=payload.sf,
        )
        return _serialize_design_result(result, "Rack Post Design")
    except Exception as exc:  # pragma: no cover - exercised by integration tests
        return _error_response(exc)


async def uniform_api(request: Request) -> JSONResponse:
    try:
        payload = UniformRequest.model_validate(await request.json())
        result = design_for_uniform_load(
            UniformLoad(
                intensity_psf=payload.intensity_psf,
                aisle_width_ft=payload.aisle_width_ft,
            ),
            _concrete(payload.fc, payload.fr, payload.E, payload.nu),
            _subgrade(payload.k),
            safety_factor=payload.sf,
        )
        return _serialize_design_result(result, "Uniform Load Design")
    except Exception as exc:  # pragma: no cover - exercised by integration tests
        return _error_response(exc)


async def frc_api(request: Request) -> JSONResponse:
    try:
        payload = FRCRequest.model_validate(await request.json())
        concrete = _concrete(payload.fc, payload.fr, payload.E, payload.nu)
        subgrade = _subgrade(payload.k)
        fibers = FiberProperties(re3=payload.re3)
        if payload.method == "yield_line":
            if payload.h_in is None:
                raise ValueError("Yield-line checks require slab thickness h_in.")
            result = design_frc_yield_line(
                load_lb=payload.load_lb,
                contact_area_in2=payload.contact_area_in2,
                h_in=payload.h_in,
                fibers=fibers,
                concrete=concrete,
                subgrade=subgrade,
                safety_factor=payload.sf,
                case=YieldLineCase(payload.case),
                joint_transfer=payload.joint_transfer,
                additional_moment_inlb_per_in=payload.additional_moment_inlb_per_in,
            )
        else:
            result = design_frc_elastic(
                load_lb=payload.load_lb,
                contact_area_in2=payload.contact_area_in2,
                fibers=fibers,
                concrete=concrete,
                subgrade=subgrade,
                safety_factor=payload.sf,
            )
        return _serialize_frc_result(result)
    except Exception as exc:  # pragma: no cover - exercised by integration tests
        return _error_response(exc)


async def pt_api(request: Request) -> JSONResponse:
    try:
        payload = PTRequest.model_validate(await request.json())
        result = design_post_tensioned(
            PostTensionedDesign(
                slab_length_ft=payload.slab_length_ft,
                slab_thickness_in=payload.slab_thickness_in,
                tendon=PostTensionTendon(Pe=payload.Pe),
                concrete=_concrete(payload.fc, payload.fr, 4_000_000.0, 0.15),
                subgrade=_subgrade(payload.k, payload.slip_sheet, payload.mu),
                residual_prestress_psi=payload.fp,
                industrial=payload.industrial,
            )
        )
        return _serialize_pt_result(result)
    except Exception as exc:  # pragma: no cover - exercised by integration tests
        return _error_response(exc)


async def shrinkage_api(request: Request) -> JSONResponse:
    try:
        payload = ShrinkageRequest.model_validate(await request.json())
        result = design_shrinkage_compensating(
            ShrinkageCompensatingDesign(
                slab_thickness_in=payload.slab_thickness_in,
                slab_length_ft=payload.slab_length_ft,
                slab_width_ft=payload.slab_width_ft,
                prism_expansion_pct=payload.prism_expansion_pct,
                rho=payload.rho,
                volume_surface_ratio=payload.volume_surface_ratio,
                concrete=Concrete(fc=payload.fc, fr=payload.fr),
                subgrade=_subgrade(payload.k, payload.slip_sheet),
                expansion_at_one_end=payload.expansion_at_one_end,
            )
        )
        return _serialize_shrinkage_result(result)
    except Exception as exc:  # pragma: no cover - exercised by integration tests
        return _error_response(exc)


def create_app() -> Starlette:
    routes = [
        Route("/", homepage),
        Route("/health", health),
        Route("/api/wheel", wheel_api, methods=["POST"]),
        Route("/api/rack", rack_api, methods=["POST"]),
        Route("/api/uniform", uniform_api, methods=["POST"]),
        Route("/api/frc", frc_api, methods=["POST"]),
        Route("/api/pt", pt_api, methods=["POST"]),
        Route("/api/shrinkage", shrinkage_api, methods=["POST"]),
    ]
    return Starlette(debug=False, routes=routes)


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("slab_designer.web.app:app", host="127.0.0.1", port=8000, reload=False)


_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>slab-designer web</title>
  <style>
    :root {
      --ink: #10243e;
      --muted: #5b6d7f;
      --paper: #f6f1e8;
      --panel: rgba(255, 252, 246, 0.88);
      --line: rgba(16, 36, 62, 0.14);
      --accent: #c55f39;
      --accent-soft: #f0c9bb;
      --ok: #1f7a57;
      --warn: #a96018;
      --shadow: 0 16px 50px rgba(16, 36, 62, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 20% 20%, rgba(197, 95, 57, 0.16), transparent 32%),
        radial-gradient(circle at 80% 0%, rgba(16, 36, 62, 0.12), transparent 28%),
        linear-gradient(180deg, #f8f3eb 0%, #f2ede3 100%);
      min-height: 100vh;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background-image:
        linear-gradient(rgba(16, 36, 62, 0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(16, 36, 62, 0.03) 1px, transparent 1px);
      background-size: 36px 36px;
      pointer-events: none;
    }
    .shell {
      position: relative;
      max-width: 1320px;
      margin: 0 auto;
      padding: 32px 20px 64px;
    }
    .hero {
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 20px;
      margin-bottom: 28px;
    }
    .hero-panel, .meta-panel, .tool, .result {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
    }
    .hero-panel {
      padding: 28px;
    }
    .hero-kicker {
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 12px;
      color: var(--accent);
      margin-bottom: 10px;
    }
    h1 {
      margin: 0 0 12px;
      font-size: clamp(2.6rem, 5vw, 4.5rem);
      line-height: 0.95;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
      font-weight: 700;
    }
    .hero p, .meta-panel p {
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }
    .meta-panel {
      padding: 24px;
      display: grid;
      align-content: space-between;
      gap: 16px;
    }
    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }
    .meta-chip {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px 14px;
      background: rgba(255, 255, 255, 0.55);
    }
    .meta-chip strong {
      display: block;
      margin-bottom: 4px;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .workspace {
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 22px;
    }
    .tool-stack {
      display: grid;
      gap: 14px;
      align-content: start;
    }
    .tab-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 8px;
      background: rgba(255, 252, 246, 0.72);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
    }
    .tab-button {
      margin: 0;
      padding: 10px 14px;
      border: 1px solid transparent;
      border-radius: 14px;
      background: transparent;
      color: var(--muted);
      box-shadow: none;
    }
    .tab-button:hover {
      transform: none;
      background: rgba(197, 95, 57, 0.08);
    }
    .tab-button.active {
      background: linear-gradient(135deg, var(--ink), #214a73);
      color: white;
      border-color: rgba(255, 255, 255, 0.2);
      box-shadow: 0 12px 24px rgba(16, 36, 62, 0.14);
    }
    .tool {
      padding: 22px;
      animation: rise 0.35s ease;
      display: none;
    }
    .tool.active {
      display: block;
    }
    .tool-header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      margin-bottom: 16px;
    }
    .tool-header h2 {
      margin: 0;
      font-size: 1.3rem;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(197, 95, 57, 0.12);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    label {
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: var(--muted);
    }
    input, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 11px 12px;
      font: inherit;
      color: var(--ink);
      background: rgba(255, 255, 255, 0.78);
    }
    .checkline {
      display: flex;
      gap: 10px;
      align-items: center;
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .checkline input {
      width: auto;
    }
    button {
      margin-top: 16px;
      border: none;
      border-radius: 16px;
      padding: 12px 16px;
      background: linear-gradient(135deg, var(--ink), #214a73);
      color: white;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      transition: transform 0.16s ease, box-shadow 0.16s ease;
      box-shadow: 0 12px 24px rgba(16, 36, 62, 0.18);
    }
    button:hover {
      transform: translateY(-1px);
    }
    .result {
      position: sticky;
      top: 24px;
      padding: 24px;
      min-height: 420px;
      animation: rise 0.35s ease;
    }
    .result h2 {
      margin: 0 0 8px;
      font-size: 1.45rem;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
    }
    .result-copy {
      color: var(--muted);
      margin-bottom: 18px;
      line-height: 1.6;
    }
    .status-line {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 14px;
    }
    .status-chip {
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.74);
    }
    .status-chip.ok { color: var(--ok); }
    .status-chip.warn { color: var(--warn); }
    .metric-list, .note-list {
      list-style: none;
      padding: 0;
      margin: 0;
    }
    .metric-list li {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      padding: 11px 0;
      border-bottom: 1px solid var(--line);
    }
    .metric-list span:first-child {
      color: var(--muted);
    }
    .basis {
      margin: 14px 0 18px;
      padding: 14px;
      border-radius: 16px;
      background: rgba(197, 95, 57, 0.08);
      color: var(--ink);
      line-height: 1.5;
    }
    .note-list li {
      padding: 9px 0;
      color: var(--muted);
      border-bottom: 1px dashed rgba(16, 36, 62, 0.08);
    }
    .empty {
      display: grid;
      place-items: center;
      min-height: 300px;
      text-align: center;
      color: var(--muted);
    }
    @keyframes rise {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @media (max-width: 1040px) {
      .hero, .workspace {
        grid-template-columns: 1fr;
      }
      .result {
        position: static;
      }
    }
    @media (max-width: 640px) {
      .grid, .meta-grid {
        grid-template-columns: 1fr;
      }
      h1 {
        font-size: 2.6rem;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="hero-panel">
        <div class="hero-kicker">ACI 360R-10 workflows</div>
        <h1>Slab design without the spreadsheet fog.</h1>
        <p>
          Start with the core methods that already exist in the library. The interface shows
          the result, the validation basis, and the engineering notes together so the method
          status stays visible instead of disappearing behind a polished form.
        </p>
      </div>
      <aside class="meta-panel">
        <p>
          This interface is deliberately thin. It is a direct shell around the current
          computational core, not a second implementation.
        </p>
        <div class="meta-grid">
          <div class="meta-chip"><strong>Ready</strong>Wheel, rack, uniform, FRC, PT, shrinkage</div>
          <div class="meta-chip"><strong>Shows</strong>Validation status and model basis</div>
          <div class="meta-chip"><strong>Surface</strong>JSON endpoints plus one-page UI</div>
          <div class="meta-chip"><strong>Default port</strong>127.0.0.1:8000</div>
        </div>
      </aside>
    </section>

    <section class="workspace">
      <div class="tool-stack">
        <div class="tab-bar" role="tablist" aria-label="Design workflows">
          <button class="tab-button active" type="button" data-tab-target="wheel">Wheel</button>
          <button class="tab-button" type="button" data-tab-target="rack">Rack</button>
          <button class="tab-button" type="button" data-tab-target="uniform">Uniform</button>
          <button class="tab-button" type="button" data-tab-target="frc">FRC</button>
          <button class="tab-button" type="button" data-tab-target="pt">PT</button>
          <button class="tab-button" type="button" data-tab-target="shrinkage">Shrinkage</button>
        </div>
        <form class="tool active" data-tab-panel="wheel" data-endpoint="/api/wheel">
          <div class="tool-header">
            <h2>Wheel Load</h2>
            <span class="badge">PCA / WRI / COE</span>
          </div>
          <div class="grid">
            <label>Axle load (lb)<input name="axle_load_lb" type="number" value="22400" step="100"></label>
            <label>Contact area (in2)<input name="contact_area_in2" type="number" value="25" step="0.1"></label>
            <label>Wheel spacing (in)<input name="wheel_spacing_in" type="number" value="40" step="0.1"></label>
            <label>Subgrade k (pci)<input name="k" type="number" value="200" step="1"></label>
            <label>Modulus of rupture fr (psi)<input name="fr" type="number" value="570" step="1"></label>
            <label>Safety factor<input name="sf" type="number" value="1.7" step="0.1"></label>
            <label>Elastic modulus E (psi)<input name="E" type="number" value="4000000" step="1000"></label>
            <label>Poisson's ratio<input name="nu" type="number" value="0.15" step="0.01"></label>
            <label>Method
              <select name="method">
                <option value="pca">PCA</option>
                <option value="wri">WRI</option>
                <option value="coe">COE</option>
              </select>
            </label>
          </div>
          <button type="submit">Run wheel design</button>
        </form>

        <form class="tool" data-tab-panel="rack" data-endpoint="/api/rack">
          <div class="tool-header">
            <h2>Rack Post</h2>
            <span class="badge">PCA</span>
          </div>
          <div class="grid">
            <label>Post load (lb)<input name="post_load_lb" type="number" value="15500" step="100"></label>
            <label>Base plate area (in2)<input name="base_plate_area_in2" type="number" value="36" step="0.1"></label>
            <label>Long spacing (in)<input name="long_spacing_in" type="number" value="100" step="1"></label>
            <label>Short spacing (in)<input name="short_spacing_in" type="number" value="40" step="1"></label>
            <label>Subgrade k (pci)<input name="k" type="number" value="100" step="1"></label>
            <label>Modulus of rupture fr (psi)<input name="fr" type="number" value="570" step="1"></label>
          </div>
          <button type="submit">Run rack design</button>
        </form>

        <form class="tool" data-tab-panel="uniform" data-endpoint="/api/uniform">
          <div class="tool-header">
            <h2>Uniform / Aisle</h2>
            <span class="badge">Chapter 7</span>
          </div>
          <div class="grid">
            <label>Uniform load (psf)<input name="intensity_psf" type="number" value="500" step="10"></label>
            <label>Aisle width (ft)<input name="aisle_width_ft" type="number" value="10" step="0.1"></label>
            <label>Subgrade k (pci)<input name="k" type="number" value="100" step="1"></label>
            <label>Modulus of rupture fr (psi)<input name="fr" type="number" value="570" step="1"></label>
          </div>
          <button type="submit">Run uniform design</button>
        </form>

        <form class="tool" data-tab-panel="frc" data-endpoint="/api/frc">
          <div class="tool-header">
            <h2>Fiber-Reinforced Concrete</h2>
            <span class="badge">Elastic / yield-line</span>
          </div>
          <div class="grid">
            <label>Load (lb)<input name="load_lb" type="number" value="15000" step="100"></label>
            <label>Contact area (in2)<input name="contact_area_in2" type="number" value="24" step="0.1"></label>
            <label>Subgrade k (pci)<input name="k" type="number" value="100" step="1"></label>
            <label>Re,3 (%)<input name="re3" type="number" value="55" step="0.1"></label>
            <label>Modulus of rupture fr (psi)<input name="fr" type="number" value="550" step="1"></label>
            <label>Method
              <select name="method">
                <option value="elastic">elastic</option>
                <option value="yield_line">yield_line</option>
              </select>
            </label>
            <label>Case
              <select name="case">
                <option value="interior">interior</option>
                <option value="edge">edge</option>
                <option value="corner">corner</option>
              </select>
            </label>
            <label>Thickness h (in)<input name="h_in" type="number" value="6" step="0.1"></label>
            <label>Joint transfer<input name="joint_transfer" type="number" value="0.2" step="0.05"></label>
            <label>Shrinkage moment (in-lb/in)<input name="additional_moment_inlb_per_in" type="number" value="1200" step="50"></label>
          </div>
          <button type="submit">Run FRC design</button>
        </form>

        <form class="tool" data-tab-panel="pt" data-endpoint="/api/pt">
          <div class="tool-header">
            <h2>Post-Tensioned</h2>
            <span class="badge">Eq. 10-1 / 10-2</span>
          </div>
          <div class="grid">
            <label>Slab length (ft)<input name="slab_length_ft" type="number" value="500" step="1"></label>
            <label>Thickness (in)<input name="slab_thickness_in" type="number" value="6" step="0.1"></label>
            <label>Tendon force Pe (lb)<input name="Pe" type="number" value="26000" step="100"></label>
            <label>Subgrade k (pci)<input name="k" type="number" value="150" step="1"></label>
            <label>Residual prestress fp (psi)<input name="fp" type="number" value="250" step="1"></label>
            <label>Friction mu<input name="mu" type="number" value="0.5" step="0.05"></label>
            <label>Slip sheet
              <select name="slip_sheet">
                <option value="none">none</option>
                <option value="one_poly">one_poly</option>
                <option value="two_poly">two_poly</option>
              </select>
            </label>
          </div>
          <label class="checkline"><input name="industrial" type="checkbox" checked>Industrial floor guidance</label>
          <button type="submit">Run PT design</button>
        </form>

        <form class="tool" data-tab-panel="shrinkage" data-endpoint="/api/shrinkage">
          <div class="tool-header">
            <h2>Shrinkage-Compensating</h2>
            <span class="badge">Digitized charts</span>
          </div>
          <div class="grid">
            <label>Thickness (in)<input name="slab_thickness_in" type="number" value="6" step="0.1"></label>
            <label>Length (ft)<input name="slab_length_ft" type="number" value="100" step="1"></label>
            <label>Width (ft)<input name="slab_width_ft" type="number" value="12" step="1"></label>
            <label>Prism expansion (%)<input name="prism_expansion_pct" type="number" value="0.05" step="0.001"></label>
            <label>Reinforcement ratio rho<input name="rho" type="number" value="0.00241" step="0.00001"></label>
            <label>V/S ratio<input name="volume_surface_ratio" type="number" value="6.0" step="0.1"></label>
            <label>Subgrade k (pci)<input name="k" type="number" value="100" step="1"></label>
            <label>Slip sheet
              <select name="slip_sheet">
                <option value="two_poly">two_poly</option>
                <option value="one_poly">one_poly</option>
                <option value="none">none</option>
              </select>
            </label>
          </div>
          <label class="checkline"><input name="expansion_at_one_end" type="checkbox" checked>Expansion at one end only</label>
          <button type="submit">Run shrinkage design</button>
        </form>
      </div>

      <aside class="result" id="result-panel">
        <div class="empty">
          <div>
            <h2>Results will land here.</h2>
            <p class="result-copy">
              Run any workflow on the left. The panel shows the key metrics, validation basis,
              and design notes from the same library objects used by the CLI and tests.
            </p>
          </div>
        </div>
      </aside>
    </section>
  </main>

  <script>
    const resultPanel = document.getElementById("result-panel");
    const tabButtons = document.querySelectorAll("[data-tab-target]");
    const tabPanels = document.querySelectorAll("[data-tab-panel]");

    function activateTab(name) {
      tabButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.tabTarget === name);
      });
      tabPanels.forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.tabPanel === name);
      });
    }

    function parseForm(form) {
      const data = {};
      for (const element of form.elements) {
        if (!element.name) continue;
        if (element.type === "checkbox") {
          data[element.name] = element.checked;
          continue;
        }
        if (element.tagName === "SELECT") {
          data[element.name] = element.value;
          continue;
        }
        if (element.type === "number") {
          data[element.name] = element.value === "" ? null : Number(element.value);
          continue;
        }
        data[element.name] = element.value;
      }
      return data;
    }

    function statusTone(status) {
      return status === "equation-based" ? "ok" : "warn";
    }

    function renderResult(payload) {
      const metrics = payload.metrics.map((row) => `
        <li><span>${row.label}</span><strong>${row.value}</strong></li>
      `).join("");
      const notes = payload.notes.map((note) => `<li>${note}</li>`).join("");
      resultPanel.innerHTML = `
        <h2>${payload.title}</h2>
        <p class="result-copy">Result generated from the library core with the method basis shown explicitly.</p>
        <div class="status-line">
          <span class="status-chip ${statusTone(payload.validation_status)}">${payload.validation_status}</span>
        </div>
        <div class="basis">${payload.model_basis}</div>
        <ul class="metric-list">${metrics}</ul>
        <h3>Notes</h3>
        <ul class="note-list">${notes}</ul>
      `;
    }

    function renderError(message) {
      resultPanel.innerHTML = `
        <h2>Input issue</h2>
        <p class="result-copy">The design core rejected the request before calculation.</p>
        <div class="basis">${message}</div>
      `;
    }

    async function submitForm(event) {
      event.preventDefault();
      const form = event.currentTarget;
      const endpoint = form.dataset.endpoint;
      const payload = parseForm(form);
      const button = form.querySelector("button");
      button.disabled = true;
      button.textContent = "Running...";
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const body = await response.json();
        if (!response.ok) {
          renderError(body.error || "Request failed.");
          return;
        }
        renderResult(body);
      } catch (error) {
        renderError(error.message || "Request failed.");
      } finally {
        button.disabled = false;
        button.textContent = button.dataset.label || button.textContent.replace("Running...", "Submit");
      }
    }

    document.querySelectorAll("form[data-endpoint]").forEach((form) => {
      const button = form.querySelector("button");
      button.dataset.label = button.textContent;
      form.addEventListener("submit", submitForm);
    });

    tabButtons.forEach((button) => {
      button.addEventListener("click", () => activateTab(button.dataset.tabTarget));
    });
  </script>
</body>
</html>
"""
