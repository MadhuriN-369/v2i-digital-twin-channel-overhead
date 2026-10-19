# V2I Digital-Twin Synchronisation Overhead

This project estimates the V2I uplink airtime consumed by continuous vehicle
state synchronisation in a SUMO vehicular-edge scenario. The mobility traces,
first-order radio model, experiment results, and plots are reproducible from
the scripts in this repository.

## Completed milestones: mobility and radio baseline

The starter scenario is a straight, 1,000 m, two-lane road (`road0`). The
simulation uses a 0.05 s step, and creates repeatable 10-second scenarios
containing 5, 10, 20, 50, or 100 vehicles. Vehicles are placed at evenly spaced
positions between 100 m and 800 m at the start of each run, leaving space for
them to move before reaching the end of the road. They start at 5 m/s and have
a 20 m/s speed limit. Mobility traces record position, speed, heading, and
acceleration.

The route definition in `routes.rou.xml` defines the vehicle type and route
only. Vehicle counts are controlled by the TraCI script so each experiment has
the requested population.

The first-order radio model and experiment runner are implemented. They use
three logical roadside-unit locations at x = 250, 500, and 750 m and one shared,
logical 10 MHz channel for all vehicles. RSU association is to the nearest unit
by road position. All vehicles, including those associated with different
RSUs, contend on the same modeled channel; spatial frequency reuse is not
assumed.

### Radio assumptions

| Parameter | Model value |
|---|---:|
| Carrier frequency | 5.9 GHz |
| Channel bandwidth | 10 MHz |
| Vehicle transmit power | 20 dBm |
| Thermal noise PSD | -174 dBm/Hz |
| Receiver noise figure | 9 dB |
| Noise over 10 MHz, including receiver figure | -95 dBm |
| Reference distance | 1 m |
| Reference path loss | Free-space loss at 5.9 GHz (about 47.87 dB) |
| Path-loss exponent | 3.25 (chosen within the assigned 3.0-3.5 range) |
| Telemetry payload | 32 bytes per update (the assigned lower bound) |
| Upload intervals | 50, 100, and 500 ms |

For distance `d >= 1 m`, the model uses
`PL(d) = PL(1 m) + 10 * 3.25 * log10(d / 1 m)`. Receiver noise is
`-174 + 10 * log10(10 MHz) + 9` dBm. SNR is received power minus this noise
power, and the ideal link rate is `10 MHz * log2(1 + SNR_linear)`.
Packet airtime is payload bits divided by this Shannon rate. The reported
effective channel capacity is total generated payload bits divided by total
Shannon airtime (the packet-weighted harmonic mean of link rates).

Vehicle update phases are seeded and independently randomized within each
upload interval; each vehicle keeps its phase during a run. The experiment
runner repeats each scenario five times by default with independent phase
seeds. Any two packets whose airtime overlaps on the shared channel are both
counted as collided. **Channel utilisation** is offered airtime divided
by the 10-second simulation duration; overlapping transmission attempts count
separately in this load metric. It can exceed 100% under overload. The separate
`channel_busy_time_percent` counts the union of airtime intervals and therefore
does not double-count overlap. Residual bandwidth and capacity are clipped to
zero when offered utilisation reaches 100%. Positions between SUMO samples
are linearly interpolated; upload times before the first sample use the first
sample position. PDR counts non-collided packets.

This is a first-order analytical baseline, not a detailed 802.11p/DSRC PHY/MAC
simulation: payload airtime uses the Shannon limit, and packet headers,
contention/backoff, fading, shadowing, receiver sensitivity, interference
between RSUs, and retransmissions are not included. Document these limitations
when interpreting the results. Because the brief does not specify a receiver
sensitivity or outage threshold, the model has no separate PHY-drop test;
reported packet losses are collision losses.

### Prerequisites

- SUMO with `sumo`, `netconvert`, and its `tools` directory available
- Python 3.10 or newer
- TraCI (included in SUMO's `tools` directory)
- NumPy and Matplotlib (install with `python -m pip install -r requirements.txt`)

The current development machine was verified with SUMO 1.28.0 and Python 3.14.2.
`SUMO_HOME` should point to the SUMO installation directory if SUMO's `bin`
directory is not on `PATH`.

### Build the road network

From the project folder:

```powershell
netconvert --node-files network\corridor.nod.xml --edge-files network\corridor.edg.xml --output-file network\corridor.net.xml
```

### Generate mobility traces

```powershell
.\.venv\Scripts\python.exe src\trace_mobility.py
```

The default run writes `data\mobility_traces.csv`. A shorter pilot can be run
with:

```powershell
.\.venv\Scripts\python.exe src\trace_mobility.py --counts 5 --duration 1 --output data\pilot.csv
```

The generated baseline contains 37,000 rows: 200 samples per vehicle for each
requested density. Re-running with the same seed produces the same CSV.

### Watch the vehicles in SUMO-GUI

First build the network using the command above, then launch the visual demo:

```powershell
sumo-gui -c network\corridor_demo.sumocfg --delay 100
```

The GUI demo starts five vehicles on the corridor and runs for 60 simulated
seconds. It is a separate visual scenario; the experiments still use the
TraCI-generated populations and are run with `python -m src.run_experiments`.

### Run the radio experiments

```powershell
.\.venv\Scripts\python.exe -m src.run_experiments
```

This runs five seeded phase repetitions per density and upload-interval pair,
then writes `results\experiment_results.csv` (one aggregated row per pair; packet
counts and PDR are pooled across repetitions) and
`results\saturation_thresholds.csv` (the first tested density
above 60% utilisation, or an explicit "not reached" status). Each experiment
row includes generated and collided packets, PDR, per-vehicle update rate,
offered telemetry load, effective Shannon capacity, channel utilisation, busy
time, residual bandwidth, residual capacity, SNR summaries, and packet counts
per RSU.

The model can also be run with a 64-byte payload or another exponent in the
assigned range:

```powershell
.\.venv\Scripts\python.exe -m src.run_experiments --payload-bytes 64 --path-loss-exponent 3.5
```

Use `--repeats 1` for a quick pilot; use the default or a larger value for the
final reported PDR. The fixed seed makes every set of repetitions reproducible.

### Plot the baseline results

```powershell
.\.venv\Scripts\python.exe -m src.plot_results
```

The command writes four figures to `results\figures\`:

- `utilisation_vs_density.png` — offered channel utilisation with 60% saturation reference line
- `pdr_vs_density.png` — packet delivery ratio across vehicle densities
- `residual_bandwidth_vs_density.png` — bandwidth remaining for task offloading
- `tx_rate_vs_density.png` — per-vehicle transmission count per second at each upload frequency

Pass `--input` to plot a separate experiment CSV, such as the 64-byte sensitivity run:

```powershell
.\.venv\Scripts\python.exe -m src.plot_results --input results\sensitivity_64b_alpha35\experiment_results.csv --output-directory results\sensitivity_64b_alpha35\figures
```

### Build the report draft

```powershell
.\.venv\Scripts\python.exe -m src.build_report
```

This creates `report.pdf` from the experiment CSVs and plots. It includes the
team roster, methodology, results, sensitivity analysis, and limitations; review
it with the mentor and update any approved model changes before submission.

### Create a draft submission archive

```powershell
.\.venv\Scripts\python.exe -m src.package_submission
```

This creates `Madhuri_241CS236.zip` one folder above the project directory. The
archive contains the project folder, `report.pdf`, and `readme.txt`; `.venv`,
Git metadata, and Python caches are excluded. It remains a draft until the
mentor approves the running code and the report.

### Current baseline finding

With the documented 32-byte payload and exponent 3.25, the highest tested
density (100 vehicles) produced:

| Update interval | Offered utilisation | PDR | Residual bandwidth |
|---|---:|---:|---:|
| 50 ms | 2.15% | 96.09% | 9.79 MHz |
| 100 ms | 1.07% | 97.96% | 9.89 MHz |
| 500 ms | 0.21% | 99.74% | 9.98 MHz |

The 60% saturation threshold was **not reached up to 100 vehicles** for any
upload interval. The higher-overhead sensitivity case (64-byte payload,
exponent 3.5, 100 vehicles) reached 9.21% at 50 ms and likewise did not reach
the threshold. These are findings for this specified scenario and simplified
channel model, not proof that saturation cannot occur in a deployed system.

1. **Done:** build and validate the SUMO mobility scenario.
2. **Done:** implement and test the specified link budget, Shannon capacity,
   upload frequencies, collision/PDR model, and saturation analysis.
3. **Done:** produce all four required baseline plots (utilisation, PDR,
   residual bandwidth, per-vehicle TX rate) and a higher-overhead 64-byte /
   alpha-3.5 sensitivity run with matching figures; discuss how the simplifying
   channel assumptions affect the measurements.
4. **Done:** upload source code to GitHub, share with team.
5. Prepare the final report, obtain mentor-approved run, and submit the
   `Madhuri_241CS236.zip` archive with the approved PDF and `readme.txt`.
