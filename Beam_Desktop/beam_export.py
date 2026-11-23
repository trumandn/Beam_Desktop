import csv


def write_results_csv(stream, result):
    writer = csv.writer(stream)
    writer.writerow((
        "Position x (ft)",
        "Shear V (kips)",
        "Moment M (kip-ft)",
        "Deflection (in)",
    ))
    writer.writerows(zip(
        result.x_ft,
        result.shear_kips,
        result.moment_kip_ft,
        result.deflection_in,
    ))
