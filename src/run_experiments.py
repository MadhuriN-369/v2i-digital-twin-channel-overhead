"""Run reproducible telemetry-overhead experiments on SUMO mobility traces."""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .channel_model import RadioParameters, link_budget, packet_airtime_s

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACE = ROOT / "data" / "mobility_traces.csv"
RESULTS_DIRECTORY = ROOT / "results"
UPLOAD_INTERVALS_MS = (50, 100, 500)
PAYLOAD_BYTES = 32
DEFAULT_SEED = 42
SATURATION_THRESHOLD_PERCENT = 60.0


@dataclass(frozen=True)
class VehicleTrace:
    times_s: list[float]
    positions_x_m: list[float]


@dataclass(frozen=True)
class PacketAttempt:
    start_s: float
    end_s: float
    rsu_x_m: float
    snr_db: float


def load_traces(path: Path) -> tuple[dict[int, dict[str, VehicleTrace]], float]:
    """Load generated mobility CSV; fail explicitly on missing or invalid data."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Mobility trace not found: {path}. Generate it with "
            r".\.venv\Scripts\python.exe src\trace_mobility.py"
        )

    collected: dict[int, dict[str, list[tuple[float, float]]]] = {}
    with path.open(newline="", encoding="utf-8") as trace_file:
        reader = csv.DictReader(trace_file)
        required_columns = {"vehicle_count", "time_s", "vehicle_id", "x_m"}
        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            raise ValueError(
                "Trace CSV must contain columns: vehicle_count, time_s, vehicle_id, x_m."
            )
        for row in reader:
            try:
                count = int(row["vehicle_count"])
                time_s = float(row["time_s"])
                x_m = float(row["x_m"])
                vehicle_id = row["vehicle_id"]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid mobility trace row: {row}") from exc
            collected.setdefault(count, {}).setdefault(vehicle_id, []).append((time_s, x_m))

    if not collected:
        raise ValueError(f"Mobility trace contains no vehicle samples: {path}")

    traces: dict[int, dict[str, VehicleTrace]] = {}
    max_time_s = 0.0
    for count, vehicles in collected.items():
        traces[count] = {}
        for vehicle_id, samples in vehicles.items():
            samples.sort()
            times = [sample[0] for sample in samples]
            positions = [sample[1] for sample in samples]
            traces[count][vehicle_id] = VehicleTrace(times, positions)
            max_time_s = max(max_time_s, times[-1])
    return traces, max_time_s


def _position_at(trace: VehicleTrace, time_s: float) -> float:
    return float(np.interp(time_s, trace.times_s, trace.positions_x_m))


def _channel_busy_time_s(
    attempts: list[PacketAttempt],
    duration_s: float | None = None,
) -> float:
    """Measure the union of transmission intervals, counting overlap once."""
    intervals = sorted(
        (
            packet.start_s,
            min(packet.end_s, duration_s) if duration_s is not None else packet.end_s,
        )
        for packet in attempts
        if duration_s is None or packet.start_s < duration_s
    )
    if not intervals:
        return 0.0

    busy_time_s = 0.0
    busy_start_s, busy_end_s = intervals[0]
    for start_s, end_s in intervals[1:]:
        if start_s <= busy_end_s:
            busy_end_s = max(busy_end_s, end_s)
        else:
            busy_time_s += busy_end_s - busy_start_s
            busy_start_s, busy_end_s = start_s, end_s
    return busy_time_s + busy_end_s - busy_start_s


def _collided_packets(attempts: list[PacketAttempt]) -> set[int]:
    """Mark all packets that overlap another transmission on the shared channel."""
    ordered = sorted(enumerate(attempts), key=lambda item: item[1].start_s)
    active: list[tuple[int, PacketAttempt]] = []
    collided: set[int] = set()
    for packet_index, packet in ordered:
        active = [
            (active_index, active_packet)
            for active_index, active_packet in active
            if active_packet.end_s > packet.start_s
        ]
        for active_index, _ in active:
            collided.add(active_index)
            collided.add(packet_index)
        active.append((packet_index, packet))
    return collided


def run_scenario(
    vehicle_count: int,
    vehicles: dict[str, VehicleTrace],
    duration_s: float,
    upload_interval_ms: int,
    radio: RadioParameters,
    seed: int,
    payload_bytes: int = PAYLOAD_BYTES,
) -> dict[str, int | float | bool]:
    """Simulate unslotted periodic telemetry over one shared logical channel."""
    if duration_s <= 0:
        raise ValueError("Simulation duration must be positive.")
    if upload_interval_ms <= 0:
        raise ValueError("Upload interval must be positive.")
    if not vehicles:
        raise ValueError("Scenario must contain at least one vehicle.")

    interval_s = upload_interval_ms / 1000.0
    rng = random.Random(seed)
    attempts: list[PacketAttempt] = []
    total_airtime_s = 0.0
    total_payload_bits = 0
    snr_values_db: list[float] = []

    for vehicle_id in sorted(vehicles):
        trace = vehicles[vehicle_id]
        phase_s = rng.uniform(0.0, interval_s)
        packet_time_s = phase_s
        while packet_time_s < duration_s:
            x_m = _position_at(trace, packet_time_s)
            rsu_x_m, snr_db, link_capacity_bps = link_budget(x_m, radio)
            airtime_s = packet_airtime_s(payload_bytes, link_capacity_bps)
            attempts.append(
                PacketAttempt(
                    packet_time_s,
                    packet_time_s + airtime_s,
                    rsu_x_m,
                    snr_db,
                )
            )
            total_airtime_s += airtime_s
            total_payload_bits += payload_bytes * 8
            snr_values_db.append(snr_db)
            packet_time_s += interval_s

    if not attempts or total_airtime_s <= 0:
        raise ValueError("No telemetry packets were generated for this scenario.")

    collisions = _collided_packets(attempts)
    packet_count = len(attempts)
    snr_array = np.asarray(snr_values_db, dtype=np.float64)
    successful_packets = packet_count - len(collisions)
    offered_airtime_utilisation = total_airtime_s / duration_s
    effective_capacity_bps = total_payload_bits / total_airtime_s
    offered_load_bps = total_payload_bits / duration_s
    residual_fraction = max(0.0, 1.0 - offered_airtime_utilisation)
    busy_time_percent = 100.0 * _channel_busy_time_s(attempts, duration_s) / duration_s
    rsu_counts = {
        rsu_x_m: sum(packet.rsu_x_m == rsu_x_m for packet in attempts)
        for rsu_x_m in radio.rsu_positions_m
    }

    return {
        "vehicle_count": vehicle_count,
        "upload_interval_ms": upload_interval_ms,
        "updates_per_vehicle_per_s": 1000.0 / upload_interval_ms,
        "payload_bytes": payload_bytes,
        "generated_packets": packet_count,
        "collided_packets": len(collisions),
        "successful_packets": successful_packets,
        "packet_delivery_ratio_percent": 100.0 * successful_packets / packet_count,
        "offered_load_mbps": offered_load_bps / 1e6,
        "effective_shannon_capacity_mbps": effective_capacity_bps / 1e6,
        "channel_utilisation_percent": 100.0 * offered_airtime_utilisation,
        "channel_busy_time_percent": busy_time_percent,
        "residual_bandwidth_mhz": radio.bandwidth_hz / 1e6 * residual_fraction,
        "residual_capacity_mbps": effective_capacity_bps / 1e6 * residual_fraction,
        "mean_snr_db": float(np.mean(snr_array)),
        "minimum_snr_db": float(np.min(snr_array)),
        "rsu_250m_packets": rsu_counts.get(250.0, 0),
        "rsu_500m_packets": rsu_counts.get(500.0, 0),
        "rsu_750m_packets": rsu_counts.get(750.0, 0),
        "saturated_over_60_percent": 100.0 * offered_airtime_utilisation
        > SATURATION_THRESHOLD_PERCENT,
    }


def write_csv(path: Path, rows: list[dict[str, int | float | bool]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty result file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as result_file:
        writer = csv.DictWriter(result_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _aggregate_repeats(
    runs: list[dict[str, int | float | bool]],
) -> dict[str, int | float | bool]:
    if not runs:
        raise ValueError("At least one repeated run is required.")
    first = runs[0]
    total_packet_columns = (
        "generated_packets",
        "collided_packets",
        "successful_packets",
        "rsu_250m_packets",
        "rsu_500m_packets",
        "rsu_750m_packets",
    )
    average_columns = (
        "offered_load_mbps",
        "effective_shannon_capacity_mbps",
        "channel_utilisation_percent",
        "channel_busy_time_percent",
        "residual_bandwidth_mhz",
        "residual_capacity_mbps",
        "mean_snr_db",
    )
    result = {
        key: value
        for key, value in first.items()
        if key not in total_packet_columns
        and key not in average_columns
        and key not in ("minimum_snr_db", "saturated_over_60_percent")
    }
    result["repeats"] = len(runs)
    for key in total_packet_columns:
        result[key] = sum(int(run[key]) for run in runs)
    for key in average_columns:
        result[key] = float(np.mean([float(run[key]) for run in runs]))
    result["minimum_snr_db"] = float(
        np.min([float(run["minimum_snr_db"]) for run in runs])
    )
    result["packet_delivery_ratio_percent"] = (
        100.0 * int(result["successful_packets"]) / int(result["generated_packets"])
    )
    result["saturated_over_60_percent"] = (
        float(result["channel_utilisation_percent"])
        > SATURATION_THRESHOLD_PERCENT
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE, help="Input mobility CSV.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random phase seed.")
    parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="Independent random upload-phase runs per scenario (default: 5).",
    )
    parser.add_argument(
        "--path-loss-exponent",
        type=float,
        default=3.25,
        help="Log-distance path-loss exponent in the assigned 3.0-3.5 range.",
    )
    parser.add_argument(
        "--payload-bytes",
        type=int,
        choices=(32, 64),
        default=PAYLOAD_BYTES,
        help="Telemetry payload size from the assigned 32-64 byte range.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=RESULTS_DIRECTORY,
        help="Directory for experiment and saturation CSV files.",
    )
    args = parser.parse_args()
    if args.repeats <= 0:
        parser.error("--repeats must be greater than zero.")
    try:
        radio = RadioParameters(path_loss_exponent=args.path_loss_exponent)
        traces, duration_s = load_traces(args.trace)
        results: list[dict[str, int | float | bool]] = []
        for vehicle_count in sorted(traces):
            for interval_ms in UPLOAD_INTERVALS_MS:
                runs = [
                    run_scenario(
                        vehicle_count,
                        traces[vehicle_count],
                        duration_s,
                        interval_ms,
                        radio,
                        args.seed
                        + vehicle_count * 100_000
                        + interval_ms * 100
                        + repeat,
                        args.payload_bytes,
                    )
                    for repeat in range(args.repeats)
                ]
                results.append(_aggregate_repeats(runs))

        results_path = args.output_directory / "experiment_results.csv"
        write_csv(results_path, results)

        thresholds: list[dict[str, int | str]] = []
        for interval_ms in UPLOAD_INTERVALS_MS:
            crossing = next(
                (
                    int(row["vehicle_count"])
                    for row in results
                    if row["upload_interval_ms"] == interval_ms
                    and row["saturated_over_60_percent"]
                ),
                None,
            )
            thresholds.append(
                {
                    "upload_interval_ms": interval_ms,
                    "saturation_threshold_vehicle_count": crossing or "",
                    "status": (
                        "reached"
                        if crossing is not None
                        else f"not reached up to {max(traces)} vehicles"
                    ),
                }
            )
        thresholds_path = args.output_directory / "saturation_thresholds.csv"
        write_csv(thresholds_path, thresholds)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")

    print(f"Radio model: {radio.carrier_frequency_hz / 1e9:.1f} GHz, "
          f"{radio.bandwidth_hz / 1e6:.0f} MHz, "
          f"{radio.transmit_power_dbm:.0f} dBm, "
          f"noise floor {radio.noise_power_dbm:.1f} dBm, "
          f"path-loss exponent {radio.path_loss_exponent:.2f}.")
    print(f"Wrote {len(results)} scenarios to {results_path}")
    print(f"Wrote saturation thresholds to {thresholds_path}")
    for row in results:
        print(
            f"{row['vehicle_count']:>3} vehicles, "
            f"{row['upload_interval_ms']:>3} ms: "
            f"utilisation {row['channel_utilisation_percent']:.2f}%, "
            f"PDR {row['packet_delivery_ratio_percent']:.2f}%, "
            f"residual {row['residual_bandwidth_mhz']:.2f} MHz"
        )


if __name__ == "__main__":
    main()
