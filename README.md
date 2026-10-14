# Garmin IMG Parser

A Python library for reading Garmin IMG files — the map format used by
Garmin GPS devices and BaseCamp/MapSource.

[Русская версия](README.ru.md)

## Features

- Read single `.img` files and `gmapsupp.img` containers with multiple maps
- Automatic XOR-decryption; skip NT-format maps gracefully
- Extract points, polylines, polygons with WGS84 coordinates and labels
- Full Garmin type dictionaries (~500 entries)
- Export to 5 formats: MP (Polish Format), GeoJSON, GPX, CSV (points only), Shapefile
- Polygonize closed boundary lines into polygons
- Deduplicate objects across zoom levels
- Batch export all maps from a container into separate folders
- Optional per-type split of shapefiles (`export_by_types_shapefiles`)

## Installation

No required dependencies — just copy `garmin_img.py` into your project.

For Shapefile export, install `pyshp`:

    pip install pyshp

Verify:

    python -c "from garmin_img import open_img; print('OK')"

## Quick start

### Single map

    from garmin_img import open_img

    img = open_img("map.img")
    print(img.summary())

    # Export all lines at the most detailed zoom level
    img.export_shapefile("out/lines", kinds=('lines',), filter_level=0)

### Container (gmapsupp.img)

    from garmin_img import open_img

    cont = open_img("gmapsupp.img")
    print(f"Maps: {len(cont)}")

    for r in cont.list_light():
        print(r['id'], r['name'])

    img = cont.find("38000035")
    img.export_mp("out.mp")

### Batch export

    python extract_all_maps.py gmapsupp.img output_folder

## Opening maps

`open_img(path)` auto-detects the file type and returns:

- `GarminIMG` — for a single map
- `GarminIMGContainer` — for a container with several maps

    obj = open_img("file.img")
    if hasattr(obj, "submaps"):
        print("container")
    else:
        print("single map")

You can also open explicitly:

    from garmin_img import GarminIMG, GarminIMGContainer

    img  = GarminIMG("file.img")
    cont = GarminIMGContainer("gmapsupp.img")

## Metadata

All map info is in `img.metadata`:

| Field | Description |
|---|---|
| `name` | name from the IMG header |
| `submap_name` | name from MPS (for container submaps) |
| `submap_id` | submap ID (e.g. `"38000035"`) |
| `map_id` | numeric map ID |
| `codepage` | LBL codepage (1251, 1252, 65001, ...) |
| `encoding` | LBL encoding (6, 9, 10) |
| `north`, `east`, `south`, `west` | map bounds |
| `locked` | whether the map is encrypted |
| `size_bytes` | file size |

    print(img.get_display_name())   # MPS → IMG header → file name
    print(img.summary())            # full text report

## Reading objects

Three ways to get objects:

| Method | When to use |
|---|---|
| `img.points / img.polylines / img.polygons` | cached, read once |
| `img.iter_points() / iter_polylines() / iter_polygons()` | lazy, saves memory |
| `img.iter_all(kinds)` | several kinds at once |

For big maps (>10,000 objects) use the `iter_*` methods:

    for p in img.iter_points():
        process(p)

For repeated access use the cached properties and clear them when done:

    for p in img.points:
        process(p)
    img.clear_cache()

### Point

    p.kind        # 'point'
    p.type        # int, 16-bit type code (0x1500, 0x1E00, ...)
    p.subtype     # int or None
    p.label       # str, label from LBL
    p.lat, p.lon  # WGS84 coordinates
    p.level       # zoom level
    p.type_name   # name from Garmin dictionary (property)

### Polyline

    pl.type         # int, 8-bit type code (0x05, 0x06, ...)
    pl.label        # str
    pl.level        # int
    pl.points       # list of (lon, lat)
    pl.direction    # bool — one-way
    pl.in_net       # bool — has data in NET
    pl.type_name    # str
    pl.type_group   # 'road', 'water', 'boundary', ...

### Polygon

Same fields as Polyline (`type`, `label`, `level`, `points`, `type_name`).

## Garmin type dictionaries

    from garmin_img import (POINT_TYPES, POLYLINE_TYPES,
                            POLYGON_TYPES, POLYLINE_GROUPS)

    POINT_TYPES[0x1500]     # 'Minor country name'
    POLYLINE_TYPES[0x06]    # 'Residential street'
    POLYGON_TYPES[0x50]     # 'Forest'
    POLYLINE_GROUPS[0x06]   # 'road'

Safe lookup with fallback:

    from garmin_img import (guess_point_type, guess_line_type,
                            guess_polygon_type)

    guess_point_type(0x1500)   # 'Minor country name'
    guess_line_type(0xAA)      # 'Unknown line (0xAA)'

Dictionary sizes: `POINT_TYPES` ~500, `POLYLINE_TYPES` 36,
`POLYGON_TYPES` 56, `POLYLINE_GROUPS` ~30.

## Custom types

Register your own names before opening a map:

    from garmin_img import (register_point_type, register_line_type,
                            register_polygon_type, register_line_group)

    register_point_type(0x1F00, "Compartment number")
    register_line_type(0x16, "Compartment boundary", group="border")
    register_polygon_type(0x50, "Coniferous forest")
    register_line_group(0x1D, "boundary")

Or load from a text file:

    [POINT]
    0x1F00 = Compartment number
    0x1400 = Quarter number

    [LINE]
    0x16 = Compartment boundary @border
    0x1F = River @water

    [POLYGON]
    0x50 = Coniferous forest

    from garmin_img import load_types_from_file
    load_types_from_file("my_types.txt", verbose=True)

Save current types to a file:

    from garmin_img import save_types_to_file
    save_types_to_file("types.txt")

## Predicates

17 helper functions for quick type checks:

    from garmin_img import (is_city_point, is_hw_exit_point,
                            is_height_point, is_feature_point,
                            has_address_point, is_navaid_point,
                            is_road_line, is_unpaved_road, is_roundabout,
                            is_height_line, is_background_polygon,
                            is_water_line, is_rail_line, is_border_line,
                            is_water_polygon, is_land_polygon)

    is_city_point(0x0400)   # True
    is_road_line(0x06)      # True
    is_water_line(0x1F)     # True
    is_border_line(0x1D)    # True

## Filters and queries

### By type

    img.points_by_type(0x1500)
    img.polylines_by_type(0x05, 0x06)
    img.polygons_by_type(0x50)

### By level

    img.polylines_by_level(0)

### By group

    img.polylines_by_group("road")
    img.polylines_by_group("water")
    img.polylines_by_group("boundary")

### Universal filter

    img.filter(kind='line', group='road', level=0)
    img.filter(types={0x01, 0x02, 0x03})
    img.filter(kind='point', predicate=lambda o: is_city_point(o.type))

### Counts

    img.has_type(0x06, kind='line')     # bool
    img.count_type(0x1500)              # int
    img.types_present()                 # {'point': {type: count, ...}, ...}

## Geo queries

### Nearby objects

    for dist, obj in img.near(lat=51.05, lon=137.74,
                              radius_km=2, kind='point', limit=10):
        print(f"{dist:.3f} km {obj.label!r}")

### Search by label

    img.search_labels("Lenina")                 # substring
    img.search_labels("river", regex=True, kind='line')
    img.search_labels("LAKE", ignore_case=True)

### Longest objects

    for length_m, pl in img.longest(n=20, kind='line', group='road'):
        print(f"{length_m/1000:8.2f} km {pl.label or '(unnamed)'}")

### Total length

    img.total_length_m(group='road')    # meters
    img.total_length_m(group='water')

### Bounding box

    img.bbox_of(type=0x50)              # (min_lon, min_lat, max_lon, max_lat)
    img.bbox_of(kind='line', group='road')

## Export

Five output formats are supported.

### Polish Format (.mp) — for GPSMapEdit, cGPSmapper

    img.export_mp("out.mp")
    img.export_mp("out.mp", levels={0})              # only level 0
    img.export_mp("out.mp", levels={0, 1, 2})        # three levels
    img.export_mp("out.mp", snap_to_grid=True)       # snap to Garmin grid

`snap_to_grid=True` rounds coordinates to the Garmin grid before writing,
so GPSMapEdit won't shift them on load. Coordinates use round-half-away-
from-zero, which works correctly for the southern hemisphere and western
longitudes.

### GeoJSON — for QGIS, Leaflet, Mapbox

    img.export_geojson("out.geojson")

### GPX — for Garmin GPS devices, Strava, OSM

    img.export_gpx("out.gpx")

### CSV — points only

    img.export_csv("points.csv")

### Shapefile — requires `pyshp`

    # All lines
    img.export_shapefile("lines", kinds=('lines',))

    # Only quarters (type 0x05) at level 0
    img.export_shapefile("quarters", kinds=('lines',),
                         filter_types={0x05}, filter_level=0)

    # All roads at level 0
    img.export_shapefile("roads", kinds=('lines',),
                         filter_group="road", filter_level=0)

    # Points of type 0x1E00
    img.export_shapefile("numbers", kinds=('points',),
                         filter_types={0x1E00})

Creates 5 files: `.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`.

DBF fields: `ID`, `TYPE_HEX`, `TYPE_NAME`, `TYPE_GROUP`, `ZOOM`,
`N_POINTS`, `LENGTH_M`, `ONEWAY`, `ROUTABLE`, `SUBTYPE`,
`MINLON`/`MINLAT`/`MAXLON`/`MAXLAT`, `LABEL`.

### Shortcuts

    img.export_roads_shapefile("roads")             # group 'road'
    img.export_roads_shapefile("roads", level=0)    # only level 0
    img.export_water_shapefile("rivers")            # group 'water'
    img.extract_shape(0x16, "boundaries", kind='line')   # one type

### All three layers at once

    result = img.export_all_shapefiles("out_dir", level=0)
    # → out_dir/points.shp, lines.shp, polygons.shp
    # result: {'points': N, 'lines': N, 'polygons': N}

### Per-type split

    img.export_by_types_shapefiles("out_types", level=0)
    # → out_types/points_1400.shp, lines_06.shp, polygons_50.shp

File names use hex type codes. Handy for QGIS: instead of one giant
`lines.shp` you get many small files you can open individually.

## Polygonize closed lines

Useful for forest maps where quarters are stored as closed boundary
lines, not as polygons.

    n_poly, n_open = img.polygonize_shapefile(
        "quarters",
        types=(0x1D,),      # which line types to treat as polygons
        tolerance=1e-6,     # closure tolerance
        filter_level=None)  # level, or None for all
    print(f"Polygons: {n_poly}, unclosed dropped: {n_open}")

A line is considered closed if its first and last points match within
`tolerance`. Closed lines become polygons; open ones are dropped.

## Deduplication

An object can appear on several zoom levels. A plain `export_shapefile`
would create duplicates.

    img.export_dedup_shapefile("points_unique", kind='points')
    # kind: 'points' | 'lines' | 'polygons'

Extra DBF fields: `MIN_LEVEL` (most detailed level), `N_LEVELS`
(number of levels where the object appears).

## Container (gmapsupp.img)

    cont = open_img("gmapsupp.img")

    len(cont)             # number of maps
    for img in cont:      # iterate
        print(img.submap_id, img.get_display_name())
    cont[0]               # by index
    cont.submaps          # list

    # Quick list
    for r in cont.list_light():
        print(r['id'], r['kind'], r['name'], r['pid'], r['fid'])

    # Full list with object counts
    for r in cont.list_submaps():
        print(r['id'], r['name'], r['points'],
              r['polylines'], r['polygons'])

    # Find a specific map
    img = cont.find("38000035")
    if img:
        print(img.summary())

    # Container stats
    print(cont.n_nt_skipped)        # NT maps skipped
    print(cont.n_service_skipped)   # service subfiles skipped

## Batch export

### From the command line

    python extract_all_maps.py gmapsupp.img output_folder

Creates one folder per map (named from the MPS table), each with three
shapefiles — points, lines, polygons (a layer is skipped if it has no
objects). Example:

    output_folder/
      Balaganskoe/
        points.shp   (+ .shx, .dbf, .prj, .cpg)
        lines.shp    (+ .shx, .dbf, .prj, .cpg)
        polygons.shp (+ .shx, .dbf, .prj, .cpg)
      Drugoe/
        points.shp
        lines.shp

### From Python, with per-type split

    cont = open_img("gmapsupp.img")
    cont.extract_all_by_name("extracted", level=0, by_types=True)

`by_types=True` (default) — per-type files inside each folder:
`points_1400.shp`, `lines_06.shp`, `polygons_50.shp`.
`by_types=False` — three common files: `points.shp`, `lines.shp`,
`polygons.shp`.

A `.done` marker is written into each folder when it finishes; on
restart, completed folders are skipped.

## Command-line interface

| Command | What it does |
|---|---|
| `python garmin_img.py info file.img` | map summary |
| `python garmin_img.py list gmapsupp.img` | list maps in a container |
| `python garmin_img.py export file.img out_prefix` | export a single map to MP/GeoJSON/SHP |
| `python garmin_img.py extract gmapsupp.img out_dir` | export all container lines |
| `python garmin_img.py extract-by-name gmapsupp.img out_dir [level]` | batch export by map name |

Example:

    python garmin_img.py extract-by-name gmapsupp.img extracted 0

## Limitations

- **NT format is not supported** (City Navigator, modern Topo)
- No routing graph (NET/NOD) — flags are read, but the graph is not built
- No elevation (DEM subfile)
- Read-only — no IMG writing
- Binary TYP files are not parsed (only text sources via `load_types_from_file`)
- Extended RGN sections (types 0x100+) are not implemented

## Garmin grid and MP format

Coordinates in IMG files are always on the Garmin grid. Each zoom level
has its own step:

    step = 360 / 2^bits_per_coord

For 24 bits the step is 0.0000214577° (~2.4 m at the equator). All
object coordinates in IMG are multiples of that step.

When exporting to MP the library writes coordinates rounded to 5 decimal
places by default, which is coarser than the Garmin grid. With
`snap_to_grid=True` coordinates are rounded to the exact Garmin grid,
so GPSMapEdit won't shift them on load.

Other formats (Shapefile / GeoJSON / GPX / CSV) keep full float64
precision and don't lose the grid.

## Dependencies

- **Required:** none
- **Optional:** `pyshp` — only for Shapefile export

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

This library would not exist without the work of:

- **John Mechalas** — "Garmin's IMG File Format" (2005)
- **N. Willink** — "Exploring Garmin's IMG Format" (2015)
- **Patrick Valsecchi** — JGarminImgParser (Java library)
- **Konstantin Galichsky** — GPSMapEdit
- The **imgdecode** project

## Feedback

If you find a map that doesn't parse correctly, or want to contribute — 
open an Issue or submit a Pull Request. Especially interested in:

- NT maps (for possible future support)
- BlueChart marine maps
- Topographic maps with DEM
- Maps with extended types (0x100+)
- Any map that produces wrong coordinates or empty labels