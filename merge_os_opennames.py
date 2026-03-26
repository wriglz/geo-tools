#!/usr/bin/env python3
"""
Merge OS Open Names dataset CSV files.

This script merges all CSV files from the Data folder of the OS Open Names dataset
and adds the headers from the Doc folder. It can accept either a zip file or an
already extracted folder.

Usage:
    python merge_os_opennames.py <path_to_zip_or_folder>

Examples:
    python merge_os_opennames.py ~/Downloads/opname_csv_gb.zip
    python merge_os_opennames.py ~/Downloads/opname_csv_gb
"""

import argparse
import csv
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


def extract_zip(zip_path: Path, extract_to: Path) -> Path:
    """
    Extract a zip file and return the path to the extracted dataset folder.

    Args:
        zip_path: Path to the zip file
        extract_to: Directory to extract to

    Returns:
        Path to the extracted dataset folder
    """
    print(f"Extracting {zip_path.name}...")

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

    # Look for the directory that contains both Data and Doc folders
    # Start by checking if extract_to itself has them
    if (extract_to / "Data").exists() and (extract_to / "Doc").exists():
        return extract_to

    # Otherwise, search for a subdirectory that contains both
    for item in extract_to.rglob('*'):
        if item.is_dir() and (item / "Data").exists() and (item / "Doc").exists():
            return item

    # If we can't find the expected structure, raise an error
    raise ValueError(
        f"Could not find dataset structure (Data and Doc folders) in {extract_to}. "
        f"Please check the zip file contents."
    )


def merge_os_opennames(dataset_path: str) -> None:
    """
    Merge all CSV files in the Data folder with headers from the Doc folder.
    Accepts either a zip file or an already extracted folder.

    Args:
        dataset_path: Path to the zip file or top-level OS Open Names dataset folder
    """
    # Convert to Path object and resolve
    input_path = Path(dataset_path).expanduser().resolve()

    # Validate paths
    if not input_path.exists():
        print(f"Error: Path does not exist: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Check if it's a zip file
    temp_dir = None
    output_dir = None
    if input_path.is_file() and input_path.suffix.lower() == '.zip':
        # Create temporary directory for extraction
        temp_dir = Path(tempfile.mkdtemp())
        try:
            dataset_dir = extract_zip(input_path, temp_dir)
            print(f"Extracted to: {dataset_dir}")
            # Save output in the same directory as the zip file
            output_dir = input_path.parent
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"Error extracting zip file: {e}", file=sys.stderr)
            sys.exit(1)
    elif input_path.is_dir():
        dataset_dir = input_path
        # Save output in the Data folder
        output_dir = None
    else:
        print(f"Error: Path must be a directory or a .zip file: {input_path}", file=sys.stderr)
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

    # Output file - if processing a zip, save in the same directory as the zip
    # Otherwise save in the Data folder
    if output_dir:
        output_file = output_dir / "OS_OpenNames_Merged.csv"
    else:
        output_file = data_dir / "OS_OpenNames_Merged.csv"

    # Merge files
    print(f"Merging files to {output_file}...")

    try:
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

    finally:
        # Clean up temporary directory if one was created
        if temp_dir and temp_dir.exists():
            print(f"\nCleaning up temporary files...")
            shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Merge OS Open Names dataset CSV files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python merge_os_opennames.py ~/Downloads/opname_csv_gb.zip
  python merge_os_opennames.py ~/Downloads/opname_csv_gb
        """
    )
    parser.add_argument(
        "dataset_path",
        help="Path to the zip file or extracted dataset folder"
    )

    args = parser.parse_args()
    merge_os_opennames(args.dataset_path)


if __name__ == "__main__":
    main()
