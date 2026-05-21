# Data Schema & Dataflow

## Overview

The external processing pipeline writes one `{glider}_web.json` file per glider
mission into `data/sync/`. These JSON files remain the source of truth. The web
app does not read the large JSON files directly during normal operation.

`data-watcher` converts each source JSON file into one compressed per-glider
NetCDF4 file under `data/netcdf/`. It also writes one aggregate tracks-only
NetCDF, `data/netcdf/tracks.nc`, that duplicates track data from all converted
gliders for fast map loading:

```text
data/sync/2511020901_web.json
        |
        | data-watcher polls for mtime changes
        v
data/netcdf/2511020901.nc
data/netcdf/tracks.nc
data/netcdf/manifest.json
        |
        v
GliderDataLoader reads NetCDF slices on demand
```

The per-glider NetCDF remains the complete cache for that glider, including its
own `/track` group. `tracks.nc` intentionally duplicates only map-facing track
arrays and instrument metadata. The manifest is written last and atomically, so
the app only sees completed NetCDF files.

## NetCDF Layout

Each `data/netcdf/{glider}.nc` file uses schema version
`gliderapp-netcdf-v1`.

Global attributes:

```text
schema_version
source_file
source_mtime
source_size
created
mission
glider_version
```

Dimensions:

```text
dive
pair = 2
ctd_sample
dox_sample
opt_sample
ph_sample
eng_sample
```

Track group:

```text
/track/time[dive, pair]
/track/lat[dive, pair]
/track/lon[dive, pair]
/track/u[dive]
/track/v[dive]
```

Instrument groups:

```text
/instruments/ctd/time[dive, ctd_sample]
/instruments/ctd/phase[dive, ctd_sample]
/instruments/ctd/p[dive, ctd_sample]
/instruments/ctd/depth[dive, ctd_sample]
/instruments/ctd/t[dive, ctd_sample]
...
```

The same pattern is used for `dox`, `opt`, and `ph`. Each instrument group has
an `info_json` attribute containing the display metadata from the source JSON.

The converter and loader also recognize an `adcp` instrument key (which would
use an `adcp_sample` dimension), reserved for depth-resolved current data. No
current source file contains an `adcp` block; the key is registered ahead of
time so that such data would convert and appear on the Profiles page with no
code change.

Engineering group:

```text
/eng/ndive[dive]
/eng/psurf[dive]
/eng/pmax[dive]
/eng/divetime[dive]
/eng/time[dive, eng_sample]
/eng/p[dive, eng_sample]
/eng/head[dive, eng_sample]
/eng/pitch[dive, eng_sample]
/eng/roll[dive, eng_sample]
```

## Aggregate Tracks NetCDF

`data/netcdf/tracks.nc` uses schema version `gliderapp-tracks-v1`. It is an
index/cache for map views, not the source of truth for profile or engineering
data. It contains active and archived gliders whenever their source
`*_web.json` file has been converted.

Global attributes:

```text
schema_version = gliderapp-tracks-v1
created
```

Layout:

```text
/tracks/{group}/time[dive, pair]
/tracks/{group}/lat[dive, pair]
/tracks/{group}/lon[dive, pair]
/tracks/{group}/u[dive]
/tracks/{group}/v[dive]
/tracks/{group}/instruments/ctd
/tracks/{group}/instruments/dox
/tracks/{group}/instruments/opt
/tracks/{group}/instruments/ph
```

Each `{group}` is a sanitized NetCDF group name derived from the glider or
mission id, for example `g_0013` or `g_2511020901`. Use the group attributes,
not the group name, as the stable identifier:

```text
glider_id       Manifest key / source id
mission         Source mission field
glider_version  Source glider generation
source_file     Source *_web.json filename
source_mtime    Source file mtime used for freshness checks
source_size     Source file size
store           Per-glider NetCDF filename containing the full data
```

The `time`, `lat`, `lon`, `u`, and `v` arrays are copied from the matching
per-glider `/track` group. Instrument child groups contain only the `info_json`
attribute copied from the per-glider instrument groups; sample arrays remain
only in the per-glider NetCDF files.

`manifest.json` records the aggregate file name and schema:

```text
tracks_store = tracks.nc
tracks_schema_version = gliderapp-tracks-v1
```

`data-watcher` rewrites `tracks.nc` when any per-glider NetCDF changes, when a
converted glider is added or removed, or when a stored `source_mtime` no longer
matches the manifest. Rewriting `tracks.nc` does not remove track data from the
per-glider NetCDF files.

## Ragged Profiles

Profiles are stored as padded 2D arrays. Each dive is one row; the sample
dimension is the maximum sample count for that instrument in that mission.
Shorter dives are padded with the NetCDF fill value (`NaN`). NetCDF4/HDF5
compression with shuffle is enabled for these arrays, so the padded side
compresses well.

This lets the app read a selected dive range directly:

```python
ctd_t[99:120, :]
ctd_p[99:120, :]
ctd_time[99:120, :]
```

The old JSON split format required loading and flattening the entire instrument
block before filtering by dive. The NetCDF layout applies the dive slice at disk
read time.

## Runtime Caching

`GliderDataLoader` loads active glider tracks at startup from `tracks.nc` when
it is present, falling back to per-glider NetCDF files if the aggregate file is
missing or unreadable. Archived mission tracks can also be read from `tracks.nc`
when selected, which supports a future archived map without opening every
per-glider store. Instrument and engineering profile data are still read from
the per-glider NetCDF files in chunks for the requested dive range or selected
dive; full instrument blocks are not kept in process memory.

The app uses `data/netcdf/manifest.json` mtime as the data version. When the
manifest changes, the per-worker loader singleton is rebuilt.

## Source `_web.json` Schema

The source files in `data/sync/` are named `{glider_or_mission}_web.json`.
They are JSON dictionaries with common top-level mission/track fields plus
optional sensor and engineering blocks.

Top-level fields:

```text
glider_version   string        "Spray" or "Spray2"
mission          string        Active serial number or archive mission id
time             list[dive][2] Unix seconds: [dive_start, dive_end]
lat              list[dive][2] Latitude at start/end of dive
lon              list[dive][2] Longitude at start/end of dive
u                list[dive]    Depth-averaged eastward velocity
v                list[dive]    Depth-averaged northward velocity
ctd              dict          CTD block, if present
opt              dict          Optical block, if present
dox              dict          Dissolved oxygen block, if present
ph               dict          pH block or metadata stub, if present
eng              dict          Engineering block, if present
```

The top-level `time`, `lat`, `lon`, `u`, and `v` arrays are the most stable
cross-generation fields. In particular, top-level `time[dive]` should be used
for dive start/end and duration calculations.

Sensor block pattern:

```text
sensor.info.<field>.name       Display name
sensor.info.<field>.unit       Display unit
sensor.<field>[dive][sample]   Per-dive sample arrays
sensor.ndive[dive][sample]     Usually repeated dive numbers, if present
sensor.phase[dive][sample]     1 = descent; other values are treated as ascent
```

Common sensor fields:

```text
ctd: time, phase, ndive, p, depth, t, c, s, theta, rho, sigma
opt: time, phase, ndive, p, depth, fl
dox: time, phase, ndive, p, depth, oxconc, ox, oxumolkg
ph:  time, phase, ndive, p, depth, Vrse, ph
```

Those lists are the full Spray-2 shape. Older Spray-1 files can be missing
some of these fields.

Engineering block pattern:

```text
eng.info.<field>.name      Display name
eng.info.<field>.unit      Display unit
eng.ndive[dive]            Dive number
eng.psurf[dive]            Surface pressure, if present
eng.pmax[dive]             Maximum pressure
eng.divetime[dive]         Not reliable across all source classes
eng.time[dive][sample]     Engineering sample time within dive
eng.p[dive][sample]        Engineering pressure
eng.head[dive][sample]     Heading
eng.pitch[dive][sample]    Pitch
eng.roll[dive][sample]     Roll
```

Do not use `eng.divetime` for app logic. It has different meanings depending
on source class, and its metadata can claim seconds even when the values are
minutes or timestamps. Use `(time[dive][1] - time[dive][0]) / 60` for duration
in minutes.

## Spray-1/Spray-2 and Active/Archive Differences

The app combines four source classes:

```text
Spray-1 active    active.csv       IDs like 0013
Spray-2 active    active2.csv      IDs like 0209
Spray-1 archive   archive.csv      mission IDs like 04900701 or 05C00701
Spray-2 archive   archive2.csv     mission IDs like 2511020901
```

Active and archive CSV rows share a leading layout, then differ:

```text
active*.csv   sn,  region, depth, active_flag, var1, var2, ...
archive*.csv  mid, region, depth,              var1, var2, ...
```

Columns read by the app:

- **sn / mid** — glider serial number or archive mission id.
- **region** — region key, resolved to a label via `config/map_config.yml`.
- **depth** — numeric; not read by the app.
- **active_flag** — active CSVs only. Only rows with flag `1` are shown as
  active gliders. Archive CSV rows have no active flag; they are a catalog of
  historical missions.
- **var1, var2, ...** — the variables this glider/mission carries, e.g.
  `theta`, `s`, `fl`, `oxconc`, `oxumolkg`, `ph`, `c`, `udop`, `vdop`, `abs`.
  This list builds the Section Details charts on the map pages: `map` and `TS`
  are shown first and always, then one chart per listed variable in CSV order.
  Editing these columns changes which plots appear.

`variables.csv` (rows of `key, display name, units`) supplies the chart headers
for those variables. A variable missing from `variables.csv` falls back to a
hardcoded name, then to the raw key.

Archive mission IDs encode date differently by generation:

```text
Spray-1 archive: YYMGGGGX    M is hexadecimal month 1-C
Spray-2 archive: YYMMGGGGXX  MM is decimal month 01-12
```

Spray-1 archive IDs can be damaged by spreadsheet round-trips when a leading
zero is stripped. The loader defensively pads 7-character alphanumeric Spray-1
archive IDs back to 8 characters.

Section files mirror the four classes:

```text
secsactive.csv     Spray-1 active
secsactive2.csv    Spray-2 active
secsarchive.csv    Spray-1 archive
secsarchive2.csv   Spray-2 archive, optional in current deployments
```

If a section file is missing or a mission has no section row, the app treats
the mission as a single section `(1, Inf)`.

Each section row is `id, start_dive, end_dive`; successive rows for the same id
define sections 1, 2, 3, ... Dives outside every range — in a gap between two
sections, or after the last section — inherit the preceding section's number
(forward-fill), so each section stays a single contiguous dive run and map
tracks are not drawn straight across the gap.

Subtle data differences observed in current source files:

- `glider_version` is `"Spray"` for Spray-1 and `"Spray2"` for Spray-2.
- Spray-1 instrument blocks may not include a per-sample `time` field. Current
  examples have `phase`, `ndive`, `p`, `depth`, and measured variables, but no
  sensor-local `time`.
- For Spray-1 profile samples without sensor-local `time`, the app cannot
  reconstruct per-sample `datetime` or `divetime` from the top-level dive
  start/end pair. Profile axes and color options for `datetime` and `divetime`
  should be disabled for those loaded ranges. A generated `sample` index can be
  used for sample-order plots when needed.
- Spray-2 instrument blocks include per-sample `time`, which allows datetime
  reconstruction from top-level dive start time plus relative sensor time.
- Spray-1 CTD examples lack conductivity `c`; Spray-2 CTD examples include it.
- Spray-1 pH may be only a metadata stub, for example `ph.info.p`, with no
  sample arrays. Spray-2 pH contains full `time`, `phase`, `p`, `depth`,
  `Vrse`, and `ph` arrays.
- `eng.psurf` is not guaranteed in every archive file. The app treats missing
  engineering summary fields as nullable.
- `eng.divetime` differs by source class in current examples:
  `Spray-1 active` uses seconds, `Spray-2 active` has values that behave like
  minutes despite metadata saying seconds, `Spray-1 archive` can contain a Unix
  timestamp-like marker, and `Spray-2 archive` uses seconds.

The NetCDF conversion preserves available fields rather than forcing all
source classes into a single science schema. The loader normalizes only the
fields needed by the app: track, sections, instrument metadata, selected
instrument samples, engineering summaries, and selected engineering dives.
