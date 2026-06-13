# BhuMe Boundary Correction — Take-Home

## Goal
For each land plot in a village, predict its true on-ground boundary and a calibrated confidence score. Flag plots you cannot place.

## Inputs
```
data/<village_slug>/
  input.geojson       # official (shifted) plot polygons, EPSG:4326
  imagery.tif         # georeferenced satellite mosaic
  boundaries.tif      # optional auto-detected field edges
  example_truths.geojson  # handful of hand-aligned truths for self-scoring
```

Two villages available: Vadnerbhairav (Nashik) and Malatavadi (Kolhapur).

## Outputs
`data/<village_slug>/predictions.geojson` — GeoJSON FeatureCollection, EPSG:4326.

| Field | Type | Required |
|---|---|---|
| `plot_number` | string | yes — must match input exactly |
| `status` | `"corrected"` or `"flagged"` | yes |
| `confidence` | float 0–1 | yes if corrected |
| `method_note` | string | optional |
| geometry | Polygon/MultiPolygon | yes — predicted or original |

## Requirements
- Submit code that reproduces `predictions.geojson` from raw village data
- Confidence must correlate with actual accuracy (calibrated, not flat)
- Flag plots you cannot confidently place — do not force corrections
- Do not move plots already in correct position
- Coordinates: lon, lat order (GeoJSON/WGS84)

## Deliverables
- GitHub repo (public or private with BhuMe invited): code + `predictions.geojson` per village + `/transcripts`
- 5-minute screen-record walkthrough (unlisted link)
- Google Form submission: repo URL, video link, résumé

## Acceptance Criteria
- Code runs end-to-end on raw village bundle
- Valid GeoJSON FeatureCollection output
- Confidence tracks accuracy (AUC > 0.5)
- IoU improvement over official position for corrected plots
- Restraint: control plots not moved
