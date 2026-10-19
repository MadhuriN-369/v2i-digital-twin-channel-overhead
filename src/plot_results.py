"""Plot the density and upload-frequency experiment results."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS = ROOT / "results" / "experiment_results.csv"
DEFAULT_OUTPUT_DIRECTORY = ROOT / "results" / "figures"


def load_results(path: Path) -> list[dict[str, float]]:
    if not path.is_file():
        raise FileNotFoundError(f"Experiment results not found: {path}")
    required = {
        "vehicle_count",
        "upload_interval_ms",
        "packet_delivery_ratio_percent",
        "channel_utilisation_percent",
        "residual_bandwidth_mhz",
        "updates_per_vehicle_per_s",
    }
    rows: list[dict[str, float]] = []
    with path.open(newline="", encoding="utf-8") as results_file:
        reader = csv.DictReader(results_file)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(
                "Experiment results CSV is missing required plotting columns."
            )
        for row in reader:
            try:
                rows.append(
                    {
                        key: float(row[key])
                        for key in required
                    }
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid experiment result row: {row}") from exc
    if not rows:
        raise ValueError(f"Experiment results contain no rows: {path}")
    return rows


def plot_metric(
    rows: list[dict[str, float]],
    metric: str,
    ylabel: str,
    title: str,
    output_path: Path,
    saturation_line: bool = False,
    y_limits: tuple[float, float] | None = None,
) -> None:
    if saturation_line:
        figure, (axis, detail_axis) = plt.subplots(
            2,
            1,
            figsize=(8, 7),
            sharex=True,
            gridspec_kw={"height_ratios": (1, 1)},
        )
    else:
        figure, axis = plt.subplots(figsize=(8, 5))
        detail_axis = None

    intervals = sorted({int(row["upload_interval_ms"]) for row in rows})
    for interval_ms in intervals:
        series = sorted(
            (
                row
                for row in rows
                if int(row["upload_interval_ms"]) == interval_ms
            ),
            key=lambda row: row["vehicle_count"],
        )
        axis.plot(
            [row["vehicle_count"] for row in series],
            [row[metric] for row in series],
            marker="o",
            linewidth=2,
            label=f"{interval_ms} ms updates",
        )
        if detail_axis is not None:
            detail_axis.plot(
                [row["vehicle_count"] for row in series],
                [row[metric] for row in series],
                marker="o",
                linewidth=2,
            )

    if saturation_line:
        axis.axhline(
            60.0,
            color="red",
            linestyle="--",
            linewidth=1.5,
            label="60% saturation threshold",
        )
        if detail_axis is not None:
            maximum = max(row[metric] for row in rows)
            detail_axis.set_ylim(0.0, max(0.5, maximum * 1.2))
            detail_axis.set_ylabel("Utilisation (zoomed %)")
            detail_axis.grid(True, linestyle=":", alpha=0.7)
            axis.set_ylim(0.0, 65.0)
    axis.set_xlabel("Vehicles in scenario")
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    axis.set_xticks(sorted({int(row["vehicle_count"]) for row in rows}))
    if y_limits is not None:
        axis.set_ylim(*y_limits)
    axis.grid(True, linestyle=":", alpha=0.7)
    axis.legend()
    if detail_axis is not None:
        axis.set_xlabel("")
        detail_axis.set_xlabel("Vehicles in scenario")
        detail_axis.set_xticks(sorted({int(row["vehicle_count"]) for row in rows}))
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def plot_tx_rate(
    rows: list[dict[str, float]],
    output_path: Path,
) -> None:
    """Plot per-vehicle transmission count per second at each upload frequency.

    Each upload interval produces a constant rate (1000 / interval_ms), so the
    lines are horizontal across vehicle densities.  Plotting them together makes
    the three operational points immediately comparable.
    """
    figure, axis = plt.subplots(figsize=(8, 5))
    intervals = sorted({int(row["upload_interval_ms"]) for row in rows})
    for interval_ms in intervals:
        series = sorted(
            (row for row in rows if int(row["upload_interval_ms"]) == interval_ms),
            key=lambda row: row["vehicle_count"],
        )
        densities = [row["vehicle_count"] for row in series]
        rates = [row["updates_per_vehicle_per_s"] for row in series]
        axis.plot(
            densities,
            rates,
            marker="o",
            linewidth=2,
            label=f"{interval_ms} ms interval ({rates[0]:.0f} updates/vehicle/s)",
        )
    axis.set_xlabel("Vehicles in scenario")
    axis.set_ylabel("Transmissions per vehicle per second")
    axis.set_title("Per-vehicle DT state upload rate by frequency")
    axis.set_xticks(sorted({int(row["vehicle_count"]) for row in rows}))
    axis.set_ylim(bottom=0)
    axis.grid(True, linestyle=":", alpha=0.7)
    axis.legend()
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    args = parser.parse_args()
    try:
        rows = load_results(args.input)
        outputs = (
            (
                "utilisation_vs_density.png",
                "channel_utilisation_percent",
                "Offered channel utilisation (%)",
                "Telemetry channel utilisation by vehicle density",
                True,
                None,
            ),
            (
                "pdr_vs_density.png",
                "packet_delivery_ratio_percent",
                "Packet delivery ratio (%)",
                "Telemetry packet delivery by vehicle density",
                False,
                (0.0, 100.0),
            ),
            (
                "residual_bandwidth_vs_density.png",
                "residual_bandwidth_mhz",
                "Residual bandwidth (MHz)",
                "Residual bandwidth for task offloading",
                False,
                (0.0, 10.0),
            ),
        )
        for filename, metric, ylabel, title, threshold, limits in outputs:
            plot_metric(
                rows,
                metric,
                ylabel,
                title,
                args.output_directory / filename,
                saturation_line=threshold,
                y_limits=limits,
            )
        plot_tx_rate(rows, args.output_directory / "tx_rate_vs_density.png")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Wrote four experiment plots to {args.output_directory}")


if __name__ == "__main__":
    main()
