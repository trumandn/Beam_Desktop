import csv
import io
import os
import tempfile
import unittest

from beam_analysis import (
    BeamInput,
    PointLoad,
    UniformLoad,
    analyze,
    beam_from_dict,
    beam_to_dict,
)
from beam_export import write_results_csv
from beam_report import write_calculation_pdf


class BeamAnalysisTests(unittest.TestCase):
    def test_full_span_uniform_load(self):
        result = analyze(BeamInput(
            support_type="Simply supported",
            span_ft=20,
            point_loads=(),
            uniform_loads=(UniformLoad(1.0, 0.0, 20.0),),
            section_name="W12x26",
        ))
        self.assertAlmostEqual(result.left_reaction_kips, 10.0, places=2)
        self.assertAlmostEqual(result.right_reaction_kips, 10.0, places=2)
        self.assertAlmostEqual(result.max_moment_kip_ft, 50.0, places=1)
        self.assertAlmostEqual(result.bending_stress_ksi, 17.96, places=1)
        self.assertAlmostEqual(result.max_deflection_in, 0.609, places=2)
        self.assertTrue(result.bending_pass)
        self.assertTrue(result.deflection_pass)

    def test_centered_point_load(self):
        result = analyze(BeamInput(
            support_type="Simply supported",
            span_ft=20,
            point_loads=(PointLoad(10.0, 5.0),),
            uniform_loads=(),
            section_name="W12x26",
        ))
        self.assertAlmostEqual(result.left_reaction_kips, 7.5, places=2)
        self.assertAlmostEqual(result.right_reaction_kips, 2.5, places=2)
        self.assertAlmostEqual(result.max_moment_kip_ft, 37.5, places=1)
        self.assertAlmostEqual(result.bending_stress_ksi, 13.47, places=1)
        self.assertAlmostEqual(result.max_deflection_in, 0.340, delta=0.01)

    def test_cantilever_free_end_point_load(self):
        result = analyze(BeamInput(
            support_type="Cantilever",
            span_ft=10,
            point_loads=(PointLoad(5.0, 10.0),),
            uniform_loads=(),
            section_name="W12x26",
        ))
        self.assertAlmostEqual(result.left_reaction_kips, 5.0, places=2)
        self.assertAlmostEqual(abs(result.fixed_end_moment_kip_ft), 50.0, places=1)
        self.assertAlmostEqual(result.max_deflection_in, 0.487, places=2)
        self.assertFalse(result.deflection_pass)

    def test_lumber_uniform_load(self):
        result = analyze(BeamInput(
            support_type="Simply supported",
            span_ft=12,
            point_loads=(),
            uniform_loads=(UniformLoad(0.05, 0.0, 12.0),),
            section_name="2x10",
        ))
        self.assertAlmostEqual(result.max_moment_kip_ft, 0.90, places=1)
        self.assertAlmostEqual(result.bending_stress_ksi, 0.505, places=2)
        self.assertAlmostEqual(result.max_deflection_in, 0.147, places=2)
        self.assertTrue(result.bending_pass)
        self.assertTrue(result.deflection_pass)

    def test_partially_loaded_beam(self):
        result = analyze(BeamInput(
            support_type="Simply supported",
            span_ft=30,
            point_loads=(),
            uniform_loads=(UniformLoad(2.0, 0.0, 15.0),),
            section_name="W18x35",
        ))
        self.assertAlmostEqual(result.left_reaction_kips, 22.5, places=2)
        self.assertAlmostEqual(result.right_reaction_kips, 7.5, places=2)
        self.assertAlmostEqual(result.max_moment_kip_ft, 126.6, places=1)
        self.assertAlmostEqual(result.max_moment_location_ft, 11.25, places=1)

    def test_zero_load(self):
        result = analyze(BeamInput(
            support_type="Simply supported",
            span_ft=20,
            point_loads=(),
            uniform_loads=(),
            section_name="W12x26",
        ))
        self.assertEqual(result.left_reaction_kips, 0)
        self.assertEqual(result.right_reaction_kips, 0)
        self.assertEqual(result.max_moment_kip_ft, 0)
        self.assertEqual(result.max_deflection_in, 0)

    def test_beam_file_round_trip(self):
        beam = BeamInput(
            support_type="Cantilever",
            span_ft=12.5,
            point_loads=(PointLoad(3.25, 12.5),),
            uniform_loads=(UniformLoad(0.75, 1.0, 9.5),),
            section_name="2x10",
            deflection_divisor=240,
        )
        self.assertEqual(beam_from_dict(beam_to_dict(beam)), beam)

    def test_beam_file_rejects_out_of_span_point_load(self):
        data = {
            "format_version": 1,
            "support_type": "Simply supported",
            "span_ft": 10,
            "section_name": "W12x26",
            "deflection_divisor": 360,
            "point_loads": [{"magnitude_kips": 1, "position_ft": 11}],
            "uniform_loads": [],
        }
        with self.assertRaisesRegex(ValueError, "within the span"):
            beam_from_dict(data)

    def test_csv_export_contains_sampled_results_and_units(self):
        result = analyze(BeamInput(
            support_type="Simply supported",
            span_ft=4,
            point_loads=(PointLoad(2, 1.1),),
            uniform_loads=(),
            section_name="W12x26",
        ))
        output = io.StringIO(newline="")
        write_results_csv(output, result)
        rows = list(csv.reader(io.StringIO(output.getvalue())))
        self.assertEqual(
            rows[0],
            [
                "Position x (ft)",
                "Shear V (kips)",
                "Moment M (kip-ft)",
                "Deflection (in)",
            ],
        )
        self.assertEqual(len(rows), len(result.x_ft) + 1)
        positions = [float(row[0]) for row in rows[1:]]
        self.assertIn(1.1, positions)

    def test_calculation_sheet_pdf_is_generated(self):
        beam = BeamInput(
            support_type="Simply supported",
            span_ft=8,
            point_loads=(PointLoad(2, 3),),
            uniform_loads=(),
            section_name="W12x26",
        )
        result = analyze(beam)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "calculation-sheet.pdf")
            write_calculation_pdf(path, beam, result)
            with open(path, "rb") as pdf_file:
                self.assertEqual(pdf_file.read(4), b"%PDF")
            self.assertGreater(os.path.getsize(path), 1000)


if __name__ == "__main__":
    unittest.main()
