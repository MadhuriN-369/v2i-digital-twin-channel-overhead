"""Find the vehicle density at which V2I channel utilisation crosses 60%.

This script uses the existing mobility traces and the same channel model as
run_experiments.py.  Because channel utilisation scales linearly with vehicle
count (each vehicle's airtime depends only on its distance to the nearest RSU,
not on how many other vehicles are present), the script:

  1. Runs the experiment at the existing 100-vehicle trace to measure the
     per-vehicle airtime contribution.
  2. Extrapolates linearly to find the exact vehicle count at which the
     offered utilisation crosses 60%.
  3. Validates the linear assumption by checking the per-vehicle rate across
     all five existing densities (5, 10, 20, 50, 100).
  4. Writes the threshold results to results/saturation_search/.

Usage (from project root):
    .venv/Scripts/python.exe -m src.find_saturation
    .venv/Scripts/python.exe -m src.find_saturation --payload-bytes 64 --path-loss-exponent 3.5
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

from .channel_model import RadioParameters, link_budget, packet_airtime_s
from .run_experiments import (
    SATURATION_THRESHOLD_PERCENT,
    UPLOAD_INTERVALS_MS,
    VehicleTrace,
    load_traces,
    run_scenario,
    _aggregate_repeats,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACE = ROOT / "data" / "mobility_traces.csv"
RESULTS_DIRECTORY = ROOT / "results"
DEFAULT_SEED = 42


def find_threshold(
    traces: dict[int, dict[str, VehicleTrace]],
    duration_s: float,
    interval_ms: int,
    radio: RadioParameters,
    payload_bytes: int,
    seed: int,
    repeats: int,
) -> dict:
    """Compute utilisation at all tested densities and extrapolate the 60% crossing."""

    densities = sorted(traces.keys())
    per_density = []

    for count in densities:
        runs = [
            run_scenario(
                count,
                traces[count],
                duration_s,
                interval_ms,
                radio,
                seed + count * 100_000 + interval_ms * 100 + r,
                payload_bytes,
            )
            for r in range(repeats)
        ]
        agg = _aggregate_repeats(runs)
        util = float(agg["channel_utilisation_percent"])
        per_vehicle = util / count
        per_density.append({
            "vehicle_count": count,
            "utilisation_percent": util,
            "per_vehicle_utilisation": per_vehicle,
            "pdr_percent": float(agg["packet_delivery_ratio_percent"]),
        })

    # Linear fit: utilisation = slope * vehicle_count
    xs = np.array([d["vehicle_count"] for d in per_density], dtype=float)
    ys = np.array([d["utilisation_percent"] for d in per_density], dtype=float)
    # Force through origin since 0 vehicles = 0 utilisation
    slope = float(np.sum(xs * ys) / np.sum(xs * xs))

    # Also compute unforced linear regression for validation
    coeffs = np.polyfit(xs, ys, 1)
    r_squared = float(1.0 - np.sum((ys - np.polyval(coeffs, xs))**2) /
                       np.sum((ys - np.mean(ys))**2))

    # Threshold extrapolation
    if slope > 0:
        threshold_count = math.ceil(SATURATION_THRESHOLD_PERCENT / slope)
    else:
        threshold_count = None

    # Check if any tested density already crosses
    crossed_at = next(
        (d["vehicle_count"] for d in per_density
         if d["utilisation_percent"] > SATURATION_THRESHOLD_PERCENT),
        None,
    )

    return {
        "upload_interval_ms": interval_ms,
        "payload_bytes": payload_bytes,
        "path_loss_exponent": radio.path_loss_exponent,
        "per_density_results": per_density,
        "slope_per_vehicle": slope,
        "r_squared": r_squared,
        "threshold_vehicle_count": crossed_at or threshold_count,
        "threshold_source": "measured" if crossed_at else "extrapolated",
        "max_tested_vehicles": max(densities),
        "max_tested_utilisation": per_density[-1]["utilisation_percent"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--path-loss-exponent", type=float, default=3.5,
                        help="Path-loss exponent (default: 3.5 for worst case).")
    parser.add_argument("--payload-bytes", type=int, choices=(32, 64), default=64,
                        help="Telemetry payload (default: 64 for worst case).")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output-directory", type=Path,
                        default=RESULTS_DIRECTORY / "saturation_search")
    args = parser.parse_args()

    radio = RadioParameters(path_loss_exponent=args.path_loss_exponent)
    traces, duration_s = load_traces(args.trace)

    print("=" * 65)
    print(f"  SATURATION THRESHOLD SEARCH")
    print(f"  {args.payload_bytes}B payload, alpha={args.path_loss_exponent}, "
          f"{args.repeats} repeats")
    print("=" * 65)

    all_sweep_rows = []
    threshold_rows = []

    for interval_ms in UPLOAD_INTERVALS_MS:
        print(f"\n--- {interval_ms} ms upload interval ---")
        result = find_threshold(
            traces, duration_s, interval_ms, radio,
            args.payload_bytes, args.seed, args.repeats,
        )

        # Print per-density results
        print(f"  {'Vehicles':>8}  {'Util%':>8}  {'Per-veh%':>10}  {'PDR%':>8}")
        for d in result["per_density_results"]:
            print(f"  {d['vehicle_count']:>8}  {d['utilisation_percent']:>8.4f}  "
                  f"{d['per_vehicle_utilisation']:>10.6f}  {d['pdr_percent']:>8.2f}")

        print(f"\n  Linear fit: util = {result['slope_per_vehicle']:.6f} * N_vehicles"
              f"  (R^2 = {result['r_squared']:.6f})")

        threshold = result["threshold_vehicle_count"]
        if threshold:
            print(f"  >> 60% threshold: ~{threshold} vehicles ({result['threshold_source']})")
        else:
            print(f"  >> 60% threshold: not reachable")

        # Collect CSV rows
        for d in result["per_density_results"]:
            all_sweep_rows.append({
                "upload_interval_ms": interval_ms,
                "payload_bytes": args.payload_bytes,
                "path_loss_exponent": args.path_loss_exponent,
                "vehicle_count": d["vehicle_count"],
                "utilisation_percent": d["utilisation_percent"],
                "per_vehicle_utilisation_percent": d["per_vehicle_utilisation"],
                "pdr_percent": d["pdr_percent"],
            })

        threshold_rows.append({
            "upload_interval_ms": interval_ms,
            "payload_bytes": args.payload_bytes,
            "path_loss_exponent": args.path_loss_exponent,
            "slope_per_vehicle": result["slope_per_vehicle"],
            "r_squared": result["r_squared"],
            "threshold_vehicle_count": threshold or "",
            "threshold_source": result["threshold_source"],
            "max_tested_vehicles": result["max_tested_vehicles"],
            "max_tested_utilisation_percent": result["max_tested_utilisation"],
        })

    # Write CSVs
    args.output_directory.mkdir(parents=True, exist_ok=True)

    sweep_path = args.output_directory / "saturation_sweep.csv"
    with sweep_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_sweep_rows[0]))
        writer.writeheader()
        writer.writerows(all_sweep_rows)

    thresh_path = args.output_directory / "saturation_thresholds_extended.csv"
    with thresh_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(threshold_rows[0]))
        writer.writeheader()
        writer.writerows(threshold_rows)

    # Final summary
    print("\n" + "=" * 65)
    print("  SATURATION THRESHOLD SUMMARY")
    print("=" * 65)
    for t in threshold_rows:
        count = t["threshold_vehicle_count"]
        src = t["threshold_source"]
        if count:
            print(f"  {t['upload_interval_ms']:>4}ms interval: "
                  f"~{count} vehicles ({src})")
        else:
            print(f"  {t['upload_interval_ms']:>4}ms interval: not reachable")
    print(f"\n  Config: {args.payload_bytes}B, alpha={args.path_loss_exponent}")
    print(f"  Wrote: {sweep_path}")
    print(f"  Wrote: {thresh_path}")


if __name__ == "__main__":
    main()
