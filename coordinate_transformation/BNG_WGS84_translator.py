"""
BNG_WGS84_translator.py
-----------------------
Converts coordinates between two systems:

  - British National Grid (BNG): the coordinate system used on Ordnance Survey
    maps. Positions are given as Easting and Northing values in metres, measured
    from a false origin south-west of the Isles of Scilly.
    Also known as OSGB36, or EPSG:27700.

  - WGS84: the global coordinate system used by GPS and most online maps
    (Google Maps, OpenStreetMap etc). Positions are given as Latitude and
    Longitude in decimal degrees.
    Also known as EPSG:4326.

Accuracy:
  The conversion uses OSTN15, Ordnance Survey's official transformation model.
  It applies a grid of correction values across Great Britain to account for
  the irregular shape of the OSGB36 datum, giving ~0.1 m accuracy to ETRS89
  (the European reference frame). The overall accuracy to WGS84 is ~1.0 m due
  to a ~0.7 m divergence between WGS84 and ETRS89 caused by tectonic plate
  motion since 1989. This is the best accuracy achievable for a WGS84 target.

Usage (command line):
  python BNG_WGS84_translator.py --to-wgs84 530000 181000
  python BNG_WGS84_translator.py --to-bng 51.51298 -0.12796
"""

import argparse  # Standard library module for parsing command-line arguments
import pyproj    # Python wrapper for the PROJ coordinate transformation library


# ---------------------------------------------------------------------------
# Allow PROJ to download the OSTN15 grid file from the internet on first use.
# The file (uk_os_OSTN15_NTv2_OSGBtoETRS.tif, ~37 MB) is cached locally after
# the first download so subsequent runs work offline.
# If this is False and the file isn't already cached, the script will fail.
# ---------------------------------------------------------------------------
pyproj.network.set_network_enabled(True)


# ---------------------------------------------------------------------------
# Define the transformation pipelines explicitly.
#
# A "pipeline" is a sequence of mathematical steps that converts coordinates
# from one system to another. By defining it explicitly we guarantee OSTN15
# is always used — the script will raise an error at startup if the grid file
# is unavailable, rather than silently falling back to a less accurate method.
#
# BNG → WGS84 pipeline (three steps):
#
#   Step 1 — Inverse Transverse Mercator projection (inv proj=tmerc)
#     BNG eastings/northings are a flat-map projection of the curved Earth.
#     This step "un-projects" them back to angles on the Airy 1830 ellipsoid
#     (the mathematical model of the Earth's shape used by OSGB36).
#     Parameters:
#       lat_0=49, lon_0=-2   — the true origin of the BNG projection
#       k=0.9996012717       — scale factor at the central meridian
#       x_0=400000           — false easting (shifts origin 400 km east)
#       y_0=-100000          — false northing (shifts origin 100 km south)
#       ellps=airy           — uses the Airy 1830 ellipsoid
#
#   Step 2 — OSTN15 grid shift (proj=hgridshift)
#     Applies the OSTN15 correction grid to shift coordinates from the OSGB36
#     datum (based on Airy 1830) to ETRS89 (based on GRS80), which is
#     effectively equivalent to WGS84 for most purposes.
#     The grid file contains pre-computed corrections at regular intervals
#     across Great Britain, interpolated for each input point.
#
#   Step 3 — Unit conversion (proj=unitconvert)
#     Converts the output from radians (PROJ's internal unit) to decimal
#     degrees, which is the standard human-readable format for lat/lon.
#
# WGS84 → BNG pipeline: the exact reverse — steps are in opposite order,
# and each step's direction is inverted.
# ---------------------------------------------------------------------------

_bng_to_wgs84 = pyproj.Transformer.from_pipeline("""
    proj=pipeline
    step inv proj=tmerc lat_0=49 lon_0=-2 k=0.9996012717 x_0=400000 y_0=-100000 ellps=airy
    step proj=hgridshift grids=uk_os_OSTN15_NTv2_OSGBtoETRS.tif
    step proj=unitconvert xy_in=rad xy_out=deg
""")

_wgs84_to_bng = pyproj.Transformer.from_pipeline("""
    proj=pipeline
    step proj=unitconvert xy_in=deg xy_out=rad
    step inv proj=hgridshift grids=uk_os_OSTN15_NTv2_OSGBtoETRS.tif
    step proj=tmerc lat_0=49 lon_0=-2 k=0.9996012717 x_0=400000 y_0=-100000 ellps=airy
""")


# ---------------------------------------------------------------------------
# Public conversion functions
# ---------------------------------------------------------------------------

def bng_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """Convert BNG easting/northing (metres) to WGS84 latitude/longitude (decimal degrees)."""
    # PROJ pipelines work in x/y order (easting first, northing second).
    # The output is also x/y, meaning longitude first — so we swap to return
    # the more conventional (latitude, longitude) order.
    lon, lat = _bng_to_wgs84.transform(easting, northing)
    return lat, lon


def wgs84_to_bng(lat: float, lon: float) -> tuple[float, float]:
    """Convert WGS84 latitude/longitude (decimal degrees) to BNG easting/northing (metres)."""
    # PROJ expects x/y input, so longitude must be passed before latitude.
    easting, northing = _wgs84_to_bng.transform(lon, lat)
    return easting, northing


# ---------------------------------------------------------------------------
# Accuracy reporting
# ---------------------------------------------------------------------------

def _get_accuracy(transformer: pyproj.Transformer) -> str:
    """
    Returns a human-readable accuracy string for the last transformation run.
    Queries PROJ for the operation it used and extracts its stated accuracy.
    A value of -1 from PROJ means accuracy is not recorded for that operation.
    """
    op = transformer.get_last_used_operation()
    if op is None:
        return "unknown"
    acc = op.accuracy
    # Check whether OSTN15 was used by looking for its name in the operation definition
    ostn15 = "OSTN15" in (op.definition or "")
    label = "OSTN15 grid shift" if ostn15 else op.name
    return f"{acc:.2f} m ({label})" if acc >= 0 else f"unknown ({label})"


# ---------------------------------------------------------------------------
# Command-line interface
# The block below only runs when the script is called directly from the
# terminal. It is skipped if this file is imported as a module by another
# Python script.
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    # Set up the command-line argument parser
    parser = argparse.ArgumentParser(description="Convert between BNG and WGS84 coordinates.")

    # Define two mutually exclusive options — the user must provide exactly one
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--to-wgs84", nargs=2, metavar=("EASTING", "NORTHING"), type=float,
                       help="Convert BNG easting/northing (metres) to WGS84")
    group.add_argument("--to-bng", nargs=2, metavar=("LAT", "LON"), type=float,
                       help="Convert WGS84 lat/lon (decimal degrees) to BNG")

    args = parser.parse_args()

    if args.to_wgs84:
        e, n = args.to_wgs84
        lat, lon = bng_to_wgs84(e, n)
        acc = _get_accuracy(_bng_to_wgs84)
        print(f"Easting:  {e:.3f} m")
        print(f"Northing: {n:.3f} m")
        print(f"→ Latitude:  {lat:.8f}°")
        print(f"→ Longitude: {lon:.8f}°")
        print(f"Transformation accuracy: {acc}")
    else:
        lat, lon = args.to_bng
        e, n = wgs84_to_bng(lat, lon)
        acc = _get_accuracy(_wgs84_to_bng)
        print(f"Latitude:  {lat:.8f}°")
        print(f"Longitude: {lon:.8f}°")
        print(f"→ Easting:  {e:.3f} m")
        print(f"→ Northing: {n:.3f} m")
        print(f"Transformation accuracy: {acc}")
