V2I Digital-Twin Synchronisation Overhead - Group 14
Cloud Computing Course Project

Team:
241CS135  Mudu Keerthana
241CS144  R Trishna
241CS152  Harika Seesa
241CS236  Madhuri Nallaboyina (Team leader)

Project:
Quantifying V2I channel overhead from continuous digital-twin state
synchronisation in vehicular edge computing networks.

Requirements:
- SUMO 1.28 or newer, including sumo, netconvert, and the TraCI tools folder
- Python 3.10 or newer
- Install Python dependencies with: python -m pip install -r requirements.txt

Run from the project folder in PowerShell:
1. Build the road: netconvert --node-files network\corridor.nod.xml --edge-files network\corridor.edg.xml --output-file network\corridor.net.xml
2. Watch the five-vehicle visual demo: sumo-gui -c network\corridor_demo.sumocfg --delay 100
3. Generate mobility data: python src\trace_mobility.py
4. Run radio experiments: python -m src.run_experiments
5. Generate plots: python -m src.plot_results
6. Build the PDF report: python -m src.build_report
7. Create the draft archive: python -m src.package_submission
8. Run tests: python -m unittest discover -s tests -v

Default results:
- data\mobility_traces.csv
- results\experiment_results.csv
- results\saturation_thresholds.csv
- results\figures\
- report.pdf
- Madhuri_241CS236.zip (one directory above the project)

The baseline uses a 32-byte telemetry payload, a 3.25 path-loss exponent, and
five repeatable random-phase runs per scenario. Airtime includes 802.11p frame overhead (28-byte MAC header plus 196 us of
preamble, DIFS and average backoff). Utilisation reaches 43.2 percent at 100
vehicles with 50 ms updates. The 60 percent threshold is not reached within 100
vehicles, but extrapolation puts it at about 139 vehicles (32 B) and about 115
vehicles (64 B, exponent 3.5).
The report identifies the analytical model assumptions and is a draft for
mentor review; it is not a claim of mentor approval.
