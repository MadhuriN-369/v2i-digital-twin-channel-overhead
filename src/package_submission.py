"""Create a draft assignment archive without local environments or caches."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE = ROOT.parent / "Madhuri_241CS236.zip"
EXCLUDED_DIRECTORY_NAMES = {".venv", ".git", "__pycache__"}
EXCLUDED_ROOT_FILES = {"report.pdf", "readme.txt"}
REQUIRED_FILES = (
    ROOT / "report.pdf",
    ROOT / "readme.txt",
    ROOT / "README.md",
    ROOT / "requirements.txt",
    ROOT / "network" / "corridor.net.xml",
    ROOT / "data" / "mobility_traces.csv",
    ROOT / "results" / "experiment_results.csv",
    ROOT / "results" / "saturation_thresholds.csv",
)


def _project_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative_path = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative_path.parts):
            continue
        if len(relative_path.parts) == 1 and relative_path.name in EXCLUDED_ROOT_FILES:
            continue
        files.append(path)
    return sorted(files)


def create_archive(output_path: Path) -> int:
    missing = [str(path) for path in REQUIRED_FILES if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Cannot package the draft; required deliverables are missing: "
            + ", ".join(missing)
        )
    resolved_output = output_path.resolve()
    if resolved_output.is_relative_to(ROOT.resolve()):
        raise ValueError("Place the archive outside the project folder.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    project_files = _project_files()
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in project_files:
            archive.write(path, f"{ROOT.name}/{path.relative_to(ROOT).as_posix()}")
        archive.write(ROOT / "report.pdf", "report.pdf")
        archive.write(ROOT / "readme.txt", "readme.txt")
    return len(project_files) + 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    try:
        file_count = create_archive(args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(
        f"Created draft archive {args.output} with {file_count} files. "
        "Get mentor approval before final submission."
    )


if __name__ == "__main__":
    main()
