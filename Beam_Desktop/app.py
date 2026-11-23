import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import csv
import json

from beam_analysis import (
    BeamInput,
    PointLoad,
    UniformLoad,
    beam_from_dict,
    beam_to_dict,
    get_sections,
    get_section,
    analyze,
)
from beam_view import BeamView
from beam_export import write_results_csv
from beam_report import write_calculation_pdf


class BeamDesignerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Beam Designer")
        self.root.geometry("1280x820")
        self.root.minsize(980, 680)
        self.root.configure(bg="#F4F7F9")
        self._build_menu()

        self.point_loads = []
        self.uniform_loads = [UniformLoad(1.0, 0.0, 20.0)]
        self.recalc_after_id = None

        self.support_var = tk.StringVar(value="Simply supported")
        self.span_var = tk.StringVar(value="20")
        self.material_var = tk.StringVar(value="Steel")
        self.section_var = tk.StringVar(value="W12x26")
        self.limit_var = tk.StringVar(value="L/360")

        outer = ttk.Frame(root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        self.left = ttk.Frame(outer, width=300)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.left.grid_propagate(False)

        self.right = ttk.Frame(outer)
        self.right.grid(row=0, column=1, sticky="nsew")
        self.right.rowconfigure(0, weight=0)
        self.right.rowconfigure(1, weight=1)
        self.right.rowconfigure(2, weight=0)
        self.right.columnconfigure(0, weight=1)

        self._build_inputs()
        self._build_export_toolbar()
        self.view = BeamView(self.right, on_point_drag=self._drag_point_load)
        self.view.canvas.get_tk_widget().grid(
            row=1, column=0, sticky="nsew"
        )
        self._build_check_cards()

        self.support_var.trace_add("write", lambda *_: self.schedule_recalculate())
        self.material_var.trace_add("write", lambda *_: self._material_changed())
        self.section_var.trace_add("write", lambda *_: self.schedule_recalculate())
        self.limit_var.trace_add("write", lambda *_: self.schedule_recalculate())
        self.span_var.trace_add("write", lambda *_: self._span_text_changed())

        self.schedule_recalculate()

    def _build_menu(self):
        menu_bar = tk.Menu(self.root)
        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Open", command=self._open_beam)
        file_menu.add_command(label="Save", command=self._save_beam)
        menu_bar.add_cascade(label="File", menu=file_menu)
        self.root.configure(menu=menu_bar)

    def _build_export_toolbar(self):
        toolbar = ttk.Frame(self.right)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(
            toolbar, text="Export",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(0, 10))
        self.csv_export_button = ttk.Button(
            toolbar,
            text="Export results to CSV",
            command=self._export_results_csv,
        )
        self.csv_export_button.pack(side="left", padx=(0, 6))
        self.pdf_export_button = ttk.Button(
            toolbar,
            text="Save calculation sheet (PDF)",
            command=self._save_calculation_pdf,
        )
        self.pdf_export_button.pack(side="left")

    def _build_inputs(self):
        title = ttk.Label(
            self.left, text="Beam Designer", font=("Segoe UI", 18, "bold")
        )
        title.pack(anchor="w", pady=(0, 14))

        group = ttk.LabelFrame(self.left, text="Beam setup", padding=10)
        group.pack(fill="x")
        self._label(group, "Support")
        ttk.Combobox(
            group, textvariable=self.support_var, state="readonly",
            values=("Simply supported", "Cantilever")
        ).pack(fill="x", pady=(0, 8))

        self._label(group, "Span (ft)")
        span_row = ttk.Frame(group)
        span_row.pack(fill="x")
        self.span_slider = tk.Scale(
            span_row, from_=4, to=40, orient="horizontal",
            resolution=0.25, length=205,
            command=self._span_slider_changed,
            bg="#F4F7F9", highlightthickness=0,
            troughcolor="#CFD8DC", activebackground="#1976D2"
        )
        self.span_slider.set(20)
        self.span_slider.pack(side="left")
        span_entry = ttk.Entry(
            span_row, textvariable=self.span_var, width=7
        )
        span_entry.pack(side="right")

        self._label(group, "Material")
        ttk.Combobox(
            group, textvariable=self.material_var, state="readonly",
            values=("Steel", "Lumber")
        ).pack(fill="x", pady=(0, 8))

        self._label(group, "Section")
        self.section_combo = ttk.Combobox(
            group, textvariable=self.section_var, state="readonly"
        )
        self.section_combo.pack(fill="x", pady=(0, 8))
        self._refresh_sections()

        self._label(group, "Deflection limit")
        ttk.Combobox(
            group, textvariable=self.limit_var, state="readonly",
            values=("L/240", "L/360")
        ).pack(fill="x")

        loads = ttk.LabelFrame(self.left, text="Loads", padding=8)
        loads.pack(fill="both", expand=True, pady=(12, 0))

        button_row = ttk.Frame(loads)
        button_row.pack(fill="x", pady=(0, 6))
        ttk.Button(
            button_row, text="+ Point load",
            command=self._add_point_load
        ).pack(side="left", padx=(0, 5))
        ttk.Button(
            button_row, text="+ Uniform load",
            command=self._add_uniform_load
        ).pack(side="left")

        canvas = tk.Canvas(loads, highlightthickness=0, bg="#F4F7F9")
        scrollbar = ttk.Scrollbar(loads, orient="vertical", command=canvas.yview)
        self.load_rows = ttk.Frame(canvas)
        self.load_rows.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.load_rows, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.status_label = ttk.Label(
            self.left, text="", foreground="#B71C1C", wraplength=280
        )
        self.status_label.pack(fill="x", pady=(8, 0))
        self._refresh_load_rows()

    def _build_check_cards(self):
        cards = ttk.Frame(self.right)
        cards.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)
        cards.columnconfigure(2, weight=1)

        self.bending_card = self._make_check_card(
            cards, "Bending", "fb = |M|max x 12 / Sx"
        )
        self.bending_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.deflection_card = self._make_check_card(
            cards, "Deflection", "ymax <= L / selected limit"
        )
        self.deflection_card.grid(row=0, column=1, sticky="nsew", padx=6)

        self.suggestion_card = ttk.Frame(
            cards, padding=10, relief="solid", borderwidth=1
        )
        self.suggestion_card.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        ttk.Label(
            self.suggestion_card, text="Suggested section",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w")
        self.suggestion_label = ttk.Label(
            self.suggestion_card, text="Calculating...", font=("Segoe UI", 12)
        )
        self.suggestion_label.pack(anchor="w", pady=(4, 6))
        self.use_button = ttk.Button(
            self.suggestion_card, text="Use section",
            command=self._use_suggested
        )
        self.use_button.pack(anchor="w")
        self.suggested_section = None

    def _make_check_card(self, parent, title, tooltip):
        card = ttk.Frame(parent, padding=10, relief="solid", borderwidth=1)
        ttk.Label(card, text=title, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        value_label = ttk.Label(card, text="--", font=("Segoe UI", 12))
        value_label.pack(anchor="w", pady=(4, 2))
        ratio_label = ttk.Label(card, text="--")
        ratio_label.pack(anchor="w")
        bar = ttk.Progressbar(card, length=220, maximum=100)
        bar.pack(fill="x", pady=(5, 0))
        card.value_label = value_label
        card.ratio_label = ratio_label
        card.bar = bar
        card.tooltip = tooltip
        card.bind("<Enter>", lambda event: self.status_label.configure(text=tooltip))
        card.bind("<Leave>", lambda event: self.status_label.configure(text=""))
        return card

    def _label(self, parent, text):
        ttk.Label(parent, text=text).pack(anchor="w", pady=(0, 2))

    def _refresh_sections(self):
        material = self.material_var.get()
        sections = get_sections(material)
        names = [section.name for section in sections]
        self.section_combo.configure(values=names)
        if self.section_var.get() not in names:
            self.section_var.set(names[0])

    def _material_changed(self):
        self._refresh_sections()
        self.schedule_recalculate()

    def _span_slider_changed(self, value):
        span = round(float(value), 2)
        self.span_var.set(str(span))

    def _span_text_changed(self):
        try:
            span = float(self.span_var.get())
            if 4 <= span <= 40:
                self.span_slider.set(span)
        except ValueError:
            pass
        self.schedule_recalculate()

    def _refresh_load_rows(self):
        for child in self.load_rows.winfo_children():
            child.destroy()

        for index, load in enumerate(self.point_loads):
            frame = ttk.LabelFrame(
                self.load_rows, text=f"Point load {index + 1}", padding=6
            )
            frame.pack(fill="x", pady=(0, 6))
            magnitude = tk.StringVar(value=str(load.magnitude_kips))
            position = tk.StringVar(value=str(load.position_ft))
            magnitude.trace_add("write", lambda *_: self._load_values_changed())
            position.trace_add("write", lambda *_: self._load_values_changed())
            frame.magnitude = magnitude
            frame.position = position
            row = ttk.Frame(frame)
            row.pack(fill="x")
            ttk.Label(row, text="kips").grid(row=0, column=0, sticky="w")
            ttk.Entry(row, textvariable=magnitude, width=8).grid(
                row=0, column=1, padx=(4, 8)
            )
            ttk.Label(row, text="ft").grid(row=0, column=2, sticky="w")
            ttk.Entry(row, textvariable=position, width=8).grid(
                row=0, column=3, padx=(4, 0)
            )
            ttk.Button(
                frame, text="Remove",
                command=lambda i=index: self._remove_point_load(i)
            ).pack(anchor="e", pady=(4, 0))

        for index, load in enumerate(self.uniform_loads):
            frame = ttk.LabelFrame(
                self.load_rows, text=f"Uniform load {index + 1}", padding=6
            )
            frame.pack(fill="x", pady=(0, 6))
            magnitude = tk.StringVar(value=str(load.magnitude_kips_per_ft))
            start = tk.StringVar(value=str(load.start_ft))
            end = tk.StringVar(value=str(load.end_ft))
            for variable in (magnitude, start, end):
                variable.trace_add("write", lambda *_: self._load_values_changed())
            frame.magnitude = magnitude
            frame.start = start
            frame.end = end
            ttk.Label(frame, text="Magnitude (kips/ft)").pack(anchor="w")
            ttk.Entry(frame, textvariable=magnitude).pack(fill="x", pady=(0, 4))
            ttk.Label(frame, text="Start - end (ft)").pack(anchor="w")
            endpoints = ttk.Frame(frame)
            endpoints.pack(fill="x")
            ttk.Entry(endpoints, textvariable=start, width=8).pack(
                side="left", padx=(0, 5)
            )
            ttk.Entry(endpoints, textvariable=end, width=8).pack(side="left")
            ttk.Button(
                frame, text="Remove",
                command=lambda i=index: self._remove_uniform_load(i)
            ).pack(anchor="e", pady=(4, 0))

    def _add_point_load(self):
        span = self._parse_span()
        position = span / 2
        if self.support_var.get() == "Cantilever":
            position = span
        self.point_loads.append(PointLoad(5.0, position))
        self._refresh_load_rows()
        self.schedule_recalculate()

    def _add_uniform_load(self):
        span = self._parse_span()
        self.uniform_loads.append(UniformLoad(0.5, 0.0, span))
        self._refresh_load_rows()
        self.schedule_recalculate()

    def _remove_point_load(self, index):
        if 0 <= index < len(self.point_loads):
            del self.point_loads[index]
        self._refresh_load_rows()
        self.schedule_recalculate()

    def _remove_uniform_load(self, index):
        if 0 <= index < len(self.uniform_loads):
            del self.uniform_loads[index]
        self._refresh_load_rows()
        self.schedule_recalculate()

    def _load_values_changed(self):
        self.schedule_recalculate()

    def _parse_span(self):
        try:
            span = float(self.span_var.get())
            if 4 <= span <= 40:
                return span
        except ValueError:
            pass
        return 20.0

    def _read_load_values(self):
        point_loads = []
        uniform_loads = []
        try:
            span = float(self.span_var.get())
            if not 4 <= span <= 40:
                raise ValueError("Span must be between 4 and 40 ft.")

            for index, frame in enumerate(self.load_rows.winfo_children()):
                if frame.cget("text").startswith("Point"):
                    magnitude = float(frame.magnitude.get())
                    position = float(frame.position.get())
                    if not 0 <= position <= span:
                        raise ValueError(
                            "Point-load position must be from 0 to the span."
                        )
                    point_loads.append(PointLoad(magnitude, position))
            for frame in self.load_rows.winfo_children():
                if frame.cget("text").startswith("Uniform"):
                    magnitude = float(frame.magnitude.get())
                    start = float(frame.start.get())
                    end = float(frame.end.get())
                    if end < start:
                        raise ValueError("Uniform-load start must be before end.")
                    uniform_loads.append(
                        UniformLoad(magnitude, start, end)
                    )
            return span, tuple(point_loads), tuple(uniform_loads)
        except ValueError as error:
            raise ValueError(str(error)) from error

    def _current_beam(self):
        span, point_loads, uniform_loads = self._read_load_values()
        return BeamInput(
            support_type=self.support_var.get(),
            span_ft=span,
            point_loads=point_loads,
            uniform_loads=uniform_loads,
            section_name=self.section_var.get(),
            deflection_divisor=240 if self.limit_var.get() == "L/240" else 360,
        )

    def _save_beam(self):
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save beam",
            defaultextension=".beam",
            filetypes=(("Beam Designer files", "*.beam"), ("JSON files", "*.json")),
        )
        if not path:
            return
        try:
            beam = self._current_beam()
            with open(path, "w", encoding="utf-8") as beam_file:
                json.dump(beam_to_dict(beam), beam_file, indent=2, allow_nan=False)
                beam_file.write("\n")
        except (OSError, ValueError, TypeError) as error:
            messagebox.showerror("Could not save beam", str(error), parent=self.root)

    def _open_beam(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open beam",
            filetypes=(("Beam Designer files", "*.beam"), ("JSON files", "*.json")),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as beam_file:
                beam = beam_from_dict(json.load(beam_file))
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
            messagebox.showerror("Could not open beam", str(error), parent=self.root)
            return

        self.support_var.set(beam.support_type)
        self.span_var.set(str(beam.span_ft))
        self.span_slider.set(beam.span_ft)
        self.material_var.set(get_section(beam.section_name).material)
        self._refresh_sections()
        self.section_var.set(beam.section_name)
        self.limit_var.set(f"L/{beam.deflection_divisor}")
        self.point_loads = list(beam.point_loads)
        self.uniform_loads = list(beam.uniform_loads)
        self._refresh_load_rows()
        self.schedule_recalculate()

    def _export_results_csv(self):
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export beam results",
            defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"),),
        )
        if not path:
            return
        try:
            result = analyze(self._current_beam())
            with open(path, "w", newline="", encoding="utf-8-sig") as csv_file:
                write_results_csv(csv_file, result)
            messagebox.showinfo(
                "Results exported", f"CSV saved to:\n{path}", parent=self.root
            )
        except (OSError, ValueError, TypeError, csv.Error) as error:
            messagebox.showerror(
                "Could not export results", str(error), parent=self.root
            )

    def _save_calculation_pdf(self):
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save calculation sheet",
            defaultextension=".pdf",
            filetypes=(("PDF files", "*.pdf"),),
        )
        if not path:
            return
        try:
            beam = self._current_beam()
            result = analyze(beam)
            write_calculation_pdf(path, beam, result)
            messagebox.showinfo(
                "Calculation sheet saved",
                f"PDF saved to:\n{path}",
                parent=self.root,
            )
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            messagebox.showerror(
                "Could not save calculation sheet",
                str(error),
                parent=self.root,
            )

    def schedule_recalculate(self):
        if self.recalc_after_id is not None:
            self.root.after_cancel(self.recalc_after_id)
        self.recalc_after_id = self.root.after(120, self.recalculate)

    def recalculate(self):
        self.recalc_after_id = None
        try:
            span, point_loads, uniform_loads = self._read_load_values()
            divisor = 240 if self.limit_var.get() == "L/240" else 360
            beam = BeamInput(
                support_type=self.support_var.get(),
                span_ft=span,
                point_loads=point_loads,
                uniform_loads=uniform_loads,
                section_name=self.section_var.get(),
                deflection_divisor=divisor,
            )
            result = analyze(beam)
            self.view.update(beam, result)
            self._update_cards(result)
            self.status_label.configure(
                text="", foreground="#B71C1C"
            )
        except (ValueError, TypeError) as error:
            self.status_label.configure(
                text=str(error), foreground="#B71C1C"
            )

    def _update_cards(self, result):
        bending_ratio = (
            result.bending_stress_ksi / result.allowable_bending_stress_ksi
        )
        deflection_ratio = (
            result.max_deflection_in / result.deflection_allowance_in
        )
        bending_pass = "PASS" if result.bending_pass else "FAIL"
        deflection_pass = "PASS" if result.deflection_pass else "FAIL"

        self.bending_card.value_label.configure(
            text=f"{result.bending_stress_ksi:.3f} / "
                 f"{result.allowable_bending_stress_ksi:.3f} ksi"
        )
        self.bending_card.ratio_label.configure(
            text=f"{bending_ratio:.0%}  {bending_pass}"
        )
        self.bending_card.bar.configure(
            value=min(bending_ratio * 100, 100)
        )

        self.deflection_card.value_label.configure(
            text=f"{result.max_deflection_in:.3f} / "
                 f"{result.deflection_allowance_in:.3f} in"
        )
        self.deflection_card.ratio_label.configure(
            text=f"{deflection_ratio:.0%}  {deflection_pass}"
        )
        self.deflection_card.bar.configure(
            value=min(deflection_ratio * 100, 100)
        )

        suggested = result.suggested_section
        self.suggested_section = suggested
        if suggested is None:
            self.suggestion_label.configure(text="No passing section")
            self.use_button.configure(state="disabled")
        else:
            self.suggestion_label.configure(text=suggested.name)
            self.use_button.configure(state="normal")

    def _use_suggested(self):
        if self.suggested_section is not None:
            self.section_var.set(self.suggested_section.name)

    def _drag_point_load(self, index, position):
        if 0 <= index < len(self.point_loads):
            old = self.point_loads[index]
            self.point_loads[index] = PointLoad(
                old.magnitude_kips, position
            )
            self._refresh_load_rows()
            self.schedule_recalculate()


def main():
    root = tk.Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    BeamDesignerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
