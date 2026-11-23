from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Polygon


def write_calculation_pdf(path, beam, result):
    figure = Figure(figsize=(11.7, 8.3), facecolor="white")
    figure.text(
        0.06, 0.965, "Beam Designer - Calculation Sheet",
        fontsize=16, fontweight="bold", color="#263238", va="top",
    )

    section = result.section
    figure.text(
        0.06, 0.92,
        f"Support: {beam.support_type}    Span: {beam.span_ft:g} ft    "
        f"Section: {section.name} ({section.material})    "
        f"Deflection limit: L/{beam.deflection_divisor}",
        fontsize=9, color="#263238", va="top",
    )
    figure.text(
        0.06, 0.885,
        f"Material properties: E = {section.e_ksi:g} ksi    "
        f"Ix = {section.ix_in4:g} in^4    Sx = {section.sx_in3:g} in^3    "
        f"Fb = {section.fb_ksi:g} ksi    Self-weight ignored",
        fontsize=8, color="#455A64", va="top",
    )

    point_lines = [
        f"P{index}: {load.magnitude_kips:g} k at {load.position_ft:g} ft"
        for index, load in enumerate(beam.point_loads, start=1)
    ] or ["None"]
    uniform_lines = [
        f"w{index}: {load.magnitude_kips_per_ft:g} k/ft, "
        f"{load.start_ft:g}-{load.end_ft:g} ft"
        for index, load in enumerate(beam.uniform_loads, start=1)
    ] or ["None"]
    figure.text(
        0.06, 0.845, "POINT LOADS", fontsize=8, fontweight="bold",
        color="#455A64", va="top",
    )
    figure.text(
        0.06, 0.82, "\n".join(point_lines), fontsize=7.5,
        color="#263238", va="top",
    )
    figure.text(
        0.52, 0.845, "UNIFORM LOADS", fontsize=8, fontweight="bold",
        color="#455A64", va="top",
    )
    figure.text(
        0.52, 0.82, "\n".join(uniform_lines), fontsize=7.5,
        color="#263238", va="top",
    )

    bending_status = "PASS" if result.bending_pass else "FAIL"
    deflection_status = "PASS" if result.deflection_pass else "FAIL"
    if beam.support_type == "Simply supported":
        reaction_text = (
            f"Reactions: RA = {result.left_reaction_kips:.3f} k, "
            f"RB = {result.right_reaction_kips:.3f} k"
        )
    else:
        reaction_text = (
            f"Fixed reaction: {result.left_reaction_kips:.3f} k    "
            f"Fixed-end moment: {abs(result.fixed_end_moment_kip_ft):.3f} kip-ft"
        )
    figure.text(
        0.06, 0.765,
        f"Bending: {result.bending_stress_ksi:.3f} / "
        f"{result.allowable_bending_stress_ksi:.3f} ksi  {bending_status}    "
        f"Deflection: {result.max_deflection_in:.3f} / "
        f"{result.deflection_allowance_in:.3f} in  {deflection_status}",
        fontsize=9, fontweight="bold", color="#263238", va="top",
    )
    figure.text(
        0.06, 0.735,
        f"{reaction_text}    "
        f"Max |V| = {result.max_shear_kips:.3f} k    "
        f"Max |M| = {result.max_moment_kip_ft:.3f} kip-ft "
        f"at {result.max_moment_location_ft:.3f} ft    "
        f"Max |y| = {result.max_deflection_in:.3f} in "
        f"at {result.max_deflection_location_ft:.3f} ft",
        fontsize=7.5, color="#455A64", va="top",
    )

    beam_ax = figure.add_axes([0.09, 0.575, 0.87, 0.105])
    shear_ax = figure.add_axes([0.09, 0.415, 0.87, 0.12])
    moment_ax = figure.add_axes([0.09, 0.255, 0.87, 0.12])
    deflection_ax = figure.add_axes([0.09, 0.095, 0.87, 0.12])
    span = beam.span_ft

    beam_ax.set_xlim(-0.04 * span, 1.04 * span)
    beam_ax.set_ylim(-0.9, 0.9)
    beam_ax.axis("off")
    beam_ax.plot([0, span], [0, 0], color="#263238", linewidth=4)
    if beam.support_type == "Simply supported":
        for x in (0, span):
            beam_ax.add_patch(Polygon(
                [[x, -0.08], [x - 0.25, -0.48], [x + 0.25, -0.48]],
                closed=True, facecolor="white", edgecolor="#263238",
                linewidth=1.2,
            ))
            beam_ax.plot([x - 0.35, x + 0.35], [-0.5, -0.5],
                         color="#263238", linewidth=1)
        beam_ax.text(0, -0.78, f"RA {result.left_reaction_kips:.2f} k",
                     ha="center", fontsize=7)
        beam_ax.text(span, -0.78, f"RB {result.right_reaction_kips:.2f} k",
                     ha="center", fontsize=7)
    else:
        beam_ax.add_patch(Polygon(
            [[-0.18 * span, -0.12], [-0.18 * span, 0.12], [0, 0]],
            closed=True, facecolor="#263238",
        ))
        for offset in (-0.17, -0.12, -0.07, -0.02):
            beam_ax.plot([offset * span, 0], [-0.15, 0.15],
                         color="#263238", linewidth=0.8)
        beam_ax.text(
            0.02 * span, -0.72,
            f"RA {result.left_reaction_kips:.2f} k, "
            f"Mfixed {abs(result.fixed_end_moment_kip_ft):.2f} kip-ft",
            ha="left", fontsize=7,
        )

    for load in beam.point_loads:
        direction = -1 if load.magnitude_kips >= 0 else 1
        beam_ax.annotate(
            "", xy=(load.position_ft, 0),
            xytext=(load.position_ft, direction * 0.62),
            arrowprops=dict(arrowstyle="-|>", color="#1976D2", lw=1.5),
        )
    for load in beam.uniform_loads:
        start = min(max(load.start_ft, 0), span)
        end = min(max(load.end_ft, 0), span)
        if end <= start:
            continue
        direction = -1 if load.magnitude_kips_per_ft >= 0 else 1
        for index in range(9):
            x = start + (end - start) * index / 8
            beam_ax.annotate(
                "", xy=(x, 0), xytext=(x, direction * 0.45),
                arrowprops=dict(arrowstyle="->", color="#1976D2", lw=0.8),
            )
        beam_ax.plot([start, end], [direction * 0.47] * 2,
                     color="#1976D2", linewidth=1)

    diagrams = (
        (shear_ax, result.shear_kips, "Shear V (kips)", "#1976D2"),
        (moment_ax, result.moment_kip_ft, "Moment M (kip-ft)", "#F59E0B"),
        (deflection_ax, result.deflection_in, "Deflection y (in)", "#7E57C2"),
    )
    for ax, values, label, color in diagrams:
        ax.fill_between(result.x_ft, values, 0, color=color, alpha=0.2)
        ax.plot(result.x_ft, values, color=color, linewidth=1.5)
        ax.axhline(0, color="#90A4AE", linewidth=0.7)
        ax.set_xlim(0, span)
        ax.set_ylabel(label, fontsize=7)
        ax.grid(True, alpha=0.18)
        ax.tick_params(labelsize=7)

    max_indices = (
        int(abs(result.shear_kips).argmax()),
        int(abs(result.moment_kip_ft).argmax()),
        int(abs(result.deflection_in).argmax()),
    )
    for ax, values, index in zip(
        (shear_ax, moment_ax, deflection_ax),
        (result.shear_kips, result.moment_kip_ft, result.deflection_in),
        max_indices,
    ):
        ax.scatter([result.x_ft[index]], [values[index]], s=18, color="#263238")

    shear_ax.set_xticklabels([])
    moment_ax.set_xticklabels([])
    deflection_ax.set_xlabel("Position x (ft)", fontsize=8)
    figure.text(
        0.96, 0.025, "Generated by Beam Designer",
        ha="right", fontsize=7, color="#78909C",
    )

    with PdfPages(path) as pdf:
        pdf.savefig(figure)
