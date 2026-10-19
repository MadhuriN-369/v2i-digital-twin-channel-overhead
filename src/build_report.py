"""Build a mentor-review PDF report from the generated experiment artifacts."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
BASELINE_RESULTS = ROOT / "results" / "experiment_results.csv"
SATURATION_RESULTS = ROOT / "results" / "saturation_thresholds.csv"
SENSITIVITY_RESULTS = (
    ROOT / "results" / "sensitivity_64b_alpha35" / "experiment_results.csv"
)
FIGURES_DIRECTORY = ROOT / "results" / "figures"
OUTPUT_PDF = ROOT / "report.pdf"
TEAM = (
    ("241CS135", "Mudu Keerthana", "Member"),
    ("241CS144", "R Trishna", "Member"),
    ("241CS152", "Harika Seesa", "Member"),
    ("241CS236", "Madhuri Nallaboyina", "Team leader"),
)
UPLOAD_INTERVALS_MS = (50, 100, 500)
VEHICLE_COUNTS = (5, 10, 20, 50, 100)
NAVY = colors.HexColor("#17365D")
PALE_BLUE = colors.HexColor("#DCE6F1")
LIGHT_GRAY = colors.HexColor("#F2F2F2")


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required report input not found: {path}. Run the experiment scripts first."
        )
    with path.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    if not rows:
        raise ValueError(f"Required report input is empty: {path}")
    return rows


def _index_results(rows: list[dict[str, str]]) -> dict[tuple[int, int], dict[str, str]]:
    indexed: dict[tuple[int, int], dict[str, str]] = {}
    for row in rows:
        try:
            key = (int(row["vehicle_count"]), int(row["upload_interval_ms"]))
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Invalid experiment result row: {row}") from exc
        indexed[key] = row
    return indexed


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=30,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=18,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=13,
            leading=19,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#444444"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=NAVY,
            spaceBefore=8,
            spaceAfter=9,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SubsectionHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=NAVY,
            spaceBefore=7,
            spaceAfter=5,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyTextCompact",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.3,
            leading=13,
            alignment=TA_LEFT,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallNote",
            parent=styles["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#555555"),
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableText",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableHeader",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ChartCaption",
            parent=styles["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#444444"),
        )
    )
    return styles


def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def _table(data, widths, styles) -> Table:
    formatted = []
    for row_index, row in enumerate(data):
        cell_style = styles["TableHeader"] if row_index == 0 else styles["TableText"]
        formatted.append(
            [
                value
                if isinstance(value, Paragraph)
                else _paragraph(str(value), cell_style)
                for value in row
            ]
        )
    table = Table(formatted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B7C9D6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _page_chrome(canvas, document) -> None:
    canvas.saveState()
    page_width, page_height = letter
    if document.page > 1:
        canvas.setStrokeColor(PALE_BLUE)
        canvas.line(document.leftMargin, page_height - 0.48 * inch,
                    page_width - document.rightMargin, page_height - 0.48 * inch)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(
            document.leftMargin,
            page_height - 0.38 * inch,
            "V2I Digital-Twin Synchronisation Overhead",
        )
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawCentredString(page_width / 2, 0.35 * inch, f"Page {document.page}")
    canvas.restoreState()


def _number(value: str, places: int = 2) -> str:
    return f"{float(value):.{places}f}"


def _metric_chart(
    story,
    styles,
    path: Path,
    heading: str,
    caption: str,
    width: float = 6.65 * inch,
    height_ratio: float = 0.78,
) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Required report figure not found: {path}")
    image = Image(str(path), width=width, height=width * height_ratio)
    story.extend(
        [
            _paragraph(heading, styles["SectionHeading"]),
            Spacer(1, 0.15 * inch),
            image,
            Spacer(1, 0.08 * inch),
            _paragraph(caption, styles["ChartCaption"]),
        ]
    )


def build_report(output_path: Path) -> None:
    baseline = _index_results(_read_csv(BASELINE_RESULTS))
    sensitivity = _index_results(_read_csv(SENSITIVITY_RESULTS))
    saturation = _read_csv(SATURATION_RESULTS)
    if len(baseline) != len(VEHICLE_COUNTS) * len(UPLOAD_INTERVALS_MS):
        raise ValueError("Baseline results do not include all 15 expected scenarios.")
    if len(sensitivity) != len(VEHICLE_COUNTS) * len(UPLOAD_INTERVALS_MS):
        raise ValueError("Sensitivity results do not include all 15 expected scenarios.")

    styles = _build_styles()
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.72 * inch,
        leftMargin=0.72 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.62 * inch,
        title="Quantifying V2I Channel Overhead from Continuous Digital Twin State Synchronisation",
        author="V2I Group 14",
        subject="Cloud Computing course project report draft",
    )
    story = []

    story.extend(
        [
            Spacer(1, 1.05 * inch),
            _paragraph("CLOUD COMPUTING COURSE PROJECT", styles["CoverSubtitle"]),
            Spacer(1, 0.42 * inch),
            _paragraph(
                "Quantifying V2I Channel Overhead from Continuous Digital Twin "
                "State Synchronisation",
                styles["CoverTitle"],
            ),
            _paragraph(
                "A SUMO and Python study of vehicular edge telemetry load",
                styles["CoverSubtitle"],
            ),
            Spacer(1, 0.55 * inch),
            _table(
                [
                    ["Roll number", "Team member", "Role"],
                    *[list(member) for member in TEAM],
                ],
                [1.25 * inch, 3.35 * inch, 1.45 * inch],
                styles,
            ),
            Spacer(1, 0.5 * inch),
            _paragraph("Assignment: Task 1 - V2I channel overhead", styles["CoverSubtitle"]),
            _paragraph("Submission report draft for mentor review", styles["CoverSubtitle"]),
            _paragraph("October 2026", styles["CoverSubtitle"]),
            Spacer(1, 0.42 * inch),
            _paragraph(
                "This report is generated from the project code and experiment CSVs. "
                "The channel assumptions and limitations are stated explicitly; "
                "the results require mentor approval before final submission.",
                styles["SmallNote"],
            ),
            PageBreak(),
        ]
    )

    story.extend(
        [
            _paragraph("Abstract", styles["SectionHeading"]),
            _paragraph(
                "Vehicular digital twins rely on frequent vehicle-state updates sent "
                "over a shared vehicle-to-infrastructure (V2I) uplink. This project "
                "implements a reproducible SUMO mobility scenario and a first-order "
                "Python link-budget model to estimate telemetry airtime, packet "
                "collisions, packet delivery ratio (PDR), and the remaining channel "
                "resource for task offloading. Five vehicle densities (5, 10, 20, 50, "
                "and 100), three update intervals (50, 100, and 500 ms), and five "
                "random-phase repetitions were evaluated. With a 32-byte payload and "
                "the assigned 5.9 GHz, 10 MHz radio parameters, the highest baseline "
                "utilisation was 2.15% at 100 vehicles and a 50 ms update interval. "
                "The required 60% saturation threshold was not reached in the tested "
                "range. A 64-byte, path-loss-exponent-3.5 sensitivity case reached "
                "9.21% at the same density and interval.",
                styles["BodyTextCompact"],
            ),
            _paragraph("1. Problem and objectives", styles["SectionHeading"]),
            _paragraph(
                "The assigned problem asks how much shared V2I uplink capacity is "
                "consumed by continuous digital-twin state synchronisation as vehicle "
                "density increases. The project objectives are to generate SUMO vehicle "
                "traces; estimate received power, SNR, and Shannon capacity; simulate "
                "periodic telemetry and overlapping transmissions; report utilisation, "
                "PDR, residual bandwidth, per-vehicle update rate, and the first tested "
                "density above 60% utilisation.",
                styles["BodyTextCompact"],
            ),
            _paragraph("2. Tools and implementation", styles["SectionHeading"]),
            _paragraph(
                "SUMO 1.28.0 supplies a 1,000 m two-lane corridor and TraCI controls "
                "vehicle insertion and state collection. Python 3.14.2 is used with "
                "NumPy for numerical summaries and Matplotlib for plots. The code is "
                "separated into mobility trace generation "
                "(src/trace_mobility.py), link-budget functions (src/channel_model.py), "
                "experiment execution (src/run_experiments.py), and plotting "
                "(src/plot_results.py). Unit checks are in tests/test_channel_model.py.",
                styles["BodyTextCompact"],
            ),
            _paragraph("3. Mobility scenario", styles["SectionHeading"]),
            _table(
                [
                    ["Setting", "Value"],
                    ["Road", "Straight 1,000 m corridor; two lanes; 20 m/s speed limit"],
                    ["Simulation duration and step", "10 s per scenario; 0.05 s step"],
                    ["Vehicle densities", "5, 10, 20, 50, 100"],
                    ["Vehicle start positions", "Evenly spaced from 100 m to 800 m"],
                    ["Initial speed and random seed", "5 m/s; seed 42"],
                    ["Mobility output", "Position, speed, heading, acceleration; 37,000 rows"],
                ],
                [2.05 * inch, 4.0 * inch],
                styles,
            ),
            PageBreak(),
        ]
    )

    story.extend(
        [
            _paragraph("4. Radio and traffic model", styles["SectionHeading"]),
            _table(
                [
                    ["Parameter", "Baseline value"],
                    ["Carrier frequency", "5.9 GHz"],
                    ["Channel bandwidth", "10 MHz"],
                    ["Transmit power", "20 dBm"],
                    ["Thermal noise PSD / receiver noise figure", "-174 dBm/Hz / 9 dB"],
                    ["Integrated receiver noise over 10 MHz", "-95 dBm"],
                    ["Reference distance and path-loss exponent", "1 m / 3.25"],
                    ["Free-space reference loss at 5.9 GHz", "About 47.87 dB"],
                    ["Logical RSU positions", "250 m, 500 m, 750 m"],
                    ["Payload / upload intervals", "32 bytes / 50, 100, 500 ms"],
                ],
                [3.0 * inch, 3.05 * inch],
                styles,
            ),
            Spacer(1, 0.12 * inch),
            _paragraph(
                "The model uses three logical RSU positions along the road. Every "
                "vehicle associates with the nearest RSU, but all vehicles contend on "
                "one shared logical 10 MHz channel; no spatial reuse between RSUs is "
                "assumed. Distance is the longitudinal road-coordinate difference.",
                styles["BodyTextCompact"],
            ),
            _paragraph("Link budget", styles["SubsectionHeading"]),
            _paragraph(
                "For distance d at or beyond the 1 m reference point, path loss is "
                "PL(d) = PL(1 m) + 10 alpha log10(d / 1 m). Reference loss is the "
                "free-space loss 20 log10(4 pi f d0 / c). Received power is transmit "
                "power minus path loss. Receiver noise is N = -174 + 10 log10(B) + NF "
                "dBm, giving -95 dBm at 10 MHz with a 9 dB noise figure. Linear SNR is "
                "10^(SNR_dB/10), and link capacity is C = B log2(1 + SNR_linear). "
                "Ideal payload airtime is payload bits divided by C.",
                styles["BodyTextCompact"],
            ),
            _paragraph("Traffic, collisions, and metrics", styles["SubsectionHeading"]),
            _paragraph(
                "For each run, vehicle upload phases are independently drawn from a "
                "uniform distribution over one upload interval and then remain fixed "
                "for that run. Five seeded phase repetitions are pooled. A collision "
                "occurs when two packet airtime intervals overlap anywhere on the shared "
                "channel; both packets are counted as unsuccessful. Positions between "
                "the 50 ms SUMO samples are linearly interpolated. The effective "
                "Shannon capacity is total payload bits divided by total ideal airtime.",
                styles["BodyTextCompact"],
            ),
            _table(
                [
                    ["Metric", "Definition"],
                    ["Offered load", "Generated payload bits / simulation duration"],
                    ["Utilisation", "Sum of ideal packet airtimes / simulation duration"],
                    ["Busy time", "Union of packet airtime intervals / duration"],
                    ["PDR", "(Generated packets - collided packets) / generated packets"],
                    ["Residual bandwidth", "10 MHz x max(0, 1 - utilisation fraction)"],
                    ["Saturation threshold", "First tested density with utilisation > 60%"],
                ],
                [1.75 * inch, 4.3 * inch],
                styles,
            ),
            Spacer(1, 0.12 * inch),
            _paragraph(
                "Offered utilisation counts overlapping attempts separately and may "
                "exceed 100% under overload; busy time counts overlapped wall-clock time "
                "once. Residual bandwidth and capacity are clipped at zero.",
                styles["SmallNote"],
            ),
            PageBreak(),
        ]
    )

    baseline_rows = [["Update interval", "PDR", "Utilisation", "Residual bandwidth"]]
    for interval_ms in UPLOAD_INTERVALS_MS:
        row = baseline[(100, interval_ms)]
        baseline_rows.append(
            [
                f"{interval_ms} ms ({1000 / interval_ms:.0f} updates/s/vehicle)",
                f"{_number(row['packet_delivery_ratio_percent'])}%",
                f"{_number(row['channel_utilisation_percent'])}%",
                f"{_number(row['residual_bandwidth_mhz'])} MHz",
            ]
        )
    saturation_rows = [["Update interval", "60% threshold result"]]
    for row in saturation:
        saturation_rows.append(
            [f"{row['upload_interval_ms']} ms", row["status"]]
        )

    story.extend(
        [
            _paragraph("5. Baseline results", styles["SectionHeading"]),
            _paragraph(
                "The following measurements are for the maximum tested density of "
                "100 vehicles. Packet counts and PDR pool five random-phase repetitions. "
                "The nominal per-vehicle transmission rates are 20, 10, and 2 telemetry "
                "updates per second for the 50, 100, and 500 ms intervals.",
                styles["BodyTextCompact"],
            ),
            _table(
                baseline_rows,
                [2.35 * inch, 1.0 * inch, 1.1 * inch, 1.6 * inch],
                styles,
            ),
            Spacer(1, 0.2 * inch),
            _paragraph("Saturation finding", styles["SubsectionHeading"]),
            _paragraph(
                "The 60% utilisation threshold was not reached for any tested update "
                "interval through 100 vehicles. This is a bounded result for the stated "
                "payload, channel model, and density set; it does not establish a "
                "threshold beyond 100 vehicles.",
                styles["BodyTextCompact"],
            ),
            _table(saturation_rows, [1.5 * inch, 4.55 * inch], styles),
            Spacer(1, 0.18 * inch),
            _paragraph(
                "At 100 vehicles, the baseline effective Shannon capacity is about "
                f"{_number(baseline[(100, 50)]['effective_shannon_capacity_mbps'])} Mbps "
                "for the 50 ms case, while the offered telemetry load is 0.512 Mbps. "
                "The resulting low airtime load explains why the assigned 60% threshold "
                "is not crossed under the idealised model.",
                styles["BodyTextCompact"],
            ),
            PageBreak(),
        ]
    )

    _metric_chart(
        story,
        styles,
        FIGURES_DIRECTORY / "utilisation_vs_density.png",
        "6. Utilisation by density and update interval",
        "The upper panel places the assigned 60% threshold in context; the lower panel "
        "zooms in on the measured baseline range.",
    )
    story.append(PageBreak())
    _metric_chart(
        story,
        styles,
        FIGURES_DIRECTORY / "pdr_vs_density.png",
        "7. Packet delivery ratio",
        "PDR falls as density and update frequency increase because overlapping "
        "transmissions collide in the shared-channel model.",
        height_ratio=0.625,
    )
    story.append(PageBreak())
    _metric_chart(
        story,
        styles,
        FIGURES_DIRECTORY / "residual_bandwidth_vs_density.png",
        "8. Residual bandwidth for offloading",
        "Residual bandwidth is the 10 MHz logical channel after offered telemetry "
        "airtime has been subtracted.",
        height_ratio=0.625,
    )
    story.append(PageBreak())

    sensitivity_rows = [["Update interval", "Utilisation", "PDR", "Residual bandwidth"]]
    for interval_ms in UPLOAD_INTERVALS_MS:
        row = sensitivity[(100, interval_ms)]
        sensitivity_rows.append(
            [
                f"{interval_ms} ms",
                f"{_number(row['channel_utilisation_percent'])}%",
                f"{_number(row['packet_delivery_ratio_percent'])}%",
                f"{_number(row['residual_bandwidth_mhz'])} MHz",
            ]
        )

    story.extend(
        [
            _paragraph("9. Sensitivity analysis", styles["SectionHeading"]),
            _paragraph(
                "To test a higher telemetry burden, payload size was increased to "
                "64 bytes and the path-loss exponent to 3.5, keeping the same mobility "
                "traces, density set, channel bandwidth, and five repetitions. At "
                "100 vehicles:",
                styles["BodyTextCompact"],
            ),
            _table(
                sensitivity_rows,
                [1.25 * inch, 1.35 * inch, 1.0 * inch, 1.65 * inch],
                styles,
            ),
            Spacer(1, 0.15 * inch),
            _paragraph(
                "Even in this higher-overhead tested case, utilisation remains below "
                "10% at 50 ms and below the required 60% threshold. Collision losses "
                "can still reduce PDR even when average channel utilisation is modest; "
                "the uncoordinated periodic access and shared-channel assumptions make "
                "PDR sensitive to upload phase alignment.",
                styles["BodyTextCompact"],
            ),
            _paragraph("10. Discussion and limitations", styles["SectionHeading"]),
            _paragraph(
                "The observed trends match the model: more vehicles and shorter update "
                "intervals increase offered telemetry airtime, reduce residual "
                "bandwidth, and create more opportunities for packet overlap. At the "
                "same 100-vehicle density, a 50 ms interval generates ten times as "
                "many updates per vehicle as a 500 ms interval. In the baseline, PDR "
                "is 96.09% at 50 ms and 99.74% at 500 ms.",
                styles["BodyTextCompact"],
            ),
            _paragraph(
                "This model is not an 802.11p/DSRC simulator. It uses Shannon-limit "
                "rates and payload-only airtime; it omits MAC/PHY headers, CSMA/CA "
                "backoff, coding-rate limits, fading, shadowing, receiver sensitivity, "
                "cross-RSU interference, retransmissions, and task-offloading packets. "
                "There is no independent PHY outage/drop threshold because none was "
                "specified in the assignment; the PDR loss counted here is from "
                "overlapping transmissions. Accordingly, the results are an optimistic, "
                "reproducible baseline and should not be presented as measured DSRC "
                "performance.",
                styles["BodyTextCompact"],
            ),
            _paragraph("11. Conclusion", styles["SectionHeading"]),
            _paragraph(
                "A working SUMO/TraCI-to-Python pipeline now generates repeatable "
                "mobility traces and evaluates telemetry overhead across all assigned "
                "densities and update intervals. Under the stated 32-byte baseline, "
                "the maximum measured offered utilisation is 2.15%, so no tested "
                "density reaches 60%. The 64-byte / exponent-3.5 sensitivity case "
                "increases maximum utilisation to 9.21%, still below the threshold. "
                "The next improvement should be a mentor-approved PHY/MAC model "
                "including packet overhead and realistic access control, followed by "
                "re-running and comparing these baseline results.",
                styles["BodyTextCompact"],
            ),
            _paragraph("Reproduction", styles["SubsectionHeading"]),
            _paragraph(
                r"Build the road with netconvert, then run "
                r"<font name='Courier'>python src\trace_mobility.py</font>, "
                r"<font name='Courier'>python -m src.run_experiments</font>, and "
                r"<font name='Courier'>python -m src.plot_results</font> from the "
                "project directory. The default experiment uses seed 42 and five "
                "phase repetitions; generated CSVs and figures are retained under "
                "data/ and results/.",
                styles["BodyTextCompact"],
            ),
            _paragraph("References", styles["SectionHeading"]),
            _paragraph(
                "[1] Course-assigned Task 1 problem statement, V2I digital-twin "
                "synchronisation overhead, 2026.",
                styles["BodyTextCompact"],
            ),
            _paragraph(
                "[2] C. E. Shannon, 'A Mathematical Theory of Communication,' "
                "Bell System Technical Journal, vol. 27, pp. 379-423 and 623-656, 1948.",
                styles["BodyTextCompact"],
            ),
            _paragraph(
                "[3] H. T. Friis, 'A Note on a Simple Transmission Formula,' "
                "Proceedings of the IRE, vol. 34, no. 5, pp. 254-256, 1946.",
                styles["BodyTextCompact"],
            ),
            _paragraph(
                "[4] German Aerospace Center (DLR), Eclipse SUMO Documentation, "
                "https://sumo.dlr.de/docs/ (accessed October 2026).",
                styles["BodyTextCompact"],
            ),
            Spacer(1, 0.1 * inch),
            KeepTogether(
                [
                    _paragraph(
                        "Mentor approval: ________________________________",
                        styles["SmallNote"],
                    ),
                    _paragraph(
                        "This is a draft prepared for review. Update it if the mentor "
                        "changes the radio assumptions or approves a different model.",
                        styles["SmallNote"],
                    ),
                ]
            ),
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.build(story, onFirstPage=_page_chrome, onLaterPages=_page_chrome)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PDF)
    args = parser.parse_args()
    try:
        build_report(args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Wrote report draft to {args.output}")


if __name__ == "__main__":
    main()
