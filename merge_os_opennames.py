#!/usr/bin/env python3
"""
Merge OS Open Names dataset CSV files.

This script merges all CSV files from the Data folder of the OS Open Names dataset
and adds the headers from the Doc folder.

Usage:
    python merge_os_opennames.py <path_to_dataset_folder>

Example:
    python merge_os_opennames.py ~/Downloads/opname_csv_gb
"""

import argparse
import csv
import sys
from pathlib import Path


def merge_os_opennames(dataset_path: str) -> None:
    """
    Merge all CSV files in the Data folder with headers from the Doc folder.

    Args:
        dataset_path: Path to the top-level OS Open Names dataset folder
    """
    # Convert to Path object and resolve
    dataset_dir = Path(dataset_path).expanduser().resolve()

    # Validate paths
    if not dataset_dir.exists():
        print(f"Error: Dataset folder does not exist: {dataset_dir}", file=sys.stderr)
        sys.exit(1)

    data_dir = dataset_dir / "Data"
    doc_dir = dataset_dir / "Doc"
    header_file = doc_dir / "OS_Open_Names_Header.csv"

    if not data_dir.exists():
        print(f"Error: Data folder not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    if not header_file.exists():
        print(f"Error: Header file not found: {header_file}", file=sys.stderr)
        sys.exit(1)

    # Get all CSV files in Data folder
    csv_files = sorted(data_dir.glob("*.csv"))

    if not csv_files:
        print(f"Error: No CSV files found in {data_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(csv_files)} CSV files to merge")

    # Read header
    with open(header_file, 'r', encoding='utf-8') as f:
        header = f.read().strip()

    print(f"Header loaded from {header_file.name}")

    # Output file
    output_file = data_dir / "OS_OpenNames_Merged.csv"

    # Merge files
    print(f"Merging files to {output_file}...")

    with open(output_file, 'w', encoding='utf-8', newline='') as outfile:
        # Write header
        outfile.write(header + '\n')

        # Merge all CSV files
        total_rows = 0
        for i, csv_file in enumerate(csv_files, 1):
            with open(csv_file, 'r', encoding='utf-8') as infile:
                rows = 0
                for line in infile:
                    outfile.write(line)
                    rows += 1
                total_rows += rows

            # Progress update every 100 files
            if i % 100 == 0:
                print(f"  Processed {i}/{len(csv_files)} files ({total_rows:,} rows)...")

    print(f"✓ Merge complete!")
    print(f"  Total files merged: {len(csv_files)}")
    print(f"  Total data rows: {total_rows:,}")
    print(f"  Output file: {output_file}")
    print(f"  File size: {output_file.stat().st_size / (1024*1024):.1f} MB")


def main():
    parser = argparse.ArgumentParser(
        description="Merge OS Open Names dataset CSV files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python merge_os_opennames.py ~/Downloads/opname_csv_gb
        """
    )
    parser.add_argument(
        "dataset_path",
        help="Path to the top-level OS Open Names dataset folder"
    )

    args = parser.parse_args()
    merge_os_opennames(args.dataset_path)


if __name__ == "__main__":
    main()
