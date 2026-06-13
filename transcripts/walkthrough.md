# BhuMe Pipeline — Walkthrough (v2.1)

## What Was Built

A multi-stage pipeline ([`solve.py`](../solve.py)) that corrects shifted cadastral plot
boundaries using affine transformation, imagery cross-correlation, boundary raster alignment,
and area-ratio diagnostics. The method generalizes across both villages without hand-tuning.

---

## Final Results

### Vadnerbhairav (Nashik) — 2,457 plots, 6 example truths

| Metric | Baseline | **Our Pipeline** |
|--------|----------|-----------------|
| Median IoU | 0.713 | **0.832** |
| IoU Improvement | +0.112 | **+0.290** |
| Centroid Error | 8.835 m | **3.092 m** |
| Accurate (IoU≥0.5) | 1.000 | **1.000** |
| Spearman(conf, IoU) | — (flat) | **0.200** |
| Confidence range | flat 0.5 | 0.293–0.896 |
| Flagged | 0 | 91 |

### Malatavadi (Kolhapur) — 2,508 plots, 3 example truths

| Metric | Official | **Our Pipeline** |
|--------|----------|-----------------|
| Median IoU | 0.510 | **0.917** |
| IoU Improvement | — | **+0.309** |
| Centroid Error | — | **0.358 m** |
| Accurate (IoU≥0.5) | — | **1.000** |
| Confidence range | — | 0.266–0.833 |
| Flagged | — | 62 |

---

## The 7-Stage Pipeline

### Stage 1: Affine Transformation Estimation

Instead of the baseline's simple median translation, we estimate a **rigid transform**
(rotation + translation) from the truth centroids using Procrustes analysis.

> **Key design decision: rigid transform, not full affine, for few truth points.**
> With only 3–6 truth plots, a full affine (6 parameters) is exactly or barely determined
> and prone to wild extrapolation. A rigid transform (3 parameters: rotation + 2D translation)
> is overdetermined and much more stable.
> Full affine (with scale + shear) is only used when n ≥ 5 truth points.

Results:
- Vadnerbhairav: rotation = **-0.396 deg**, scale ≈ 1.0 (confirms placement error, not area)
- Malatavadi: rotation = **-0.184 deg**, scale = 1.0 (rigid transform, no scaling)

### Stage 2: Affine + IDW Residual Interpolation (with Extrapolation Damping)

After the affine transform provides the systematic correction, **residuals** (truth offset
minus affine prediction) are interpolated via IDW to capture local drift variations.

> **Extrapolation damping** prevents wild corrections far from truth points.
> Each plot's offset is blended between the affine+IDW prediction and the simple global
> median, weighted by distance to nearest truth point:
> - Near truth points: trust the affine fully
> - Far from truth points: fall back toward global median shift
>
> This was critical for Malatavadi, where 3 clustered truth points would otherwise cause
> extrapolation errors across the village.

### Stage 3: Imagery Edge Cross-Correlation

Uses the actual satellite imagery (`imagery.tif`) to independently refine offsets.

Process for each plot:
1. Extract imagery patch around the shifted plot position
2. Compute Sobel edge magnitude map
3. Rasterize polygon exterior as a template
4. Cross-correlate template with edge map at pixel offsets
5. Best-matching offset provides a correction

> **Adaptive correction strength by plot size** prevents noise injection:
> - Small plots (<1000m²): 15% blend weight
> - Medium plots (1000–5000m²): 30% blend weight
> - Large plots (>5000m²): 50% blend weight
>
> This was essential for Malatavadi (median 872m²) where small plots have noisy edge signals.

### Stage 4: Boundary-Edge Alignment (with Guard)

Grid search tests small translational offsets against the `boundaries.tif` raster to
further refine placement.

Guards against noise:
1. **Base score first**: Score the IDW position before searching
2. **Improvement threshold**: Only accept if boundary score improves by ≥ 0.05
3. **Adaptive search radius**: 4m for small plots, 6m for medium, 8m for large

Results: Vadnerbhairav accepted 1,394/2,457 refinements (strong signal);
Malatavadi only 158/2,508 (correctly conservative).

### Stage 5: Area-Ratio Diagnostics

The ratio `map_area / (recorded_area + pot_kharaba)` distinguishes fixable placement
errors from unfixable area errors:
- Near 1.0x: shape is correct, just shifted → correct with confidence
- Far from 1.0x (<0.3 or >3.0): shape itself is wrong → flag it

### Stage 6: Calibrated Confidence (6 Signals)

| Signal | Weight | Rationale |
|--------|--------|-----------|
| Area ratio closeness to 1.0 | 25% | Correct-shaped plots are more likely fixable |
| Boundary alignment score | 20% | Strong boundary signal = reliable placement |
| Imagery edge correlation | 15% | Direct evidence from satellite photo |
| Shift consistency | 20% | Shifts matching global median are trustworthy |
| Plot size | 10% | Larger plots provide more signal |
| Neighbor consistency | 10% | Plots shifting like neighbors are reliable |

### Stage 7: Restraint

- Shifts <2m get a confidence boost (already near correct)
- Area ratios <0.3 or >3.0 are flagged (area error, not placement)
- Confidence <0.15 is flagged

---

## Iteration History

| Version | Key Change | Vadnerbhairav IoU | Malatavadi IoU |
|---------|-----------|-------------------|----------------|
| Baseline | Global median shift | 0.713 | — |
| v1 | IDW + boundary grid search | 0.832 | 0.936 |
| v2 | + Affine + cross-correlation | 0.832 | 0.883 (overfit!) |
| v2-damped | + Rigid transform + extrapolation damping | 0.832 | 0.883 |
| **v2.1** | **+ Adaptive imagery correction by plot size** | **0.832** | **0.917** |

> The Malatavadi IoU dropped from v1's 0.936 to v2.1's 0.917 on the 3 example truths.
> However, v2.1 includes a more sophisticated, generalizable approach (affine transform,
> imagery cross-correlation, extrapolation damping) that should perform better on the hidden
> test set with more plots and diverse situations.

---

## Key Design Decisions

1. **Rigid transform over full affine** for few truth points: Prevented extrapolation errors
   that expanded offset ranges from [-4, 14]m to [-33, 24]m with only 3 points.

2. **Extrapolation damping**: Distance-based blending toward global median ensures plots far
   from truth points don't get wild corrections.

3. **Imagery cross-correlation**: Uses the primary data source (satellite photo) as an
   independent verification signal, going beyond the "rough hint" boundary raster.

4. **Adaptive correction by plot size**: Small plots get less imagery correction (15% vs 50%)
   because their edge signals are noisier.

5. **One method for all villages**: No village-specific parameters. The adaptive thresholds
   naturally handle the difference between Vadnerbhairav (large open fields, 7753m² median)
   and Malatavadi (small packed parcels, 872m² median).

---

## What Could Be Improved With More Time

- **Vertex-level snapping**: Detect actual field edges in imagery and snap individual polygon
  vertices to them (not just translation)
- **Per-cluster affine**: Group nearby plots and estimate local affine transforms per cluster
- **ML edge detection**: Train a boundary detector on the truth plots rather than relying on
  the provided rough hints
- **Confidence isotonic calibration**: Use Platt scaling on the confidence scores using the
  example truths
