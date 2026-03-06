"""Command-line interface for slab_designer.

Usage examples:

  # Design for a wheel load (PCA interior method)
  slab-designer wheel --axle 22400 --contact 25 --spacing 40 --k 200 --fr 570

  # Design for a rack post load
  slab-designer rack --post 15500 --plate 36 --long 100 --short 40 --k 100 --fr 570

  # Design for uniform load with aisle
  slab-designer uniform --load 500 --aisle 10 --k 100 --fr 570

  # FRC elastic design
  slab-designer frc --load 15000 --contact 24 --re3 55 --k 100 --fr 550

  # Post-tensioned design
  slab-designer pt --length 500 --thickness 6 --pe 26000 --k 150

  # Analyze stress at a given thickness
  slab-designer analyze --load 11200 --contact 25 --h 7.75 --k 200
"""

from __future__ import annotations

import math
from typing import Optional

try:
    import typer
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
except ImportError as e:
    raise ImportError(
        "CLI dependencies not installed. Run: pip install slab-designer[cli]"
    ) from e

from slab_designer import (
    Concrete,
    FiberProperties,
    PostTensionTendon,
    RackLoad,
    Subgrade,
    UniformLoad,
    WheelLoad,
    design_frc_elastic,
    design_frc_yield_line,
    design_for_rack_load,
    design_for_uniform_load,
    design_for_wheel_load,
    design_post_tensioned,
    isolation_joint_width,
)
from slab_designer.analysis import (
    radius_of_relative_stiffness,
    westergaard_interior,
    westergaard_edge,
    westergaard_corner,
    allowable_stress,
)
from slab_designer.design.frc import YieldLineCase
from slab_designer.soil import SlipSheet

app = typer.Typer(
    name="slab-designer",
    help="ACI 360R-10 concrete slab-on-ground design tool.",
    no_args_is_help=True,
)
console = Console()


# ---------------------------------------------------------------------------
# Shared option definitions
# ---------------------------------------------------------------------------

def _concrete(fc: float, fr: float, E: float, nu: float) -> Concrete:
    return Concrete(fc=fc, fr=fr, E=E, nu=nu)


def _subgrade(k: float, mu: Optional[float], slip_sheet: str) -> Subgrade:
    ss = SlipSheet(slip_sheet) if slip_sheet in [s.value for s in SlipSheet] else SlipSheet.NONE
    return Subgrade(k=k, mu=mu, slip_sheet=ss)


def _print_design_result(result, title: str) -> None:
    """Pretty-print a DesignResult."""
    status = "[green]ADEQUATE[/green]" if result.is_adequate else "[red]INADEQUATE[/red]"

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Parameter", style="bold cyan")
    table.add_column("Value")

    table.add_row("Method", result.method.value)
    table.add_row("Load case", result.load_case.value)
    table.add_row(
        "Required thickness",
        f"{result.required_thickness_in:.2f} in  "
        f"→ {result.required_thickness_rounded_in:.2f} in (rounded)",
    )
    table.add_row(
        "Computed stress",
        f"{result.computed_stress_psi:.1f} psi",
    )
    table.add_row(
        "Allowable stress",
        f"{result.allowable_stress_psi:.1f} psi  (fr / SF = "
        f"{result.concrete.fr:.0f} / {result.safety_factor})",
    )
    table.add_row("Utilization", f"{result.utilization:.3f}")
    table.add_row("Status", status)
    table.add_row("Radius L", f"{result.L_in:.2f} in")

    console.print(Panel(table, title=f"[bold]{title}[/bold]", border_style="blue"))

    if result.notes:
        for note in result.notes:
            console.print(f"  [dim]• {note}[/dim]")


# ---------------------------------------------------------------------------
# Wheel load design
# ---------------------------------------------------------------------------

@app.command()
def wheel(
    axle: float = typer.Option(..., help="Axle load, lb."),
    contact: float = typer.Option(..., help="Tire contact area, in²."),
    spacing: float = typer.Option(40.0, help="Wheel spacing (center-to-center), in."),
    k: float = typer.Option(..., help="Modulus of subgrade reaction, pci."),
    fr: float = typer.Option(570.0, help="Modulus of rupture, psi."),
    fc: float = typer.Option(4000.0, help="Concrete compressive strength, psi."),
    sf: float = typer.Option(1.7, help="Factor of safety."),
    E: float = typer.Option(4_000_000.0, help="Elastic modulus, psi."),
    nu: float = typer.Option(0.15, help="Poisson's ratio."),
    mu: Optional[float] = typer.Option(None, help="Friction coefficient override."),
    slip_sheet: str = typer.Option("none", help="Slip sheet type: none, one_poly, two_poly."),
    edge: bool = typer.Option(False, help="Use COE edge method instead of PCA interior."),
) -> None:
    """Design slab thickness for a wheel (axle) load per ACI 360R-10 §7.2.1."""
    load = WheelLoad(
        axle_load_lb=axle,
        contact_area_in2=contact,
        wheel_spacing_in=spacing,
    )
    concrete = _concrete(fc, fr, E, nu)
    subgrade = _subgrade(k, mu, slip_sheet)

    from slab_designer.design.unreinforced import LoadCase
    lc = LoadCase.EDGE if edge else LoadCase.INTERIOR

    result = design_for_wheel_load(load, concrete, subgrade, safety_factor=sf, load_case=lc)
    _print_design_result(result, "Wheel Load Design (PCA Method)")


# ---------------------------------------------------------------------------
# Rack post load design
# ---------------------------------------------------------------------------

@app.command()
def rack(
    post: float = typer.Option(..., help="Post load, lb."),
    plate: float = typer.Option(..., help="Base plate area, in²."),
    long: float = typer.Option(100.0, help="Longitudinal post spacing, in."),
    short: float = typer.Option(40.0, help="Transverse post spacing, in."),
    k: float = typer.Option(..., help="Modulus of subgrade reaction, pci."),
    fr: float = typer.Option(570.0, help="Modulus of rupture, psi."),
    fc: float = typer.Option(4000.0, help="Concrete compressive strength, psi."),
    sf: float = typer.Option(1.4, help="Factor of safety."),
    E: float = typer.Option(4_000_000.0, help="Elastic modulus, psi."),
    nu: float = typer.Option(0.15, help="Poisson's ratio."),
    k_sub: Optional[float] = typer.Option(None, hidden=True),
) -> None:
    """Design slab thickness for rack/post storage loads per ACI 360R-10 §7.2.1.2."""
    load = RackLoad(
        post_load_lb=post,
        base_plate_area_in2=plate,
        long_spacing_in=long,
        short_spacing_in=short,
    )
    concrete = _concrete(fc, fr, E, nu)
    subgrade = Subgrade(k=k)

    result = design_for_rack_load(load, concrete, subgrade, safety_factor=sf)
    _print_design_result(result, "Rack Post Load Design (PCA Method)")


# ---------------------------------------------------------------------------
# Uniform load with aisle design
# ---------------------------------------------------------------------------

@app.command()
def uniform(
    load: float = typer.Option(..., help="Uniform load intensity, psf."),
    aisle: float = typer.Option(..., help="Clear aisle width, ft."),
    k: float = typer.Option(..., help="Modulus of subgrade reaction, pci."),
    fr: float = typer.Option(570.0, help="Modulus of rupture, psi."),
    fc: float = typer.Option(4000.0, help="Concrete compressive strength, psi."),
    sf: float = typer.Option(1.7, help="Factor of safety."),
    E: float = typer.Option(4_000_000.0, help="Elastic modulus, psi."),
    nu: float = typer.Option(0.15, help="Poisson's ratio."),
) -> None:
    """Design slab thickness for uniform loading with aisles per ACI 360R-10 §7.2.1.3."""
    ul = UniformLoad(intensity_psf=load, aisle_width_ft=aisle)
    concrete = _concrete(fc, fr, E, nu)
    subgrade = Subgrade(k=k)

    result = design_for_uniform_load(ul, concrete, subgrade, safety_factor=sf)
    _print_design_result(result, "Uniform Load Design (Rice/Hetenyi Aisle Method)")


# ---------------------------------------------------------------------------
# FRC design
# ---------------------------------------------------------------------------

@app.command()
def frc(
    load: float = typer.Option(..., help="Applied concentrated load, lb."),
    contact: float = typer.Option(..., help="Contact area, in²."),
    k: float = typer.Option(..., help="Modulus of subgrade reaction, pci."),
    fr: float = typer.Option(550.0, help="Modulus of rupture of plain concrete, psi."),
    fc: float = typer.Option(4000.0, help="Concrete compressive strength, psi."),
    re3: float = typer.Option(..., help="Fiber residual strength factor Re,3, %%."),
    sf: float = typer.Option(1.5, help="Factor of safety."),
    E: float = typer.Option(4_000_000.0, help="Elastic modulus, psi."),
    nu: float = typer.Option(0.15, help="Poisson's ratio."),
    method: str = typer.Option("elastic", help="Design method: elastic or yield_line."),
    case: str = typer.Option("interior", help="Load case: interior, edge, or corner."),
    h: Optional[float] = typer.Option(None, help="Slab thickness for yield-line check, in."),
    transfer: float = typer.Option(0.0, help="Joint load transfer fraction (edge only)."),
    shrinkage: float = typer.Option(0.0, help="Shrinkage/curling moment, in·lb/in."),
) -> None:
    """Design fiber-reinforced concrete slab per ACI 360R-10 Chapter 11."""
    fibers = FiberProperties(re3=re3)
    concrete = _concrete(fc, fr, E, nu)
    subgrade = Subgrade(k=k)

    case_map = {
        "interior": YieldLineCase.INTERIOR,
        "edge": YieldLineCase.EDGE,
        "corner": YieldLineCase.CORNER,
    }
    yl_case = case_map.get(case.lower(), YieldLineCase.INTERIOR)

    if method.lower() == "elastic":
        result = design_frc_elastic(
            load_lb=load,
            contact_area_in2=contact,
            fibers=fibers,
            concrete=concrete,
            subgrade=subgrade,
            safety_factor=sf,
        )
    else:
        if h is None:
            console.print("[red]--h is required for yield-line method.[/red]")
            raise typer.Exit(code=1)
        result = design_frc_yield_line(
            load_lb=load,
            contact_area_in2=contact,
            h_in=h,
            fibers=fibers,
            concrete=concrete,
            subgrade=subgrade,
            safety_factor=sf,
            case=yl_case,
            joint_transfer=transfer,
            additional_moment_inlb_per_in=shrinkage,
        )

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Parameter", style="bold cyan")
    table.add_column("Value")
    table.add_row("Method", result.method)
    table.add_row("Re,3", f"{result.re3:.1f} %")
    table.add_row("M₀", f"{result.M0_inlb_per_in:.0f} in·lb/in")
    if result.h_in:
        table.add_row("Required thickness", f"{result.h_in:.2f} in")
    if result.P_allowable_lb:
        table.add_row("Allowable load", f"{result.P_allowable_lb:.0f} lb")
    if result.allowable_stress_psi:
        table.add_row("Allowable stress", f"{result.allowable_stress_psi:.1f} psi")

    console.print(Panel(table, title="[bold]FRC Slab Design[/bold]", border_style="blue"))
    for note in result.notes:
        console.print(f"  [dim]• {note}[/dim]")


# ---------------------------------------------------------------------------
# Post-tensioned design
# ---------------------------------------------------------------------------

@app.command()
def pt(
    length: float = typer.Option(..., help="Slab length in PT direction, ft."),
    thickness: float = typer.Option(..., help="Slab thickness, in."),
    pe: float = typer.Option(..., help="Effective tendon force Pe, lb."),
    k: float = typer.Option(150.0, help="Modulus of subgrade reaction, pci."),
    fr: float = typer.Option(570.0, help="Modulus of rupture, psi."),
    fc: float = typer.Option(4000.0, help="Concrete compressive strength, psi."),
    fp: Optional[float] = typer.Option(None, help="Residual prestress override, psi."),
    mu: float = typer.Option(0.5, help="Subgrade friction coefficient."),
    slip_sheet: str = typer.Option("none", help="Slip sheet type: none, one_poly, two_poly."),
    industrial: bool = typer.Option(True, help="Industrial floor (affects recommended fp)."),
) -> None:
    """Design post-tensioned slab-on-ground per ACI 360R-10 Chapter 10."""
    from slab_designer.design.post_tensioned import PostTensionedDesign
    concrete = _concrete(fc, fr, 4_000_000.0, 0.15)
    ss = SlipSheet(slip_sheet) if slip_sheet in [s.value for s in SlipSheet] else SlipSheet.NONE
    subgrade = Subgrade(k=k, mu=mu, slip_sheet=ss)
    tendon = PostTensionTendon(Pe=pe)

    design = PostTensionedDesign(
        slab_length_ft=length,
        slab_thickness_in=thickness,
        tendon=tendon,
        concrete=concrete,
        subgrade=subgrade,
        residual_prestress_psi=fp,
    )
    result = design_post_tensioned(design)

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Parameter", style="bold cyan")
    table.add_column("Value")
    table.add_row("Slab length", f"{length:.0f} ft")
    table.add_row("Slab thickness", f"{thickness:.1f} in")
    table.add_row("Residual prestress fp", f"{result.fp_psi:.0f} psi")
    table.add_row("Friction force Pr", f"{result.Pr_lb_ft:.0f} lb/ft")
    table.add_row(
        "Tendon spacing",
        f"{result.tendon_spacing_ft:.3f} ft  ({result.tendon_spacing_in:.1f} in)",
    )
    table.add_row("Radius of stiffness L", f"{result.L_in:.2f} in")

    console.print(Panel(table, title="[bold]Post-Tensioned Slab Design[/bold]", border_style="blue"))
    for note in result.notes:
        console.print(f"  [dim]• {note}[/dim]")


# ---------------------------------------------------------------------------
# Stress analysis at a given thickness
# ---------------------------------------------------------------------------

@app.command()
def analyze(
    load: float = typer.Option(..., help="Concentrated load, lb."),
    contact: float = typer.Option(..., help="Contact area, in²."),
    h: float = typer.Option(..., help="Slab thickness to check, in."),
    k: float = typer.Option(..., help="Modulus of subgrade reaction, pci."),
    fr: float = typer.Option(570.0, help="Modulus of rupture, psi."),
    sf: float = typer.Option(1.7, help="Factor of safety."),
    E: float = typer.Option(4_000_000.0, help="Elastic modulus, psi."),
    nu: float = typer.Option(0.15, help="Poisson's ratio."),
    case: str = typer.Option("interior", help="Load case: interior, edge, or corner."),
) -> None:
    """Compute Westergaard stress for a given slab thickness and load."""
    a = math.sqrt(contact / math.pi)
    fa = allowable_stress(fr, sf)

    if case.lower() == "edge":
        ws = westergaard_edge(load, h, a, k, E=E, nu=nu)
    elif case.lower() == "corner":
        ws = westergaard_corner(load, h, a, k, E=E, nu=nu)
    else:
        ws = westergaard_interior(load, h, a, k, E=E, nu=nu)

    status = "[green]OK[/green]" if ws.stress_psi <= fa else "[red]NG[/red]"

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Parameter", style="bold cyan")
    table.add_column("Value")
    table.add_row("Load case", ws.case)
    table.add_row("Load P", f"{load:.0f} lb")
    table.add_row("Contact radius a", f"{a:.3f} in")
    table.add_row("Slab thickness h", f"{h:.2f} in")
    table.add_row("Radius of stiffness L", f"{ws.L:.2f} in")
    table.add_row("Computed stress", f"{ws.stress_psi:.1f} psi")
    table.add_row("Allowable stress", f"{fa:.1f} psi  (fr={fr:.0f} / SF={sf})")
    table.add_row("Utilization", f"{ws.stress_psi/fa:.3f}")
    table.add_row("Status", status)

    console.print(Panel(table, title="[bold]Westergaard Stress Analysis[/bold]", border_style="blue"))


# ---------------------------------------------------------------------------
# Isolation joint width
# ---------------------------------------------------------------------------

@app.command()
def joint(
    length: float = typer.Option(..., help="Slab length, ft."),
    strain: float = typer.Option(0.00035, help="Expansion strain (dimensionless)."),
    one_end: bool = typer.Option(True, help="Expansion at one end only."),
) -> None:
    """Compute isolation joint width for shrinkage-compensating concrete (Eq. 9-1)."""
    jw = isolation_joint_width(
        slab_length_ft=length,
        expansion_strain=strain,
        expansion_at_one_end=one_end,
    )
    console.print(
        f"Isolation joint width = [bold]{jw:.3f} in[/bold] "
        f"({'one end' if one_end else 'split both ends'})"
    )
    console.print(
        f"  Slab: {length:.0f} ft,  ε = {strain:.5f},  "
        f"2 × {length} × 12 × {strain} {'/ 2' if not one_end else ''} = {jw:.3f} in"
    )


if __name__ == "__main__":
    app()
