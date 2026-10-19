"""Generate reproducible SUMO/TraCI mobility traces for the V2I project."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VEHICLE_START_RANGE_M = (100.0, 800.0)
SIMULATION_STEP_S = 0.05
DEFAULT_COUNTS = (5, 10, 20, 50, 100)


def _load_traci():
    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        tools_directory = Path(sumo_home) / "tools"
        if tools_directory.is_dir():
            sys.path.insert(0, str(tools_directory))

    try:
        import traci
    except ImportError as exc:
        raise RuntimeError(
            "TraCI could not be imported. Install SUMO and set SUMO_HOME "
            "to its installation directory."
        ) from exc
    return traci


def _sumo_executable() -> str:
    executable = shutil.which("sumo")
    if executable:
        return executable

    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        candidate = Path(sumo_home) / "bin" / (
            "sumo.exe" if os.name == "nt" else "sumo"
        )
        if candidate.is_file():
            return str(candidate)

    raise RuntimeError(
        "SUMO could not be found. Add its bin directory to PATH or set SUMO_HOME."
    )


def _parse_counts(value: str) -> tuple[int, ...]:
    try:
        counts = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Counts must be comma-separated positive integers."
        ) from exc
    if not counts or any(count <= 0 for count in counts):
        raise argparse.ArgumentTypeError(
            "Counts must be comma-separated positive integers."
        )
    if any(count not in DEFAULT_COUNTS for count in counts):
        raise argparse.ArgumentTypeError(
            f"Each count must be one of: {', '.join(map(str, DEFAULT_COUNTS))}."
        )
    return counts


def generate_traces(
    counts: tuple[int, ...],
    duration_s: float,
    seed: int,
    output_path: Path,
) -> int:
    traci = _load_traci()
    sumo = _sumo_executable()
    config = ROOT / "network" / "corridor.sumocfg"
    steps = round(duration_s / SIMULATION_STEP_S)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(
            (
                "vehicle_count",
                "time_s",
                "vehicle_id",
                "x_m",
                "y_m",
                "speed_mps",
                "heading_deg",
                "acceleration_mps2",
            )
        )

        for vehicle_count in counts:
            traci.start(
                [
                    sumo,
                    "-c",
                    str(config),
                    "--seed",
                    str(seed),
                    "--no-step-log",
                    "true",
                    "--duration-log.disable",
                    "true",
                ]
            )
            try:
                for index in range(vehicle_count):
                    position_m = VEHICLE_START_RANGE_M[0] + (
                        (index + 0.5)
                        * (VEHICLE_START_RANGE_M[1] - VEHICLE_START_RANGE_M[0])
                        / vehicle_count
                    )
                    traci.vehicle.add(
                        f"veh{index}",
                        "r0",
                        typeID="car",
                        depart="now",
                        departLane=str(index % 2),
                        departPos=f"{position_m:.3f}",
                        departSpeed="5",
                    )

                for _ in range(steps):
                    traci.simulationStep()
                    time_s = traci.simulation.getTime()
                    for vehicle_id in sorted(traci.vehicle.getIDList()):
                        x_m, y_m = traci.vehicle.getPosition(vehicle_id)
                        writer.writerow(
                            (
                                vehicle_count,
                                f"{time_s:.2f}",
                                vehicle_id,
                                f"{x_m:.3f}",
                                f"{y_m:.3f}",
                                f"{traci.vehicle.getSpeed(vehicle_id):.3f}",
                                f"{traci.vehicle.getAngle(vehicle_id):.2f}",
                                f"{traci.vehicle.getAcceleration(vehicle_id):.3f}",
                            )
                        )
                        rows_written += 1
            finally:
                traci.close()

    return rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--counts",
        type=_parse_counts,
        default=DEFAULT_COUNTS,
        help="Vehicle counts to simulate (default: 5,10,20,50,100).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Duration of each scenario in seconds (default: 10).",
    )
    parser.add_argument("--seed", type=int, default=42, help="SUMO random seed.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "mobility_traces.csv",
        help="CSV output path.",
    )
    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("--duration must be greater than zero.")
    step_count = args.duration / SIMULATION_STEP_S
    if abs(step_count - round(step_count)) > 1e-9:
        parser.error("--duration must be a multiple of the 0.05-second simulation step.")

    try:
        rows_written = generate_traces(args.counts, args.duration, args.seed, args.output)
    except (OSError, RuntimeError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Wrote {rows_written} mobility samples to {args.output}")


if __name__ == "__main__":
    main()
