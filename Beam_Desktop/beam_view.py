import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Polygon


class BeamView:
    def __init__(self, parent, on_point_drag=None):
        self.parent = parent
        self.on_point_drag = on_point_drag
        self.figure = Figure(figsize=(9.5, 8.2), dpi=100)
        self.figure.subplots_adjust(
            left=0.09, right=0.98, top=0.97, bottom=0.06, hspace=0.42
        )
        self.axes = [
            self.figure.add_subplot(4, 1, 1),
            self.figure.add_subplot(4, 1, 2),
            self.figure.add_subplot(4, 1, 3),
            self.figure.add_subplot(4, 1, 4),
        ]
        self.canvas = FigureCanvasTkAgg(self.figure, master=parent)
        self.crosshair_lines = []
        self.crosshair_texts = []
        self.result = None
        self.dragging_point = None
        self.point_positions = []
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("button_release_event", self._on_release)

    def update(self, beam, result):
        self.result = result
        self.crosshair_lines = []
        self.crosshair_texts = []
        for ax in self.axes:
            ax.clear()
        span = beam.span_ft

        beam_ax, shear_ax, moment_ax, deflection_ax = self.axes
        beam_ax.set_xlim(-0.04 * span, 1.04 * span)
        beam_ax.set_ylim(-1.15, 1.15)
        beam_ax.axis("off")
        beam_ax.plot([0, span], [0, 0], color="#263238", linewidth=5)

        if beam.support_type == "Simply supported":
            beam_ax.plot([0, 0], [-0.08, -0.45], color="#263238", linewidth=2)
            beam_ax.plot([-0.30, 0.30], [-0.45, -0.45], color="#263238", linewidth=2)
            beam_ax.plot([span, span], [-0.08, -0.45], color="#263238", linewidth=2)
            beam_ax.plot([span - 0.30, span + 0.30], [-0.45, -0.45], color="#263238", linewidth=2)
            beam_ax.scatter(
                [0, span], [0, 0], marker="o", s=55,
                facecolor="white", edgecolor="#263238", zorder=5
            )
        else:
            beam_ax.add_patch(Polygon(
                [[-0.02 * span, -0.10], [-0.02 * span, 0.10],
                 [-0.18 * span, 0], [-0.02 * span, -0.10]],
                closed=True, facecolor="#263238"
            ))
            for offset in (-0.18, -0.10, -0.02):
                beam_ax.plot([offset * span, 0], [-0.15, 0.15],
                              color="#263238", linewidth=1)

        beam_ax.text(
            0.5 * span, 0.82, "Simply supported" if beam.support_type == "Simply supported"
            else "Cantilever - fixed left",
            ha="center", va="center", fontsize=9, color="#455A64"
        )

        for load in beam.uniform_loads:
            start = max(0, load.start_ft)
            end = min(span, load.end_ft)
            if end <= start:
                continue
            xs = [start + (end - start) * i / 8 for i in range(9)]
            direction = -1 if load.magnitude_kips_per_ft >= 0 else 1
            for x in xs:
                beam_ax.annotate(
                    "", xy=(x, 0), xytext=(x, direction * 0.55),
                    arrowprops=dict(arrowstyle="->", color="#1976D2", lw=1.2)
                )
            beam_ax.plot([start, end], [0.58, 0.58], color="#1976D2", linewidth=2)

        self.point_positions = []
        for load in beam.point_loads:
            x = load.position_ft
            self.point_positions.append(x)
            beam_ax.annotate(
                "", xy=(x, 0), xytext=(x, 0.75),
                arrowprops=dict(arrowstyle="-|>", color="#1976D2", lw=2),
                annotation_clip=True
            )
            beam_ax.scatter([x], [0], s=35, color="#1976D2", zorder=6)

        if beam.support_type == "Simply supported":
            beam_ax.annotate(
                f"Ra {result.left_reaction_kips:.2f} k",
                xy=(0, -0.52), xytext=(0, -0.82),
                ha="center", fontsize=8, color="#455A64"
            )
            beam_ax.annotate(
                f"Rb {result.right_reaction_kips:.2f} k",
                xy=(span, -0.52), xytext=(span, -0.82),
                ha="center", fontsize=8, color="#455A64"
            )
        else:
            beam_ax.annotate(
                f"RA {result.left_reaction_kips:.2f} k",
                xy=(0, -0.52), xytext=(0, -0.82),
                ha="center", fontsize=8, color="#455A64"
            )
            beam_ax.annotate(
                f"Mfixed {abs(result.fixed_end_moment_kip_ft):.2f} kip-ft",
                xy=(0, 0.25), xytext=(0.04 * span, 0.40),
                ha="left", fontsize=8, color="#455A64"
            )

        diagrams = (
            (shear_ax, result.shear_kips, "Shear (kips)", "#1976D2",
             result.max_shear_kips),
            (moment_ax, result.moment_kip_ft, "Moment (kip-ft)", "#F59E0B",
             result.max_moment_kip_ft),
            (deflection_ax, result.deflection_in, "Deflected shape (in)", "#7E57C2",
             result.max_deflection_in),
        )
        for ax, values, title, color, maximum in diagrams:
            ax.fill_between(result.x_ft, values, 0, color=color, alpha=0.22)
            ax.plot(result.x_ft, values, color=color, linewidth=1.8)
            ax.axhline(0, color="#90A4AE", linewidth=0.8)
            ax.set_xlim(0, span)
            ax.set_title(title, loc="left", fontsize=9, color="#37474F")
            ax.grid(True, axis="both", alpha=0.18)
            ax.tick_params(labelsize=8)
            ax.set_ylabel("")

        moment_index = int(abs(result.moment_kip_ft).argmax())
        deflection_index = int(abs(result.deflection_in).argmax())
        shear_index = int(abs(result.shear_kips).argmax())
        for ax, index, values, fmt in (
            (shear_ax, shear_index, result.shear_kips, "{:.2f} k"),
            (moment_ax, moment_index, result.moment_kip_ft, "{:.2f} kip-ft"),
            (deflection_ax, deflection_index, result.deflection_in, "{:.3f} in"),
        ):
            x = result.x_ft[index]
            y = values[index]
            ax.scatter([x], [y], s=28, color="#263238", zorder=5)
            ax.annotate(
                fmt.format(y),
                xy=(x, y), xytext=(4, 8),
                textcoords="offset points", fontsize=8,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#CFD8DC")
            )

        for ax in self.axes[:-1]:
            ax.set_xticklabels([])
        self.axes[-1].set_xlabel("Beam position (ft)")
        self.canvas.draw_idle()

    def _on_press(self, event):
        if event.inaxes is not self.axes[0] or event.xdata is None:
            return
        for index, x in enumerate(self.point_positions):
            if abs(event.xdata - x) <= 0.45:
                self.dragging_point = index
                break

    def _on_motion(self, event):
        if event.inaxes not in self.axes or event.xdata is None:
            return
        span = max(self.axes[-1].get_xlim())
        x = min(max(event.xdata, 0), span)
        if not self.crosshair_lines:
            for ax in self.axes:
                self.crosshair_lines.append(
                    ax.axvline(x, color="#90A4AE", linewidth=1, linestyle="--")
                )
            if self.result is not None:
                for ax in self.axes:
                    self.crosshair_texts.append(
                        ax.text(
                            0.98, 0.90, "", transform=ax.transAxes,
                            ha="right", va="top", fontsize=8,
                            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#CFD8DC")
                        )
                    )
        else:
            for line in self.crosshair_lines:
                line.set_xdata([x, x])
        if self.result is not None:
            index = int(abs(self.result.x_ft - x).argmin())
            labels = (
                f"V {self.result.shear_kips[index]:.2f} k",
                f"M {self.result.moment_kip_ft[index]:.2f} kip-ft",
                f"y {self.result.deflection_in[index]:.3f} in",
            )
            for text, label in zip(self.crosshair_texts, labels):
                text.set_text(label)
        self.canvas.draw_idle()

    def _on_release(self, event):
        if self.dragging_point is None:
            return
        if event.inaxes is self.axes[0] and event.xdata is not None:
            span = max(self.axes[-1].get_xlim())
            x = min(max(round(event.xdata * 4) / 4, 0), span)
            if self.on_point_drag:
                self.on_point_drag(self.dragging_point, x)
        self.dragging_point = None
