# Geospatial Data Warehouse — Claude Rules

## General Conventions

- Use consistent geometry column aliases across all models: `geom` for `GEOMETRY`,
  `geog` for `GEOGRAPHY`.
- Store raw source geometries in a dedicated column. Create derived simplified or
  indexed columns separately — never overwrite source precision.
- Document the geometry type (Point, LineString, Polygon, Multi*, GeometryCollection)
  in column comments — neither platform enforces single-type columns.
- Document the resolution/zoom level of any H3/Quadbin index column in a table comment.
- For tables frequently queried with bounding box filters, compute and store a `bbox`
  column at write time rather than deriving it at query time.

## CRS & Type System

- Both BigQuery `GEOGRAPHY` and Snowflake `GEOGRAPHY` are always WGS84/geodetic.
  There is no SRID concept — don't try to store or cast SRIDs.
- Snowflake also has a `GEOMETRY` type which supports arbitrary SRIDs. Never mix
  `GEOGRAPHY` and `GEOMETRY` in the same pipeline without explicit conversion.
- Distances and areas are always in metres / square metres on the sphere. Results
  will differ from PostGIS planar equivalents — flag this when porting queries.

## Clustering & Table Management

**BigQuery:**
- All tables containing geometry must be clustered by the geometry column (`CLUSTER BY geom`).
  BigQuery uses its native S2 indexing system to prune data at query time — this is the
  most efficient clustering strategy for geography columns.
- To change clustering or partitioning on an existing table, DROP it first —
  `CREATE OR REPLACE TABLE` cannot change the clustering/partitioning spec.
- Use time-partitioned tables instead of date-sharded tables (e.g. avoid
  `my_table_20240101` naming). Sharded tables add schema/metadata overhead and
  require permission checks per table at query time.

**Snowflake:**
- Cluster tables on the geohash of the geography column:
  `CLUSTER BY (ST_GEOHASH(geog, 6))` — tune precision (5–7) to match typical query
  bounding boxes.
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

**Both platforms:**
- If a table has an H3 or Quadbin spatial index column, cluster by that column instead
  of the raw geometry/geography — it is more selective.

## Geometry Ingestion & Validity

**BigQuery — always use `make_valid => TRUE`:**
```sql
ST_GEOGFROMTEXT(wkt_col,     make_valid => TRUE)
ST_GEOGFROMGEOJSON(json_col, make_valid => TRUE)
```
A single invalid geometry (self-intersection, unclosed ring, etc.) will otherwise
fail the entire query or load job.

**Snowflake — always use the safe constructors in pipelines:**
```sql
TRY_TO_GEOGRAPHY(col)   -- soft failure, returns NULL on bad input
TRY_TO_GEOMETRY(col)    -- equivalent for GEOMETRY type
```

**Both platforms:**
- Null geometries propagate silently through spatial functions — add
  `WHERE geom IS NOT NULL` guards in spatial joins.
- Coordinates must be `[lon, lat]` order in all constructors — `[lat, lon]` is the
  most common silent error in spatial pipelines.

## Spatial Index Columns (H3 / Quadbin)

- Include the resolution in the column name or comment (e.g. `h3_res8`, `quadbin_z12`).
- Never mix resolutions within a single aggregation — always pass the resolution
  explicitly to `H3_LATLNG_TO_CELL` / `QUADBIN_FROMLONGLAT`.
- When joining on spatial index columns, ensure both sides use the same resolution.
- For parent/child traversal use `H3_CELL_TO_PARENT` / `H3_GRID_DISK` rather than
  re-indexing raw geometries.
- **BigQuery only:** H3 is not natively supported in BigQuery — it requires the CARTO
  Analytics Toolbox. Do not use H3 functions in BigQuery without confirming the
  toolbox is installed. Native BigQuery spatial indexing uses S2.

## Querying Against Clustered Spatial Columns (BigQuery)

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

## Snowflake: Predicates That Disable Micro-Partition Pruning

These patterns are common in spatial pipelines and silently prevent Snowflake from
skipping micro-partitions, causing full table scans:

- **Subqueries in WHERE predicates** — Snowflake cannot prune on a predicate that
  contains a subquery, even if it resolves to a constant. This is a common pattern
  when filtering spatial tables by a reference date or latest load timestamp:
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
  recover the geometry with `ANY_VALUE(geom)`.
- When deduplicating with `QUALIFY ROW_NUMBER() OVER (PARTITION BY ...)`, never
  partition by geometry — partition by a stable ID or hash.

## Spatial Joins & Query Performance

- **Always alias geometry columns in spatial joins** — both tables commonly have a
  column named `geom` or `geog`. Always alias at the column level to avoid silent
  name collisions in the output:
  ```sql
  SELECT
    a.id,
    a.geom AS geom_a,
    b.id   AS id_b,
    b.geom AS geom_b
  FROM table_a a
  JOIN table_b b ON ST_INTERSECTS(a.geom, b.geom)
  ```
  Omitting aliases means downstream queries or tools may silently read the wrong
  geometry column, or the join output may only materialise one of the two.
- Always filter on non-spatial keys first to reduce row counts before applying
  spatial predicates.
- On BigQuery, in a spatial join between a large and small table, place the larger
  table first — the query optimiser uses this for broadcast join decisions.
- Never use `ST_DISTANCE` in a WHERE clause for radius searches — prefer `ST_DWITHIN`
  (Snowflake) or `ST_DISTANCE(...) < x` with a coarse bounding box pre-filter (BigQuery).
- Cross-join spatial operations require a reviewer sign-off — they are among the most
  expensive query patterns on both platforms.

## Snowflake: Memory Spillage on Spatial Operations

Complex geometry columns (large polygons, multipolygons, linestrings with many
vertices) combined with spatial joins or functions like `ST_INTERSECTION` and
`ST_DIFFERENCE` are among the most memory-intensive operations in Snowflake.

- Spillage on spatial queries indicates the warehouse is undersized for the geometry
  complexity, or the query needs restructuring (e.g. pre-filtering to reduce row
  counts before applying spatial predicates, or simplifying geometries before joining).
- `ST_SIMPLIFY` complex source geometries into a separate column at write time for
  use in joins and filters, preserving the full-precision geometry for output only.

## Snowflake: GeoJSON Properties in VARIANT Columns

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

## BigQuery: Geospatially Relevant Anti-Patterns

- **`SELECT *`** — always select only the columns needed. BigQuery is columnar;
  geometry columns are wide and expensive to read unnecessarily.
- **`ORDER BY` without `LIMIT`** — a common pattern when ranking results by distance
  or area. Sorting a very large result set runs on a single slot and will throw a
  Resources Exceeded error. Always pair `ORDER BY` with a `LIMIT` on large tables.
- **Date-sharded table names** (e.g. `events_20240101`) — use time-partitioned tables
  instead. Sharded tables require BigQuery to check permissions and load metadata for
  each table individually, which compounds when spatial queries span many shards.

## Function Reference

| Concept             | BigQuery                          | Snowflake                            |
|---------------------|-----------------------------------|--------------------------------------|
| WKT → geography     | `ST_GEOGFROMTEXT`                 | `TRY_TO_GEOGRAPHY`                   |
| GeoJSON → geography | `ST_GEOGFROMGEOJSON`              | `TRY_TO_GEOGRAPHY` (accepts GeoJSON) |
| Geography → WKT     | `ST_ASTEXT`                       | `ST_ASTEXT`                          |
| Geography → GeoJSON | `ST_ASGEOJSON`                    | `ST_ASGEOJSON`                       |
| Point from coords   | `ST_GEOGPOINT(lon, lat)`          | `ST_MAKEPOINT(lon, lat)`             |
| Bounding box        | `ST_BOUNDINGBOX` (returns STRUCT) | `ST_ENVELOPE`                        |
| Centroid            | `ST_CENTROID`                     | `ST_CENTROID`                        |
| Area                | `ST_AREA` (sq metres)             | `ST_AREA` (sq metres)                |
| Within distance     | `ST_DISTANCE(...) < x`            | `ST_DWITHIN`                         |
