# Claude Project Transcript

## 13 Jun

**User**: Identified task to generate two structured markdown files

**Claude**:
Generated the following files based on the project requirements:

### prompt.md

```markdown
# BhuMe Boundary Correction — Take-Home
Goal
For each land plot in a village, predict its true on-ground boundary and a calibrated confidence score. Flag plots you cannot place.

Inputs
data/<village_slug>/
  input.geojson       # official (shifted) plot polygons, EPSG:4326
  imagery.tif         # georeferenced satellite mosaic
  boundaries.tif      # optional auto-detected field edges
  example_truths.geojson  # handful of hand-aligned truths for self-scoring
Two villages available: Vadnerbhairav (Nashik) and Malatavadi (Kolhapur).

Outputs
data/<village_slug>/predictions.geojson — GeoJSON FeatureCollection, EPSG:4326.

Field	Type	Required
plot_number	string	yes — must match input exactly
status	"corrected" or "flagged"	yes
confidence	float 0–1	yes if corrected
method_note	string	optional
geometry	Polygon/MultiPolygon	yes — predicted or original
Requirements
Submit code that reproduces predictions.geojson from raw village data
Confidence must correlate with actual accuracy (calibrated, not flat)
Flag plots you cannot confidently place — do not force corrections
Do not move plots already in correct position
Coordinates: lon, lat order (GeoJSON/WGS84)
Deliverables
GitHub repo (public or private with BhuMe invited): code + predictions.geojson per village + /transcripts
5-minute screen-record walkthrough (unlisted link)
Google Form submission: repo URL, video link, résumé
Acceptance Criteria
Code runs end-to-end on raw village bundle
Valid GeoJSON FeatureCollection output
Confidence tracks accuracy (AUC > 0.5)
IoU improvement over official position for corrected plots
Restraint: control plots not moved
```

### instructions.md

```markdown
Instructions
Behavior
Solve a geospatial alignment problem: old cadastral map outlines are offset from real fields
Distinguish placement errors (fixable by shifting) from area errors (not fixable)
Use map_area_sqm / recorded_area_sqm ratio as signal: near 1.0 → likely placement error
Use recorded_area + pot_kharaba_ha as full expected area, not cultivable alone
Apply starter kit helpers: load, patch_for_plot, lonlat_to_pixel, pixel_to_lonlat, score, write_predictions
Beat global_median_shift baseline on both accuracy and calibration
Standards
Python 3.12, managed via uv sync
All geospatial work in EPSG:4326 (lon, lat); imagery in EPSG:3857 — use kit converters
Confidence must be meaningful: high confidence = high expected IoU
IoU threshold for a "hit": ≥ 0.5
Constraints
No hand-editing of output geometry
No overfitting to example_truths.geojson (handful of plots; real scoring uses hidden set)
Do not require API keys, GPU, or cloud services
Must process whole village at once (context from neighbors permitted)
Omitted plots = not attempted (no penalty, no credit)
Security
No credentials in repo
No PII — holder names are anonymised in input; keep them that way
Testing
Run uv run quickstart.py data/<village>/ to validate full pipeline
Validate output schema at hiring.bhume.in/test before submitting
Use score(preds, village) for directional accuracy + calibration feedback
Documentation
/transcripts/: all AI chat exports (CLI sessions as files; web chats as share links in transcripts/README.md)
AI use expected and required — document both understanding (web chats) and coding (CLI tools) usage
No written report required
Prohibitions
No hand-aligned geometry
No flat confidence values (all same score)
No skipping the video walkthrough
No private repo without granting BhuMe access
No missing plot_number match to input
```

**User**: generate the markdown files

**Claude**: Created 2 files, ran a command, read a file. Both files are ready to download.
- Prompt Document (`prompt.md`)
- Instructions Document (`instructions.md`)
