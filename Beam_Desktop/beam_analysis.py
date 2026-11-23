from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np


@dataclass(frozen=True)
class PointLoad:
    magnitude_kips: float
    position_ft: float


@dataclass(frozen=True)
class UniformLoad:
    magnitude_kips_per_ft: float
    start_ft: float
    end_ft: float


@dataclass(frozen=True)
class Section:
    name: str
    material: str
    e_ksi: float
    fb_ksi: float
    ix_in4: float
    sx_in3: float
    weight_lb_per_ft: Optional[float] = None


STEEL_SECTIONS = (
    Section("W8x10", "Steel", 29000, 30, 30.8, 7.81, 10),
    Section("W10x12", "Steel", 29000, 30, 53.8, 10.9, 12),
    Section("W12x26", "Steel", 29000, 30, 204, 33.4, 26),
    Section("W14x22", "Steel", 29000, 30, 199, 29.0, 22),
    Section("W16x26", "Steel", 29000, 30, 301, 38.4, 26),
    Section("W18x35", "Steel", 29000, 30, 510, 57.6, 35),
    Section("W21x44", "Steel", 29000, 30, 843, 81.6, 44),
    Section("W24x55", "Steel", 29000, 30, 1350, 114, 55),
)

LUMBER_SECTIONS = (
    Section("2x8", "Lumber", 1600, 0.900, 47.63, 13.14),
    Section("2x10", "Lumber", 1600, 0.900, 98.93, 21.39),
    Section("2x12", "Lumber", 1600, 0.900, 177.98, 31.64),
)


@dataclass(frozen=True)
class BeamInput:
    support_type: str
    span_ft: float
    point_loads: tuple[PointLoad, ...]
    uniform_loads: tuple[UniformLoad, ...]
    section_name: str
    deflection_divisor: int = 360


@dataclass(frozen=True)
class AnalysisResult:
    x_ft: np.ndarray
    shear_kips: np.ndarray
    moment_kip_ft: np.ndarray
    deflection_in: np.ndarray
    left_reaction_kips: float
    right_reaction_kips: float
    fixed_end_moment_kip_ft: float
    max_shear_kips: float
    max_moment_kip_ft: float
    max_moment_location_ft: float
    max_deflection_in: float
    max_deflection_location_ft: float
    bending_stress_ksi: float
    allowable_bending_stress_ksi: float
    deflection_allowance_in: float
    bending_pass: bool
    deflection_pass: bool
    section: Section
    suggested_section: Optional[Section]


def get_sections(material: str) -> tuple[Section, ...]:
    return STEEL_SECTIONS if material.lower() == "steel" else LUMBER_SECTIONS


def get_section(name: str) -> Section:
    for section in STEEL_SECTIONS + LUMBER_SECTIONS:
        if section.name == name:
            return section
    raise ValueError("Unknown section: " + name)


def _clip_uniform_loads(
    loads: Iterable[UniformLoad], span_ft: float
) -> tuple[UniformLoad, ...]:
    clipped = []
    for load in loads:
        start = min(max(load.start_ft, 0.0), span_ft)
        end = min(max(load.end_ft, 0.0), span_ft)
        if end > start:
            clipped.append(
                UniformLoad(load.magnitude_kips_per_ft, start, end)
            )
    return tuple(clipped)


def _sample_grid(span_ft: float, point_loads: Iterable[PointLoad],
                 uniform_loads: Iterable[UniformLoad]) -> np.ndarray:
    points = [0.0, span_ft]
    points.extend(np.arange(0.25, span_ft, 0.25).tolist())
    points.extend(load.position_ft for load in point_loads)
    for load in uniform_loads:
        points.extend((load.start_ft, load.end_ft))
    return np.array(sorted(set(round(x, 10) for x in points)), dtype=float)


def _quadratic_location(x: np.ndarray, y: np.ndarray, index: int) -> tuple[float, float]:
    if index <= 0 or index >= len(x) - 1:
        return float(x[index]), float(y[index])
    dx = np.array([x[index - 1], x[index], x[index + 1]], dtype=float)
    dy = np.array([y[index - 1], y[index], y[index + 1]], dtype=float)
    if np.all(dy == dy[1]):
        return float(x[index]), float(y[index])
    coefficients = np.polyfit(dx, dy, 2)
    if abs(coefficients[0]) < 1e-12:
        return float(x[index]), float(y[index])
    location = -coefficients[1] / (2 * coefficients[0])
    if not dx[0] <= location <= dx[-1]:
        return float(x[index]), float(y[index])
    value = np.polyval(coefficients, location)
    return float(location), float(value)


def analyze(beam: BeamInput) -> AnalysisResult:
    if beam.support_type not in ("Simply supported", "Cantilever"):
        raise ValueError("Support type must be Simply supported or Cantilever")
    if beam.span_ft < 4 or beam.span_ft > 40:
        raise ValueError("Span must be between 4 and 40 ft")
    if beam.deflection_divisor not in (240, 360):
        raise ValueError("Deflection divisor must be 240 or 360")

    section = get_section(beam.section_name)
    span = beam.span_ft
    point_loads = tuple(
        load for load in beam.point_loads
        if -0.0001 <= load.position_ft <= span + 0.0001
    )
    uniform_loads = _clip_uniform_loads(beam.uniform_loads, span)

    total_load = sum(load.magnitude_kips for load in point_loads)
    total_moment = sum(
        load.magnitude_kips * load.position_ft for load in point_loads
    )
    for load in uniform_loads:
        length = load.end_ft - load.start_ft
        load_total = load.magnitude_kips_per_ft * length
        first_moment = load.magnitude_kips_per_ft * (
            (load.end_ft ** 2 - load.start_ft ** 2) / 2
        )
        total_load += load_total
        total_moment += first_moment

    if beam.support_type == "Simply supported":
        right_reaction = total_moment / span
        left_reaction = total_load - right_reaction
        fixed_moment = 0.0
    else:
        left_reaction = total_load
        right_reaction = 0.0
        fixed_moment = -total_moment

    x = _sample_grid(span, point_loads, uniform_loads)
    shear = np.zeros_like(x)
    moment = np.zeros_like(x)

    for i, xi in enumerate(x):
        if beam.support_type == "Simply supported":
            v = left_reaction
            m = left_reaction * xi
            for load in point_loads:
                if xi > load.position_ft:
                    v -= load.magnitude_kips
                    m -= load.magnitude_kips * (xi - load.position_ft)
            for load in uniform_loads:
                if xi > load.start_ft:
                    loaded_length = min(
                        xi - load.start_ft,
                        load.end_ft - load.start_ft,
                    )
                    v -= load.magnitude_kips_per_ft * loaded_length
                    if xi <= load.end_ft:
                        m -= (
                            load.magnitude_kips_per_ft
                            * loaded_length ** 2 / 2
                        )
                    else:
                        full_length = load.end_ft - load.start_ft
                        centroid = (
                            load.start_ft + load.end_ft
                        ) / 2
                        m -= (
                            load.magnitude_kips_per_ft
                            * full_length
                            * (xi - centroid)
                        )
        else:
            v = 0.0
            m = 0.0
            for load in point_loads:
                if load.position_ft >= xi:
                    v -= load.magnitude_kips
                    m -= load.magnitude_kips * (load.position_ft - xi)
            for load in uniform_loads:
                overlap_start = max(load.start_ft, xi)
                overlap_end = load.end_ft
                if overlap_end > overlap_start:
                    overlap_length = overlap_end - overlap_start
                    v -= load.magnitude_kips_per_ft * overlap_length
                    centroid = (overlap_start + overlap_end) / 2
                    m -= (
                        load.magnitude_kips_per_ft
                        * overlap_length
                        * (centroid - xi)
                    )
        shear[i] = v
        moment[i] = m

    x_in = x * 12.0
    curvature = moment * 12.0 / (section.e_ksi * section.ix_in4)
    theta = np.zeros_like(x_in)
    deflection = np.zeros_like(x_in)

    for i in range(1, len(x_in)):
        dx = x_in[i] - x_in[i - 1]
        theta[i] = theta[i - 1] + 0.5 * (
            curvature[i - 1] + curvature[i]
        ) * dx
        deflection[i] = deflection[i - 1] + 0.5 * (
            theta[i - 1] + theta[i]
        ) * dx

    if beam.support_type == "Simply supported":
        theta_correction = deflection[-1] / x_in[-1]
        deflection = deflection - theta_correction * x_in
    else:
        fixed_correction = theta[0]
        deflection = deflection - fixed_correction * x_in

    max_shear_index = int(np.argmax(np.abs(shear)))
    max_moment_index = int(np.argmax(np.abs(moment)))
    max_deflection_index = int(np.argmax(np.abs(deflection)))

    max_moment_location = float(x[max_moment_index])
    max_moment_value = float(moment[max_moment_index])
    max_deflection_location, max_deflection_value = _quadratic_location(
        x, deflection, max_deflection_index
    )

    max_shear = float(np.abs(shear[max_shear_index]))
    max_moment = abs(float(max_moment_value))
    max_deflection = abs(float(max_deflection_value))
    bending_stress = max_moment * 12.0 / section.sx_in3
    deflection_allowance = span * 12.0 / beam.deflection_divisor
    bending_pass = bending_stress <= section.fb_ksi
    deflection_pass = max_deflection <= deflection_allowance

    sections = get_sections(section.material)
    suggested = None
    candidates = []
    for candidate in sections:
        candidate_stress = max_moment * 12.0 / candidate.sx_in3
        candidate_deflection = _deflection_for_section(
            beam.support_type, span, x, moment, candidate
        )
        candidate_pass = (
            candidate_stress <= candidate.fb_ksi
            and np.max(np.abs(candidate_deflection)) <= deflection_allowance
        )
        if candidate_pass:
            candidates.append(candidate)

    if candidates:
        if section.material == "Steel":
            weight_sorted = sorted(
                candidates,
                key=lambda item: (
                    item.weight_lb_per_ft if item.weight_lb_per_ft is not None else 1e9,
                    -(item.ix_in4),
                ),
            )
            suggested = weight_sorted[0]
        else:
            suggested = candidates[0]

    return AnalysisResult(
        x_ft=x,
        shear_kips=shear,
        moment_kip_ft=moment,
        deflection_in=deflection,
        left_reaction_kips=left_reaction,
        right_reaction_kips=right_reaction,
        fixed_end_moment_kip_ft=fixed_moment,
        max_shear_kips=max_shear,
        max_moment_kip_ft=max_moment,
        max_moment_location_ft=max_moment_location,
        max_deflection_in=max_deflection,
        max_deflection_location_ft=max_deflection_location,
        bending_stress_ksi=bending_stress,
        allowable_bending_stress_ksi=section.fb_ksi,
        deflection_allowance_in=deflection_allowance,
        bending_pass=bending_pass,
        deflection_pass=deflection_pass,
        section=section,
        suggested_section=suggested,
    )


def _deflection_for_section(
    support_type: str,
    span_ft: float,
    x: np.ndarray,
    moment_kip_ft: np.ndarray,
    section: Section,
) -> np.ndarray:
    x_in = x * 12.0
    curvature = moment_kip_ft * 12.0 / (
        section.e_ksi * section.ix_in4
    )
    theta = np.zeros_like(x_in)
    deflection = np.zeros_like(x_in)
    for i in range(1, len(x_in)):
        dx = x_in[i] - x_in[i - 1]
        theta[i] = theta[i - 1] + 0.5 * (
            curvature[i - 1] + curvature[i]
        ) * dx
        deflection[i] = deflection[i - 1] + 0.5 * (
            theta[i - 1] + theta[i]
        ) * dx

    if support_type == "Simply supported":
        deflection = deflection - (deflection[-1] / x_in[-1]) * x_in
    return deflection
