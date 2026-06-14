# Claude AI Transcripts

This file contains the transcripts of the Claude sessions used for the BhuMe Boundary Correction project.

---

# Session 1: Planning, Understanding, and Architecture

**Tool:** Claude (claude.ai — Claude Sonnet 4.6)  
**Purpose:** Understanding the problem domain, reviewing the starter kit, and planning the solution approach  
**Date:** June 2026

## Session Overview

This transcript documents a Claude.ai web chat session focused on understanding the BhuMe engineering take-home assignment, reviewing all provided project files, and establishing a clear mental model of the task before writing code.

## Conversation

### Turn 1 — User

Shared the following project files for review and analysis:

- `BhuMe_Assignment_Document.md` — Full candidate preparation guide covering the problem background, glossary, technologies, data description, starter kit documentation, scoring rubric, and submission instructions.
- `CONTRACT.md` — The precise data and submission contract specifying input/output schemas.
- `quickstart.py` — End-to-end worked example: load → inspect → predict (naive baseline) → score → write output.
- `README.md` — Starter kit overview explaining what each helper does and why.
- `pyproject.toml` — Project dependencies (geopandas, rasterio, shapely, numpy, scipy, pillow).
- `uv.lock` — Locked dependency file for reproducible installs.

**Request:** Compile our entire conversation into a clean Markdown transcript for the `/transcripts` folder.

---

### Turn 2 — Claude

Acknowledged the request and noted an important limitation: only this current conversation session is directly accessible — prior Claude.ai chats in the project are not retrievable as full text from within a new session.

Produced this Markdown document capturing the current session and recommended adding share links for other Claude.ai chats to `transcripts/README.md` per the submission guidelines.

---

## Project Context (Reconstructed for Record)

The following summarises the problem as understood from the provided files, to make this transcript self-contained.

### The Core Problem

Maharashtra's cadastral (land parcel) maps were originally drawn by hand on paper at scales of 1:4,000–1:10,000, then scanned and georeferenced by MRSAC (Maharashtra Remote Sensing Application Centre) onto satellite imagery. Because the old drawings were never tied to GPS coordinates, the resulting digital outlines sit metres away from the actual fields they describe on the ground. This is called **drift**.

The assignment task: for each plot in a village, decide whether its official boundary can be corrected to sit on the real field visible in satellite imagery, produce a corrected geometry if so, and assign a confidence score to that correction.

### Two Kinds of Error (Key Distinction)

| Type | Meaning | Fixable? |
|------|---------|----------|
| **Placement error** | Shape is roughly right but sitting in the wrong location | ✅ Yes — translate/rotate/warp to match imagery |
| **Area error** | The drawn shape doesn't match the recorded area at all | ❌ No — geometry is wrong; moving it won't help |

A useful heuristic: `map_area_sqm / (recorded_area_sqm + pot_kharaba_ha × 10000)` close to 1.0 suggests a placement problem. Far from 1.0 suggests an area problem.

### Input Data (per village)

```
data/<village_slug>/
  input.geojson       # Official (shifted) plot outlines — what we transform
  imagery.tif         # Georeferenced satellite mosaic — primary signal
  boundaries.tif      # Pre-computed field-edge hints — rough, optional
  example_truths.geojson  # A handful of hand-aligned truths for self-scoring
```

Each feature in `input.geojson` (EPSG:4326, lon/lat) carries:
- `plot_number` — unique identifier (must be echoed exactly in output)
- `map_area_sqm` — area of the drawn polygon
- `recorded_area_sqm`, `recorded_area_ha` — cultivable 7/12 area
- `pot_kharaba_ha` — uncultivable area (add to recorded area for full extent)
- `surveys` — breakdown of survey numbers, hissa subdivisions, and per-holder areas

### Output Format (`predictions.geojson`)

One feature per plot you attempt (EPSG:4326):

```json
{
  "type": "Feature",
  "geometry": { "type": "Polygon", "coordinates": [...] },
  "properties": {
    "plot_number": "142",
    "status": "corrected",
    "confidence": 0.78,
    "method_note": "shifted onto field edge visible in imagery"
  }
}
```

`status` is either `"corrected"` (new geometry provided) or `"flagged"` (original geometry kept, not confident). Plots omitted entirely get no credit and no penalty.

### Scoring Dimensions

1. **Accuracy** — IoU (intersection-over-union) and centroid distance vs hidden hand-aligned truths. IoU ≥ 0.5 is a "hit".
2. **Confidence calibration** ★ — Does high confidence actually predict high accuracy? Scored as AUC (0.5 = random, 1.0 = perfect). This is the most heavily weighted metric.
3. **Restraint** — Avoid moving already-correct plots. Moving a correct plot counts against you.

The tiers are Bronze (runs, honest), Silver (improves on official), Gold (calibrated confidence), Platinum (generalises across villages).

### Starter Kit Helpers

| Helper | Purpose |
|--------|---------|
| `load(village)` | Open village folder, return plots + imagery + hints + truths as one object |
| `patch_for_plot(src, geom)` | Crop satellite imagery to a polygon with padding |
| `lonlat_to_pixel` / `pixel_to_lonlat` | Convert between EPSG:4326 and image pixel coordinates |
| `score(preds, village)` | Run accuracy + calibration + restraint metrics against example truths |
| `write_predictions(path, gdf)` | Write contract-valid `predictions.geojson` |
| `global_median_shift(village)` | Naive baseline: apply one median offset to all plots, flat confidence |

### Baseline Behaviour

`global_median_shift` computes a single (dx, dy) shift from the example truths and applies it uniformly. It helps plots that drifted coherently, misses rotations/local stretches/outliers, and uses flat confidence (so AUC → 0.5 — no calibration signal). Beating its IoU improvement AND producing meaningful confidence is the first real goal.

### Two Villages

| Village | District | Plots | Area | Median plot | Character |
|---------|----------|------:|-----:|------------:|-----------|
| Vadnerbhairav | Nashik | 2,457 | ~54 km² | 7,753 m² | Open farmland, large separated fields, drift easy to see — good for building intuition |
| Malatavadi | Kolhapur | 2,508 | ~5.8 km² | 872 m² | Dense, small plots near a town — boundary hints thin, confidence harder to earn |

### Setup Commands

```bash
# Install uv (once): https://docs.astral.sh/uv/getting-started/installation/
uv sync                        # installs Python 3.12 + all deps into .venv
uv run quickstart.py data/34855_vadnerbhairav_chandavad_nashik
```

---

## Key Insights from File Review

1. **The area ratio is a diagnostic, not a verdict.** `map_area / (recorded + pot_kharaba)` near 1.0 points to placement; far from 1.0 may indicate a split parcel, digitising error, or genuinely wrong shape. Always check imagery before concluding.

2. **Pot-kharaba matters for area comparisons.** `recorded_area_sqm` excludes uncultivable land. The full expected area is `recorded_area_sqm + pot_kharaba_ha × 10000`. Comparing only against `recorded_area_sqm` will mislead on plots with large uncultivable portions.

3. **Flat confidence is worthless.** The baseline explicitly sets identical confidence for every plot, scoring ~0.5 AUC. Real confidence should be derived from signal strength — how clearly the field edge appears, how well cross-correlation converges, how close the area ratio is to 1.0, etc.

4. **Flagging is correct behaviour.** When a plot can't be reliably placed (tree cover, no visible bund, conflicting area ratio), returning `status: "flagged"` is an honest answer that protects calibration score.

5. **Coordinate order matters.** GeoJSON uses **lon, lat** (longitude first). Mixing up with lat, lon silently shifts everything by a large amount.

6. **CRS mismatch is pre-handled.** Plots are EPSG:4326 (lon/lat degrees), imagery is EPSG:3857 (web-mercator, metres). The starter kit helpers (`patch_for_plot`, `lonlat_to_pixel`) handle conversion internally.

7. **Don't overfit to example truths.** There are only 6 (Vadnerbhairav) or 3 (Malatavadi) example truths. The real grade uses a larger hidden set. Design the method to generalise.

8. **Submit a method, not hand-edited results.** BhuMe runs the code and reads it alongside the video and transcripts. Hand-aligned geometry scores poorly even when IoU looks good.

---

## Planned Approach (for reference)

### Phase 1 — Understand the Baseline
- Run `quickstart.py` on Vadnerbhairav
- Inspect `patch_example.png` and the printed score
- Understand what `global_median_shift` does and where it fails

### Phase 2 — Better Correction
- For each plot, extract the satellite patch with padding
- Use the boundaries hint raster where available
- Attempt cross-correlation or edge-fitting to recover a local offset
- Fall back to the global shift where signal is absent
- Flag plots where the area ratio is far from 1.0 or signal is too weak

### Phase 3 — Confidence Calibration
- Assign confidence based on measurable signal quality:
  - Strength of cross-correlation peak
  - Closeness of area ratio to 1.0
  - Clarity of edge detection results
  - Whether boundaries.tif has strong signal under the plot
- Verify calibration on the example truths before finalising

### Phase 4 — Packaging
- Ensure `predictions.geojson` is valid GeoJSON FeatureCollection
- Run through the Test page at `hiring.bhume.in/test`
- Record 5-minute walkthrough video
- Collect all transcripts → `/transcripts/`

---

## Files Reviewed This Session

| File | Status |
|------|--------|
| `BhuMe_Assignment_Document.md` | ✅ Reviewed in full |
| `CONTRACT.md` | ✅ Reviewed in full |
| `quickstart.py` | ✅ Reviewed in full |
| `README.md` | ✅ Reviewed in full |
| `pyproject.toml` | ✅ Reviewed |
| `uv.lock` | ✅ Scanned (dependency versions noted) |

---

## Notes for Submission

- This file belongs in `/transcripts/transcript_claude_ai_session.md` (or consolidated in `ClaudeTranscripts.md`)
- For any other Claude.ai chats used during this project, add their share links to `transcripts/README.md`
- For Claude Code (CLI) sessions, run `/export` inside the session to save the log, then commit under `/transcripts/`
- The hiring team reads how AI was directed, not just whether it was used — include chats where the problem was understood, not only coding sessions

---

# Session 2: Prompt and Instructions File Generation

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

---

*End of transcript*
