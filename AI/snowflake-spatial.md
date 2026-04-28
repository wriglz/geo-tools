# Snowflake Geospatial — Claude Rules

## General Conventions

- Use consistent geometry column aliases: `geom` for `GEOMETRY`, `geog` for `GEOGRAPHY`.
- Store raw source geometries in a dedicated column. Create derived simplified or
  indexed columns separately — never overwrite source precision.
- Document the geometry type (Point, LineString, Polygon, Multi*, GeometryCollection)
  in column comments — Snowflake does not enforce single-type columns.
- Document the resolution/zoom level of any H3/Quadbin index column in a table comment.
- For tables frequently queried with bounding box filters, compute and store a `bbox`
  column at write time rather than deriving it at query time.

## CRS & Type System

- Snowflake `GEOGRAPHY` is always WGS84/geodetic. There is no SRID concept on
  `GEOGRAPHY` — don't try to store or cast SRIDs.
- Snowflake also has a `GEOMETRY` type which supports arbitrary SRIDs. Never mix
  `GEOGRAPHY` and `GEOMETRY` in the same pipeline without explicit conversion.
- Distances and areas are always in metres / square metres on the sphere. Results
  will differ from PostGIS planar equivalents — flag this when porting queries.

## Clustering & Table Management

- Cluster tables on the geohash of the geography column:
  `CLUSTER BY (ST_GEOHASH(geog, 6))` — tune precision (5–7) to match typical query
  bounding boxes.
- If a table has an H3 or Quadbin spatial index column, cluster by that column instead
  of the raw geography — it is more selective.
- A table can only have one cluster key. Choosing a geohash or spatial index column
  as the cluster key means non-spatial range filters on other columns (e.g. date,
  region) will not benefit from clustering pruning. If those filters are equally
  important, consider a materialized view with a different cluster key, or add Search
  Optimization on the non-spatial columns instead.
- Only apply clustering to large tables where queries are selective on the cluster
  key. Snowflake performs automatic micro-partition tuning on smaller tables and
  explicit clustering adds ongoing serverless compute cost with little benefit
  otherwise.
- Add search optimisation on the geography column where the tier supports it:
  `ALTER TABLE t ADD SEARCH OPTIMIZATION ON GEO(geog)`.
- If the table has both Automatic Clustering and Search Optimization enabled,
  every recluster triggers Search Optimization maintenance as well. This compounding
  cost is significant on tables that are frequently refreshed with new geometries —
  flag this when designing pipelines for high-DML spatial tables.

## Geometry Ingestion & Validity

Always use the safe constructors in pipelines — they return NULL on bad input rather
than failing the entire query:

```sql
TRY_TO_GEOGRAPHY(col)   -- for GEOGRAPHY type
TRY_TO_GEOMETRY(col)    -- for GEOMETRY type
```

- Null geometries propagate silently through spatial functions — add
  `WHERE geog IS NOT NULL` guards in spatial joins.
- Coordinates must be `[lon, lat]` order in all constructors — `[lat, lon]` is the
  most common silent error in spatial pipelines.

## Spatial Index Columns (H3 / Quadbin)

**General rules:**
- Include the resolution in the column name or comment (e.g. `h3_res8`, `quadbin_z12`).
- Never mix resolutions within a single aggregation — always pass resolution explicitly.
- When joining on spatial index columns, ensure both sides use the same resolution.
- For parent/child traversal use the dedicated functions rather than re-indexing raw geometries.

### H3 — Native Snowflake Functions (prefer these)

Snowflake has comprehensive native H3 support — use these in preference to the CARTO
toolbox equivalents. Most functions have both an integer (`INT`) and string (`STRING`)
variant; use the string variants for readability, integer variants for storage efficiency.

| Concept | Function |
|---|---|
| Point → H3 index | `H3_POINT_TO_CELL_STRING(point GEOGRAPHY, resolution INT)` |
| Lon/lat → H3 index | `H3_LATLNG_TO_CELL_STRING(lat FLOAT, lon FLOAT, resolution INT)` |
| Polygon → H3 indexes | `H3_COVERAGE_STRINGS(geog GEOGRAPHY, resolution INT)` |
| Polygon polyfill (strict) | `H3_POLYGON_TO_CELLS_STRINGS(geog GEOGRAPHY, resolution INT)` |
| H3 index → boundary polygon | `H3_CELL_TO_BOUNDARY(cell STRING)` |
| H3 index → centre point | `H3_CELL_TO_POINT(cell STRING)` |
| H3 index → parent | `H3_CELL_TO_PARENT(cell STRING, resolution INT)` |
| H3 index → children | `H3_CELL_TO_CHILDREN_STRING(cell STRING, resolution INT)` |
| Filled disk of k rings | `H3_GRID_DISK(cell STRING, k INT)` |
| Grid distance between cells | `H3_GRID_DISTANCE(origin STRING, destination STRING)` |
| Path of cells between two cells | `H3_GRID_PATH(origin STRING, destination STRING)` |
| Resolution of index | `H3_GET_RESOLUTION(cell STRING)` |
| Compact array of indexes | `H3_COMPACT_CELLS_STRINGS(cells ARRAY)` |
| Uncompact to resolution | `H3_UNCOMPACT_CELLS_STRINGS(cells ARRAY, resolution INT)` |
| Validate index | `H3_IS_VALID_CELL(cell STRING)` |
| Is pentagon cell | `H3_IS_PENTAGON(cell STRING)` |
| INT64 index → STRING | `H3_INT_TO_STRING(cell INT)` |
| STRING index → INT64 | `H3_STRING_TO_INT(cell STRING)` |

TRY variants (return NULL on error rather than failing): `H3_TRY_COVERAGE`,
`H3_TRY_COVERAGE_STRINGS`, `H3_TRY_GRID_DISTANCE`, `H3_TRY_GRID_PATH`,
`H3_TRY_POLYGON_TO_CELLS`, `H3_TRY_POLYGON_TO_CELLS_STRINGS`.

### H3 — CARTO Analytics Toolbox Additions (3 functions with no native equivalent)

The CARTO toolbox H3 functions largely duplicate native Snowflake functions with
different names. Only reach for CARTO when you need one of these three capabilities.
Prefix: `CARTO.CARTO.<FUNCTION>`

```sql
-- Hollow ring at exactly distance k (native H3_GRID_DISK gives a filled disk)
CARTO.CARTO.H3_HEXRING(origin STRING, size INT) → ARRAY

-- Filled disk annotated with each cell's grid distance from the origin
-- (native H3_GRID_DISK returns cells only, no distance metadata)
CARTO.CARTO.H3_KRING_DISTANCES(origin STRING, size INT) → ARRAY
-- Returns: [{index STRING, distance INT}, ...]

-- Large-scale polyfill that writes results to a table rather than returning an ARRAY
-- (avoids ARRAY size limits for country-scale or fine-resolution fills)
CARTO.CARTO.H3_POLYFILL_TABLE(
    input_query  STRING,   -- SQL query returning a geometry column
    resolution   INT,
    mode         STRING,   -- 'center' | 'contains' | 'intersects'
    output_table STRING    -- fully-qualified destination table
) → procedure (no return value)
```

### Quadbin — CARTO Analytics Toolbox (no native Snowflake alternative)

Snowflake has zero native Quadbin support. All Quadbin work requires the CARTO
Analytics Toolbox. Prefix: `CARTO.CARTO.<FUNCTION>`

**Type note:** Quadbin indexes are `BIGINT` (integer), not strings.

| Concept | Function signature | Returns |
|---|---|---|
| Point → Quadbin index | `CARTO.CARTO.QUADBIN_FROMGEOGPOINT(point GEOGRAPHY, resolution INT)` | `BIGINT` |
| Lon/lat → Quadbin index | `CARTO.CARTO.QUADBIN_FROMLONGLAT(longitude FLOAT64, latitude FLOAT64, resolution INT)` | `BIGINT` |
| Polygon → Quadbin indexes | `CARTO.CARTO.QUADBIN_POLYFILL(geography GEOGRAPHY, resolution INT)` | `ARRAY<BIGINT>` |
| Quadbin index → boundary polygon | `CARTO.CARTO.QUADBIN_BOUNDARY(quadbin BIGINT)` | `GEOGRAPHY` |
| Quadbin index → centre point | `CARTO.CARTO.QUADBIN_CENTER(quadbin BIGINT)` | `GEOGRAPHY` |
| Quadbin index → bounding box | `CARTO.CARTO.QUADBIN_BBOX(quadbin BIGINT)` | `ARRAY<FLOAT64>` (W, S, E, N) |
| Quadbin index → parent | `CARTO.CARTO.QUADBIN_TOPARENT(quadbin BIGINT, resolution INT)` | `BIGINT` |
| Quadbin index → children | `CARTO.CARTO.QUADBIN_TOCHILDREN(quadbin BIGINT, resolution INT)` | `ARRAY<BIGINT>` |
| Filled disk of k rings | `CARTO.CARTO.QUADBIN_KRING(origin BIGINT, size INT)` | `ARRAY<BIGINT>` |
| Filled disk with distances | `CARTO.CARTO.QUADBIN_KRING_DISTANCES(origin BIGINT, size INT)` | `ARRAY<STRUCT>` |
| Adjacent tile in direction | `CARTO.CARTO.QUADBIN_SIBLING(quadbin BIGINT, direction STRING)` | `BIGINT` (direction: `'left'\|'right'\|'up'\|'down'`) |
| Grid distance between tiles | `CARTO.CARTO.QUADBIN_DISTANCE(origin BIGINT, destination BIGINT)` | `BIGINT` |
| Resolution of index | `CARTO.CARTO.QUADBIN_RESOLUTION(quadbin BIGINT)` | `INT` |
| Validate index | `CARTO.CARTO.QUADBIN_ISVALID(quadbin BIGINT)` | `BOOLEAN` |
| Quadbin → Quadkey string | `CARTO.CARTO.QUADBIN_TOQUADKEY(quadbin BIGINT)` | `STRING` |
| Quadkey string → Quadbin | `CARTO.CARTO.QUADBIN_FROMQUADKEY(quadkey STRING)` | `BIGINT` |
| Z/X/Y tile → Quadbin | `CARTO.CARTO.QUADBIN_FROMZXY(z INT, x INT, y INT)` | `BIGINT` |
| Quadbin → Z/X/Y tile | `CARTO.CARTO.QUADBIN_TOZXY(quadbin BIGINT)` | `STRUCT<INT, INT, INT>` |

## Predicates That Disable Micro-Partition Pruning

These patterns are common in spatial pipelines and silently prevent Snowflake from
skipping micro-partitions, causing full table scans:

- **Subqueries in WHERE predicates** — Snowflake cannot prune on a predicate that
  contains a subquery, even if it resolves to a constant:
  ```sql
  -- Bad: disables pruning
  WHERE load_date > (SELECT MAX(load_date) FROM ref_table)

  -- Good: materialise first
  SET max_date = (SELECT MAX(load_date) FROM ref_table);
  WHERE load_date > $max_date
  ```
- **`UPPER()` / `LOWER()` in filter predicates** — case functions on columns (e.g.
  place names, region codes, category fields attached to spatial features) disable
  pruning. Store string data in a consistent case at load time and filter without
  case-transformation functions.

## Grouping & Aggregation

- Never GROUP BY geometry/geography columns. Always group on a non-spatial key and
  recover the geometry with `ANY_VALUE(geog)`.
- When deduplicating with `QUALIFY ROW_NUMBER() OVER (PARTITION BY ...)`, never
  partition by geometry — partition by a stable ID or hash.

## Spatial Joins & Query Performance

- **Always alias geometry columns in spatial joins** — both tables commonly have a
  column named `geom` or `geog`:
  ```sql
  SELECT
    a.id,
    a.geog AS geog_a,
    b.id   AS id_b,
    b.geog AS geog_b
  FROM table_a a
  JOIN table_b b ON ST_INTERSECTS(a.geog, b.geog)
  ```
- Always filter on non-spatial keys first to reduce row counts before applying
  spatial predicates.
- Prefer `ST_DWITHIN` over `ST_DISTANCE` in WHERE clauses for radius searches.
- Cross-join spatial operations require a reviewer sign-off — they are among the most
  expensive query patterns.

## Memory Spillage on Spatial Operations

Complex geometry columns (large polygons, multipolygons, linestrings with many
vertices) combined with spatial joins or functions like `ST_INTERSECTION` and
`ST_DIFFERENCE` are among the most memory-intensive operations in Snowflake.

- Spillage on spatial queries indicates the warehouse is undersized for the geometry
  complexity, or the query needs restructuring (e.g. pre-filtering to reduce row
  counts before applying spatial predicates, or simplifying geometries before joining).
- `ST_SIMPLIFY` complex source geometries into a separate column at write time for
  use in joins and filters, preserving the full-precision geometry for output only.

## GeoJSON Properties in VARIANT Columns

Spatial data pipelines that ingest raw GeoJSON frequently store feature properties in
a VARIANT column. This causes pruning and performance problems when those properties
are used as filters:

- Dates and timestamps stored as strings inside VARIANT are treated as strings by
  the query engine — range filters on them are slow and do not prune micro-partitions
  effectively.
- Extract frequently filtered properties (dates, IDs, category codes) into proper
  typed relational columns at load time. Keep the raw VARIANT for archival or
  schema-flexible access only.
- If VARIANT querying is unavoidable, add Search Optimization on the specific VARIANT
  paths that are queried most frequently.

## Function Reference

| Concept             | Function                             |
|---------------------|--------------------------------------|
| WKT → geography     | `TRY_TO_GEOGRAPHY`                   |
| GeoJSON → geography | `TRY_TO_GEOGRAPHY` (accepts GeoJSON) |
| Geography → WKT     | `ST_ASTEXT`                          |
| Geography → GeoJSON | `ST_ASGEOJSON`                       |
| Point from coords   | `ST_MAKEPOINT(lon, lat)`             |
| Bounding box        | `ST_ENVELOPE`                        |
| Centroid            | `ST_CENTROID`                        |
| Area                | `ST_AREA` (sq metres)                |
| Within distance     | `ST_DWITHIN`                         |
