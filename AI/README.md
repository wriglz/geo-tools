# AI Context Files

This directory contains markdown files that provide Claude with rules and conventions
for geospatial work in this repository. Load the relevant file(s) into your Claude
conversation depending on which platform you are working with.

## Files

### [claude.md](claude.md)
The combined reference covering both BigQuery and Snowflake. Use this when working
across both platforms or when the platform is not yet decided.

### [bigquery-spatial.md](bigquery-spatial.md)
BigQuery-specific rules. Covers clustering with S2 geography columns, geometry
ingestion with `make_valid`, spatial index columns (H3 requires CARTO Toolbox),
query patterns that benefit from clustering, and common anti-patterns.

### [snowflake-spatial.md](snowflake-spatial.md)
Snowflake-specific rules. Covers clustering with `ST_GEOHASH`, the `GEOMETRY` vs
`GEOGRAPHY` distinction, safe constructors (`TRY_TO_GEOGRAPHY`), predicates that
disable micro-partition pruning, memory spillage on spatial operations, and GeoJSON
properties in VARIANT columns.
