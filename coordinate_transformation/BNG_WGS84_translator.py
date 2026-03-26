"""
Convert between British National Grid (OSGB36) and WGS84 coordinates.
Uses OSTN15 NTv2 grid shift via PROJ (downloaded and cached on first use).
"""

import argparse
import pyproj

pyproj.network.set_network_enabled(True)

# Explicit OSTN15 pipelines — forces use of OSTN15 grid shift.
# Raises an error at startup if the grid file cannot be found or downloaded.
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


def bng_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    lon, lat = _bng_to_wgs84.transform(easting, northing)
    return lat, lon


def wgs84_to_bng(lat: float, lon: float) -> tuple[float, float]:
    easting, northing = _wgs84_to_bng.transform(lon, lat)
    return easting, northing


def _get_accuracy(transformer: pyproj.Transformer) -> str:
    op = transformer.get_last_used_operation()
    if op is None:
        return "unknown"
    acc = op.accuracy
    ostn15 = "OSTN15" in (op.definition or "")
    label = "OSTN15 grid shift" if ostn15 else op.name
    return f"{acc:.2f} m ({label})" if acc >= 0 else f"unknown ({label})"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert between BNG and WGS84 coordinates.")
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
