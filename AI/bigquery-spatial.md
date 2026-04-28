# BigQuery Geospatial — Claude Rules

## General Conventions

- Use consistent geometry column aliases: `geom` for `GEOMETRY`, `geog` for `GEOGRAPHY`.
- Store raw source geometries in a dedicated column. Create derived simplified or
  indexed columns separately — never overwrite source precision.
- Document the geometry type (Point, LineString, Polygon, Multi*, GeometryCollection)
  in column comments — BigQuery does not enforce single-type columns.
- Document the resolution/zoom level of any H3/Quadbin index column in a table comment.
- For tables frequently queried with bounding box filters, compute and store a `bbox`
  column at write time rather than deriving it at query time.

## CRS & Type System

- BigQuery `GEOGRAPHY` is always WGS84/geodetic. There is no SRID concept — don't
  try to store or cast SRIDs.
- Distances and areas are always in metres / square metres on the sphere. Results
  will differ from PostGIS planar equivalents — flag this when porting queries.

## Clustering & Table Management

- All tables containing geometry must be clustered by the geometry column (`CLUSTER BY geom`).
  BigQuery uses its native S2 indexing system to prune data at query time — this is the
  most efficient clustering strategy for geography columns.
- If a table has an H3 or Quadbin spatial index column, cluster by that column instead
  of the raw geometry — it is more selective.
- To change clustering or partitioning on an existing table, DROP it first —
  `CREATE OR REPLACE TABLE` cannot change the clustering/partitioning spec.
- Use time-partitioned tables instead of date-sharded tables (e.g. avoid
  `my_table_20240101` naming). Sharded tables add schema/metadata overhead and
  require permission checks per table at query time.

## Geometry Ingestion & Validity

Always use `make_valid => TRUE` — a single invalid geometry (self-intersection,
unclosed ring, etc.) will otherwise fail the entire query or load job:

```sql
ST_GEOGFROMTEXT(wkt_col,     make_valid => TRUE)
ST_GEOGFROMGEOJSON(json_col, make_valid => TRUE)
```

- Null geometries propagate silently through spatial functions — add
  `WHERE geom IS NOT NULL` guards in spatial joins.
- Coordinates must be `[lon, lat]` order in all constructors — `[lat, lon]` is the
  most common silent error in spatial pipelines.

## Spatial Index Columns (H3 / Quadbin)

H3 and Quadbin are not natively supported in BigQuery — both require the
**CARTO Analytics Toolbox**. Do not use these functions without confirming the
toolbox is installed. Native BigQuery spatial indexing uses S2.

The toolbox is available in two regions — use the prefix that matches your data:
- US: `carto-un.carto.<FUNCTION>`
- EU: `carto-un-eu.carto.<FUNCTION>`

**Type distinction:** H3 indexes are `STRING`; Quadbin indexes are `INT64`.
Never mix the two or cast between them.

**General rules:**
- Include the resolution in the column name or comment (e.g. `h3_res8`, `quadbin_z12`).
- Never mix resolutions within a single aggregation — always pass resolution explicitly.
- When joining on spatial index columns, ensure both sides use the same resolution.
- For parent/child traversal use the dedicated functions rather than re-indexing raw geometries.

### H3 Function Reference

| Concept | Function signature | Returns |
|---|---|---|
| Point → H3 index | `carto-un.carto.H3_FROMGEOGPOINT(point GEOGRAPHY, resolution INT64)` | `STRING` |
| Lon/lat → H3 index | `carto-un.carto.H3_FROMLONGLAT(longitude FLOAT64, latitude FLOAT64, resolution INT64)` | `STRING` |
| Polygon → H3 indexes | `carto-un.carto.H3_POLYFILL(geog GEOGRAPHY, resolution INT64)` | `ARRAY<STRING>` |
| Polygon → H3 indexes (with mode) | `carto-un.carto.H3_POLYFILL_MODE(geog GEOGRAPHY, resolution INT64, mode STRING)` | `ARRAY<STRING>` |
| Polygon → H3 indexes (large scale) | `carto-un.carto.H3_POLYFILL_TABLE(input_query STRING, resolution INT64, mode STRING, output_table STRING)` | procedure |
| H3 index → boundary polygon | `carto-un.carto.H3_BOUNDARY(index STRING)` | `GEOGRAPHY` |
| H3 index → centre point | `carto-un.carto.H3_CENTER(index STRING)` | `GEOGRAPHY` |
| H3 index → parent | `carto-un.carto.H3_TOPARENT(index STRING, resolution INT64)` | `STRING` |
| H3 index → children | `carto-un.carto.H3_TOCHILDREN(index STRING, resolution INT64)` | `ARRAY<STRING>` |
| Filled disk of k rings | `carto-un.carto.H3_KRING(origin STRING, size INT64)` | `ARRAY<STRING>` |
| Filled disk with distances | `carto-un.carto.H3_KRING_DISTANCES(origin STRING, size INT64)` | `ARRAY<STRUCT<index STRING, distance INT64>>` |
| Hollow ring at distance k | `carto-un.carto.H3_HEXRING(origin STRING, size INT64)` | `ARRAY<STRING>` |
| Grid distance between cells | `carto-un.carto.H3_DISTANCE(origin STRING, destination STRING)` | `INT64` |
| Resolution of index | `carto-un.carto.H3_RESOLUTION(index STRING)` | `INT64` |
| Compact array of indexes | `carto-un.carto.H3_COMPACT(indexArray ARRAY<STRING>)` | `ARRAY<STRING>` |
| Uncompact to resolution | `carto-un.carto.H3_UNCOMPACT(indexArray ARRAY<STRING>, resolution INT64)` | `ARRAY<STRING>` |
| Validate index | `carto-un.carto.H3_ISVALID(index STRING)` | `BOOL` |
| Is pentagon cell | `carto-un.carto.H3_ISPENTAGON(index STRING)` | `BOOL` |
| INT64 index → STRING | `carto-un.carto.H3_INT_TOSTRING(index INT64)` | `STRING` |
| STRING index → INT64 | `carto-un.carto.H3_STRING_TOINT(index STRING)` | `INT64` |

### Quadbin Function Reference

| Concept | Function signature | Returns |
|---|---|---|
| Point → Quadbin index | `carto-un.carto.QUADBIN_FROMGEOGPOINT(point GEOGRAPHY, resolution INT64)` | `INT64` |
| Lon/lat → Quadbin index | `carto-un.carto.QUADBIN_FROMLONGLAT(longitude FLOAT64, latitude FLOAT64, resolution INT64)` | `INT64` |
| Polygon → Quadbin indexes | `carto-un.carto.QUADBIN_POLYFILL(geog GEOGRAPHY, resolution INT64)` | `ARRAY<INT64>` |
| Polygon → Quadbin indexes (with mode) | `carto-un.carto.QUADBIN_POLYFILL_MODE(geog GEOGRAPHY, resolution INT64, mode STRING)` | `ARRAY<INT64>` |
| Polygon → Quadbin indexes (large scale) | `carto-un.carto.QUADBIN_POLYFILL_TABLE(input_query STRING, resolution INT64, mode STRING, output_table STRING)` | procedure |
| Quadbin index → boundary polygon | `carto-un.carto.QUADBIN_BOUNDARY(quadbin INT64)` | `GEOGRAPHY` |
| Quadbin index → centre point | `carto-un.carto.QUADBIN_CENTER(quadbin INT64)` | `GEOGRAPHY` |
| Quadbin index → bounding box | `carto-un.carto.QUADBIN_BBOX(quadbin INT64)` | `ARRAY<FLOAT64>` |
| Quadbin index → parent | `carto-un.carto.QUADBIN_TOPARENT(quadbin INT64, resolution INT64)` | `INT64` |
| Quadbin index → children | `carto-un.carto.QUADBIN_TOCHILDREN(quadbin INT64, resolution INT64)` | `ARRAY<INT64>` |
| Filled disk of k rings | `carto-un.carto.QUADBIN_KRING(origin INT64, size INT64)` | `ARRAY<INT64>` |
| Filled disk with distances | `carto-un.carto.QUADBIN_KRING_DISTANCES(origin INT64, size INT64)` | `ARRAY<STRUCT<index INT64, distance INT64>>` |
| Adjacent cell in direction | `carto-un.carto.QUADBIN_SIBLING(quadbin INT64, direction STRING)` | `INT64` |
| Grid distance between cells | `carto-un.carto.QUADBIN_DISTANCE(origin INT64, destination INT64)` | `INT64` |
| Resolution of index | `carto-un.carto.QUADBIN_RESOLUTION(quadbin INT64)` | `INT64` |
| Validate index | `carto-un.carto.QUADBIN_ISVALID(quadbin INT64)` | `BOOL` |
| Quadbin → quadkey string | `carto-un.carto.QUADBIN_TOQUADKEY(quadbin INT64)` | `STRING` |
| Quadkey string → Quadbin | `carto-un.carto.QUADBIN_FROMQUADKEY(quadkey STRING)` | `INT64` |
| Z/X/Y tile → Quadbin | `carto-un.carto.QUADBIN_FROMZXY(z INT64, x INT64, y INT64)` | `INT64` |
| Quadbin → Z/X/Y tile | `carto-un.carto.QUADBIN_TOZXY(quadbin INT64)` | `STRUCT<INT64, INT64, INT64>` |

## Querying Against Clustered Spatial Columns

BigQuery's spatial clustering uses S2 cell indexing under the hood. To get pruning
benefits from clustering, the query predicate must be compatible with the index:

- **Native geography clustering:** `ST_INTERSECTS`, `ST_CONTAINS`, `ST_WITHIN`,
  `ST_DWITHIN` all benefit from clustering on a `GEOGRAPHY` column. This is the
  most efficient pattern — prefer it.
- **Geohash string clustering:** If clustering by a geohash string column, you
  **must query using exact match or range predicates** on the full geohash value.
  Never use `LEFT(geohash_col, n)` or `RIGHT(geohash_col, n)` for prefix matching —
  these functions prevent BigQuery from using the cluster index and force a full
  table scan. Use a precomputed lower-resolution geohash column instead.

## Grouping & Aggregation

- Never GROUP BY geometry/geography columns. Always group on a non-spatial key and
  recover the geometry with `ANY_VALUE(geom)`.
- When deduplicating with `QUALIFY ROW_NUMBER() OVER (PARTITION BY ...)`, never
  partition by geometry — partition by a stable ID or hash.

## Spatial Joins & Query Performance

- **Always alias geometry columns in spatial joins** — both tables commonly have a
  column named `geom` or `geog`:
  ```sql
  SELECT
    a.id,
    a.geom AS geom_a,
    b.id   AS id_b,
    b.geom AS geom_b
  FROM table_a a
  JOIN table_b b ON ST_INTERSECTS(a.geom, b.geom)
  ```
- Always filter on non-spatial keys first to reduce row counts before applying
  spatial predicates.
- In a spatial join between a large and small table, place the larger table first —
  the query optimiser uses this for broadcast join decisions.
- Never use `ST_DISTANCE` in a WHERE clause for radius searches — use
  `ST_DISTANCE(...) < x` with a coarse bounding box pre-filter.
- Cross-join spatial operations require a reviewer sign-off — they are among the most
  expensive query patterns.

## Anti-Patterns

- **`SELECT *`** — always select only the columns needed. BigQuery is columnar;
  geometry columns are wide and expensive to read unnecessarily.
- **`ORDER BY` without `LIMIT`** — a common pattern when ranking results by distance
  or area. Sorting a very large result set runs on a single slot and will throw a
  Resources Exceeded error. Always pair `ORDER BY` with a `LIMIT` on large tables.
- **Date-sharded table names** (e.g. `events_20240101`) — use time-partitioned tables
  instead. Sharded tables require BigQuery to check permissions and load metadata for
  each table individually, which compounds when spatial queries span many shards.

## Function Reference

| Concept             | Function                          |
|---------------------|-----------------------------------|
| WKT → geography     | `ST_GEOGFROMTEXT`                 |
| GeoJSON → geography | `ST_GEOGFROMGEOJSON`              |
| Geography → WKT     | `ST_ASTEXT`                       |
| Geography → GeoJSON | `ST_ASGEOJSON`                    |
| Point from coords   | `ST_GEOGPOINT(lon, lat)`          |
| Bounding box        | `ST_BOUNDINGBOX` (returns STRUCT) |
| Centroid            | `ST_CENTROID`                     |
| Area                | `ST_AREA` (sq metres)             |
| Within distance     | `ST_DISTANCE(...) < x`            |
