# Garmin IMG Parser

A Python library for reading Garmin IMG files — the map format used by
Garmin GPS devices and BaseCamp/MapSource.

[Русская версия](README.ru.md)

## Features

- Read single `.img` files and `gmapsupp.img` containers with multiple maps
- Automatic XOR-decryption; skip NT-format maps gracefully
- Extract points, polylines, polygons with WGS84 coordinates and labels
- Full Garmin type dictionaries (~500 entries)
- Export to 5 formats: MP (Polish Format), GeoJSON, GPX, CSV, Shapefile
- Polygonize closed boundary lines into polygons
- Deduplicate objects across zoom levels
- Batch export all maps from a container into separate folders

## Installation

No required dependencies — just copy `garmin_img.py` into your project.

For Shapefile export, install `pyshp`:

    pip install pyshp

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

## What you can extract

For each object — points, polylines, polygons — you get:

    p.type          # 0x1500 (numeric type code)
    p.type_name     # "Minor country name" (from Garmin dictionary)
    p.label         # label text from the LBL subfile
    p.lat, p.lon    # WGS84 coordinates
    p.level         # zoom level

For polylines and polygons:

    pl.points       # [(lon, lat), (lon, lat), ...]
    pl.type_group   # "road", "water", "boundary", ...

## Batch export

    python extract_all_maps.py gmapsupp.img output_folder

Creates one folder per map (named from the MPS table) with shapefiles
split by object type — for example:

    output_folder/
      Balaganskoe/
        points_Major_country_name.shp
        points_State_province_region_name.shp
        lines_Residential_street.shp
        lines_Collector_road.shp

## Custom type names

You can register your own type names before opening a map:

    from garmin_img import register_line_type, register_point_type

    register_point_type(0x1E00, "Compartment number")
    register_line_type(0x06, "Compartment boundary", group="boundary")

Or load from a text file:

    from garmin_img import load_types_from_file
    load_types_from_file("my_types.txt")

## Limitations

- **NT format is not supported** (City Navigator, modern Topo)
- No routing graph (NET/NOD) — flags are read, but the graph is not built
- No elevation (DEM subfile)
- Read-only — no IMG writing
- Binary TYP files are not parsed (only text sources via `load_types_from_file`)
- Extended RGN sections (types 0x100+) are not implemented

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
