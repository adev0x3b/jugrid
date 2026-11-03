# Methodology

JuGrid screens a region's power grid for climate hazards. It answers "which assets should we
look at first, today and in 2050?", not "will this line fail?".

## Assets

Every `power=substation`, `power=plant`, `power=line`, `power=minor_line` and `power=cable`
OpenStreetMap has inside the region (`area["ISO3166-2"=…]`), fetched from the Overpass API.

- Substations and plants become points: the node itself, the centroid of a mapped outline, or
  the middle of a relation's bounding box.
- Lines and cables stay lines. Their length is the great-circle length of the way.
- Voltage is the highest value of the `voltage` tag, in kV.

A new ingest updates assets in place and removes those OpenStreetMap no longer has. An empty
answer is refused, so a broken query cannot empty the map.

## Climate

Daily data from [NASA NEX-GDDP-CMIP6](https://registry.opendata.aws/nex-gddp-cmip6/): CMIP6
models bias-corrected against observations and downscaled to 0.25° (about 25 km). JuGrid
uses one model, EC-Earth3 (`JUGRID_CLIMATE_MODEL`), and three periods of the same length:

| Scenario | Experiment | Years (default) |
|---|---|---|
| Today | historical | 1995–2014 |
| 2050, middle road | SSP2-4.5 | 2041–2060 |
| 2050, high emissions | SSP5-8.5 | 2041–2060 |

"Today" is the model's own historical run, not observations, so the change to 2050 compares
like with like.

Each file holds one variable for one year for the whole globe, chunked one day at a time, so a
region needs the whole file. The ingest downloads it, cuts the region's cells out, writes them
to the Zarr store (`daily/<scenario>/<variable>/<year>`) and deletes the file. A year is marked
complete only once written, so an interrupted ingest resumes where it stopped.

## Indicators

Computed per cell with xarray, as the mean over the period of a yearly value:

| Hazard | Indicator | Variables | Why it matters to a grid |
|---|---|---|---|
| Extreme heat | Days above 35 °C | `tasmax` | Lines sag and lose capacity; transformers derate |
| Heavy rain | Wettest day (Rx1day), mm | `pr` | Flash floods, landslides under towers, flooded cabins |
| Wind | Windiest day, daily mean m/s | `sfcWind` | Conductor galloping, falling trees |
| Wet snow | Days with ≥ 10 mm at −1…2 °C | `tas`, `pr` | Snow sleeves that break conductors |

Daily mean wind understates gusts; the wind indicator ranks places against each other rather
than predicting gust speeds.

## River flood

Water depth of the 1-in-100-year river flood from the Copernicus Emergency Management Service
global flood hazard maps (GloFAS v2, about 90 m). A point reads its pixel; a line is sampled
about every pixel and keeps its deepest water and the kilometres that run through wet pixels.
The maps have no climate projection, so flood reads the same in every scenario.

## Scores

Each indicator becomes a 0–1 score, linear between a "no risk" and a "full risk" mark:

| Hazard | 0 at | 1 at |
|---|---|---|
| Extreme heat | 0 days | 20 days |
| Heavy rain | 40 mm | 120 mm |
| Wind | 5 m/s | 12 m/s |
| Wet snow | 1 day | 12 days |
| River flood | 0 m | 1.5 m |

That score is then weighted by how much the hazard hurts the kind of asset:

| Asset | Heat | Heavy rain | Wind | Wet snow | Flood |
|---|---|---|---|---|---|
| Power line | 0.7 | 0.3 | 1.0 | 1.0 | 0.3 |
| Distribution line | 0.6 | 0.4 | 1.0 | 1.0 | 0.4 |
| Underground cable | 0.5 | 0.5 | 0.0 | 0.0 | 0.7 |
| Substation | 0.7 | 0.6 | 0.3 | 0.4 | 1.0 |
| Power plant | 0.6 | 0.5 | 0.5 | 0.4 | 0.9 |

A point reads its cell; a line reads every cell it crosses and keeps the worst value. An
asset's overall score is its highest hazard score: an asset fails on its weakest point.
Scores are shown out of 100 and banded as low (< 25), medium (< 50), high (< 75) and very high.

The marks and weights live in `backend/src/jugrid/risk/hazards.py`; the API serves them at
`/api/meta` and the app's "About the data" shows them.

## Limits

- One climate model. A model ensemble would give a range instead of a value.
- 25 km cells: a valley and the ridge above it can share one.
- No asset age, condition, design standard or redundancy: exposure, not vulnerability of a
  specific asset.
- OpenStreetMap's coverage of distribution lines and cables varies from place to place.
