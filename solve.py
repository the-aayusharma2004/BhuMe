#!/usr/bin/env python3
"""
BhuMe Boundary Correction -- Multi-stage pipeline (v2 -- improved).

Stages:
  1. Affine transformation estimation from example truths
  2. Affine + IDW residual interpolation for per-plot offsets
  3. Imagery edge cross-correlation refinement
  4. Boundary-edge alignment scoring (with guard)
  5. Area-ratio diagnostics
  6. Calibrated confidence scoring (multi-signal)
  7. Restraint (don't move already-correct plots)

Improvements over v1:
  - Affine transform captures rotation/scale, not just translation
  - Imagery cross-correlation uses actual satellite edges, not just boundary hints
  - Combined boundary + imagery signal for more robust confidence

Usage:
    uv run solve.py data/34855_vadnerbhairav_chandavad_nashik
    uv run solve.py data/12429_malatavadi_chandgad_kolhapur
"""

from __future__ import annotations

import sys
import statistics
import math
from pathlib import Path

import numpy as np
import geopandas as gpd
import pyproj
import rasterio
from rasterio.windows import from_bounds
from shapely.affinity import translate
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform
from scipy.spatial import cKDTree
from scipy.ndimage import sobel

from bhume import load, score, write_predictions
from bhume.geo import geom_to_imagery_crs, patch_for_plot, open_imagery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utm_for(geom: BaseGeometry) -> str:
    """Pick a UTM CRS for a geometry in EPSG:4326."""
    lon = geom.centroid.x
    return f'EPSG:{32600 + int((lon + 180) // 6) + 1}'


# ---------------------------------------------------------------------------
# Stage 1: Affine transformation from truth points
# ---------------------------------------------------------------------------

def _estimate_affine_from_truths(village, utm: str) -> tuple[np.ndarray, list[dict]]:
    """Estimate a best-fit affine transform from truth centroids.

    Returns:
        affine_matrix: 2x3 affine matrix [[a, b, tx], [c, d, ty]]
        offsets: per-truth offset dicts for IDW residuals
    """
    official_u = village.plots.to_crs(utm)
    truth_u = village.example_truths.to_crs(utm)

    src_pts = []  # official centroids
    dst_pts = []  # truth centroids
    offsets = []

    for pn in village.example_truths.index:
        if pn in official_u.index:
            o = official_u.loc[pn, 'geometry'].centroid
            t = truth_u.loc[pn, 'geometry'].centroid
            src_pts.append([o.x, o.y])
            dst_pts.append([t.x, t.y])
            offsets.append({
                'plot_number': pn,
                'x': o.x, 'y': o.y,
                'dx': t.x - o.x, 'dy': t.y - o.y,
            })

    if len(src_pts) < 2:
        # Fall back to simple translation
        mdx = statistics.median([o['dx'] for o in offsets]) if offsets else 0.0
        mdy = statistics.median([o['dy'] for o in offsets]) if offsets else 0.0
        affine = np.array([[1.0, 0.0, mdx],
                           [0.0, 1.0, mdy]])
        return affine, offsets

    src = np.array(src_pts)
    dst = np.array(dst_pts)
    n = len(src)

    # Center the points to improve numerical stability
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_c = src - src_mean
    dst_c = dst - dst_mean

    if n >= 5:
        # Full affine (6 params) -- only when overdetermined (n >= 5)
        # dst_x = a * src_x + b * src_y + tx
        # dst_y = c * src_x + d * src_y + ty
        A = np.zeros((2 * n, 6))
        b_vec = np.zeros(2 * n)
        for i in range(n):
            A[2*i, 0] = src[i, 0]
            A[2*i, 1] = src[i, 1]
            A[2*i, 2] = 1.0
            b_vec[2*i] = dst[i, 0]

            A[2*i+1, 3] = src[i, 0]
            A[2*i+1, 4] = src[i, 1]
            A[2*i+1, 5] = 1.0
            b_vec[2*i+1] = dst[i, 1]

        result, _, _, _ = np.linalg.lstsq(A, b_vec, rcond=None)
        affine = np.array([[result[0], result[1], result[2]],
                           [result[3], result[4], result[5]]])
    else:
        # 2-4 points: rigid transform (rotation + translation, 3 params)
        # Procrustes -- much more stable than full affine with few points
        H = src_c.T @ dst_c
        U, S, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T

        if np.linalg.det(R) < 0:
            Vt[-1, :] *= -1
            R = Vt.T @ U.T

        t_vec = dst_mean - R @ src_mean
        affine = np.array([[R[0, 0], R[0, 1], t_vec[0]],
                           [R[1, 0], R[1, 1], t_vec[1]]])

    return affine, offsets


def _apply_affine(affine: np.ndarray, x: float, y: float) -> tuple[float, float]:
    """Apply a 2x3 affine to a point, return (new_x, new_y)."""
    new_x = affine[0, 0] * x + affine[0, 1] * y + affine[0, 2]
    new_y = affine[1, 0] * x + affine[1, 1] * y + affine[1, 2]
    return new_x, new_y


def _affine_offset_at(affine: np.ndarray, x: float, y: float) -> tuple[float, float]:
    """Compute the (dx, dy) offset that the affine implies at point (x, y)."""
    new_x, new_y = _apply_affine(affine, x, y)
    return new_x - x, new_y - y


# ---------------------------------------------------------------------------
# Stage 2: IDW residual interpolation
# ---------------------------------------------------------------------------

def _idw_interpolate(
    known_points: np.ndarray,
    known_dx: np.ndarray,
    known_dy: np.ndarray,
    query_points: np.ndarray,
    power: float = 2.0,
    min_dist: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Inverse Distance Weighting interpolation of dx, dy residuals."""
    n_known = len(known_points)
    n_query = len(query_points)

    if n_known == 0:
        return np.zeros(n_query), np.zeros(n_query)
    if n_known == 1:
        return np.full(n_query, known_dx[0]), np.full(n_query, known_dy[0])

    tree = cKDTree(known_points)
    dists, indices = tree.query(query_points, k=n_known)

    if dists.ndim == 1:
        dists = dists.reshape(-1, 1)
        indices = indices.reshape(-1, 1)

    dists = np.maximum(dists, min_dist)
    weights = 1.0 / (dists ** power)
    weight_sum = weights.sum(axis=1, keepdims=True)
    weights_normed = weights / weight_sum

    interp_dx = (weights_normed * known_dx[indices]).sum(axis=1)
    interp_dy = (weights_normed * known_dy[indices]).sum(axis=1)

    return interp_dx, interp_dy


# ---------------------------------------------------------------------------
# Stage 3: Imagery edge cross-correlation
# ---------------------------------------------------------------------------

def _extract_edge_map(image_rgb: np.ndarray) -> np.ndarray:
    """Convert RGB image to edge magnitude map using Sobel filter."""
    # Convert to grayscale
    gray = np.mean(image_rgb.astype(np.float32), axis=2)
    # Sobel edge detection
    sx = sobel(gray, axis=1)
    sy = sobel(gray, axis=0)
    edges = np.sqrt(sx**2 + sy**2)
    return edges


def _rasterize_polygon_edges(
    geom_crs, transform, shape,
    n_samples: int = 200,
) -> np.ndarray:
    """Create a binary edge mask from polygon exterior in pixel coordinates."""
    mask = np.zeros(shape, dtype=np.float32)
    h, w = shape

    exterior = (
        geom_crs.exterior if hasattr(geom_crs, 'exterior')
        else (geom_crs.geoms[0].exterior if hasattr(geom_crs, 'geoms') else None)
    )
    if exterior is None:
        return mask

    inv_a = 1.0 / transform.a
    inv_e = 1.0 / transform.e
    c_val = transform.c
    f_val = transform.f
    step = exterior.length / n_samples if n_samples > 0 else 1.0

    for i in range(n_samples):
        pt = exterior.interpolate(i * step)
        col_i = int(round((pt.x - c_val) * inv_a))
        row_i = int(round((pt.y - f_val) * inv_e))
        if 0 <= row_i < h and 0 <= col_i < w:
            mask[row_i, col_i] = 1.0

    return mask


def _cross_correlate_offset(
    src_imagery,
    geom_4326: BaseGeometry,
    base_dx_utm: float,
    base_dy_utm: float,
    utm_crs: str,
    search_radius_px: int = 5,
) -> tuple[float, float, float]:
    """Use imagery edge cross-correlation to find the best sub-pixel offset.

    Works by:
    1. Extract imagery patch around the plot
    2. Compute edge map of imagery
    3. Rasterize polygon edges as a template
    4. Cross-correlate template with edge map at various offsets
    5. Return best offset correction and correlation score

    Returns (ddx_utm, ddy_utm, corr_score) -- the *correction* to add to base offset.
    """
    try:
        # Apply the base offset first
        tf_to_utm = pyproj.Transformer.from_crs('EPSG:4326', utm_crs, always_xy=True)
        tf_to_4326 = pyproj.Transformer.from_crs(utm_crs, 'EPSG:4326', always_xy=True)

        geom_utm = shp_transform(
            lambda xs, ys, z=None: tf_to_utm.transform(xs, ys), geom_4326
        )
        shifted_utm = translate(geom_utm, base_dx_utm, base_dy_utm)
        shifted_4326 = shp_transform(
            lambda xs, ys, z=None: tf_to_4326.transform(xs, ys), shifted_utm
        )

        # Get imagery patch around the shifted position
        patch = patch_for_plot(src_imagery, shifted_4326, pad_m=40.0)
        if patch.image.shape[0] < 10 or patch.image.shape[1] < 10:
            return 0.0, 0.0, 0.0

        # Edge map of imagery
        edge_map = _extract_edge_map(patch.image)

        # Rasterize the polygon edges in the patch coordinates
        geom_patch_crs = geom_to_imagery_crs(src_imagery, shifted_4326)
        template = _rasterize_polygon_edges(
            geom_patch_crs, patch.transform,
            (patch.image.shape[0], patch.image.shape[1]),
            n_samples=min(200, max(50, int(geom_patch_crs.length / 2)))
        )

        if template.sum() < 5:
            return 0.0, 0.0, 0.0

        # Normalize edge map
        e_std = edge_map.std()
        if e_std < 1e-6:
            return 0.0, 0.0, 0.0
        edge_norm = (edge_map - edge_map.mean()) / e_std

        # Test offsets in pixel space
        best_ddx, best_ddy = 0, 0
        best_corr = -1e9

        for ddy in range(-search_radius_px, search_radius_px + 1):
            for ddx in range(-search_radius_px, search_radius_px + 1):
                # Shift template
                shifted_template = np.roll(np.roll(template, ddy, axis=0), ddx, axis=1)
                # Correlation: sum of edge values where template has points
                mask_pts = shifted_template > 0
                if mask_pts.sum() < 5:
                    continue
                corr = edge_norm[mask_pts].mean()
                if corr > best_corr:
                    best_corr = corr
                    best_ddx = ddx
                    best_ddy = ddy

        # Convert pixel offset to metres
        # patch.transform.a = pixel width in CRS units (metres for EPSG:3857)
        ddx_m = best_ddx * abs(patch.transform.a)
        ddy_m = -best_ddy * abs(patch.transform.e)  # Row axis is inverted

        # Convert from imagery CRS (EPSG:3857) metres to UTM metres
        # These are approximate local metres, so they're roughly equivalent
        corr_score = max(0.0, min(1.0, (best_corr + 1.0) / 2.0))

        return ddx_m, ddy_m, corr_score

    except Exception:
        return 0.0, 0.0, 0.0


# ---------------------------------------------------------------------------
# Boundary alignment helpers
# ---------------------------------------------------------------------------

def _sample_boundary_along_exterior(
    boundary_data: np.ndarray,
    win_transform,
    exterior,
    n_samples: int = 100,
) -> float:
    """Sample boundary raster values along a polygon exterior. Returns mean value."""
    if exterior is None or boundary_data.size == 0:
        return 0.0

    d_min, d_max = float(boundary_data.min()), float(boundary_data.max())
    if d_max == d_min:
        return 0.5

    step = exterior.length / n_samples if n_samples > 0 else 1.0
    vals = []
    inv_a = 1.0 / win_transform.a
    inv_e = 1.0 / win_transform.e
    c = win_transform.c
    f = win_transform.f
    h, w = boundary_data.shape

    for i in range(n_samples):
        pt = exterior.interpolate(i * step)
        col_i = int(round((pt.x - c) * inv_a))
        row_i = int(round((pt.y - f) * inv_e))
        if 0 <= row_i < h and 0 <= col_i < w:
            vals.append(boundary_data[row_i, col_i])

    if not vals:
        return 0.0

    return float((np.mean(vals) - d_min) / (d_max - d_min))


def _boundary_alignment_score_fast(
    src_boundaries,
    geom_boundary_crs: BaseGeometry,
    pad_m: float = 5.0,
) -> float:
    """Score boundary alignment in the boundary raster's native CRS."""
    try:
        minx, miny, maxx, maxy = geom_boundary_crs.bounds
        left, bottom = minx - pad_m, miny - pad_m
        right, top = maxx + pad_m, maxy + pad_m

        dl, db, dr, dt = src_boundaries.bounds
        left, bottom = max(left, dl), max(bottom, db)
        right, top = min(right, dr), min(top, dt)

        if right <= left or top <= bottom:
            return 0.0

        window = from_bounds(left, bottom, right, top, transform=src_boundaries.transform)
        data = src_boundaries.read(1, window=window)
        if data.size == 0:
            return 0.0

        win_transform = src_boundaries.window_transform(window)
        exterior = (
            geom_boundary_crs.exterior if hasattr(geom_boundary_crs, 'exterior')
            else (geom_boundary_crs.geoms[0].exterior if hasattr(geom_boundary_crs, 'geoms') else None)
        )
        return _sample_boundary_along_exterior(data, win_transform, exterior, n_samples=80)

    except Exception:
        return 0.0


def _grid_search_offset_fast(
    src_boundaries,
    base_dx_utm: float,
    base_dy_utm: float,
    utm_to_boundary_tf,
    geom_utm: BaseGeometry,
    search_radius_m: float = 6.0,
    step_m: float = 2.0,
) -> tuple[float, float, float]:
    """Grid-search for best boundary-aligned offset."""
    best_dx, best_dy, best_score = base_dx_utm, base_dy_utm, -1.0

    offsets = np.arange(-search_radius_m, search_radius_m + step_m, step_m)
    for ddx in offsets:
        for ddy in offsets:
            test_dx = base_dx_utm + ddx
            test_dy = base_dy_utm + ddy
            shifted_utm = translate(geom_utm, test_dx, test_dy)
            shifted_bcrs = shp_transform(
                lambda xs, ys, z=None: utm_to_boundary_tf.transform(xs, ys),
                shifted_utm
            )
            s = _boundary_alignment_score_fast(src_boundaries, shifted_bcrs)
            if s > best_score:
                best_score = s
                best_dx = test_dx
                best_dy = test_dy

    return best_dx, best_dy, best_score


# ---------------------------------------------------------------------------
# Area ratio
# ---------------------------------------------------------------------------

def _compute_area_ratio(row) -> float | None:
    """Compute map_area / total_recorded_area. Near 1.0 = placement error."""
    map_area = row.get('map_area_sqm')
    recorded_area = row.get('recorded_area_sqm')
    pot_kharaba = row.get('pot_kharaba_ha')

    if map_area is None or map_area == 0:
        return None

    total_recorded = 0.0
    if recorded_area is not None and not (isinstance(recorded_area, float) and math.isnan(recorded_area)):
        total_recorded += recorded_area
    if pot_kharaba is not None and not (isinstance(pot_kharaba, float) and math.isnan(pot_kharaba)):
        total_recorded += pot_kharaba * 10000

    if total_recorded <= 0:
        return None

    return map_area / total_recorded


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def solve(village_dir: str) -> None:
    """Full pipeline: load -> affine -> IDW residuals -> imagery xcorr -> boundary -> score -> write."""
    village = load(village_dir)
    n_truth = 0 if village.example_truths is None else len(village.example_truths)
    print(f'Loaded {village.slug}')
    print(f'  {len(village.plots)} plots, {n_truth} example truths, '
          f'boundaries={"yes" if village.boundaries_path else "none"}')

    if village.example_truths is None:
        raise ValueError(f'{village.slug} has no example_truths.geojson')

    utm = _utm_for(village.example_truths.geometry.iloc[0])

    # =====================================================================
    # Stage 1: Affine transformation from truth points
    # =====================================================================
    print('\n-- Stage 1: Estimating affine transformation from truths...')
    affine, truth_offsets = _estimate_affine_from_truths(village, utm)

    # Report affine parameters
    scale_x = math.sqrt(affine[0, 0]**2 + affine[1, 0]**2)
    scale_y = math.sqrt(affine[0, 1]**2 + affine[1, 1]**2)
    rotation_rad = math.atan2(affine[1, 0], affine[0, 0])
    rotation_deg = math.degrees(rotation_rad)
    print(f'  Affine: scale=({scale_x:.6f}, {scale_y:.6f}), '
          f'rotation={rotation_deg:.3f} deg, '
          f'translation=({affine[0, 2]:.1f}, {affine[1, 2]:.1f})m')

    # Also compute simple global median for comparison
    mdx = statistics.median([o['dx'] for o in truth_offsets])
    mdy = statistics.median([o['dy'] for o in truth_offsets])
    print(f'  Global median shift: dx={mdx:.1f}m, dy={mdy:.1f}m')

    # =====================================================================
    # Stage 2: Affine + IDW residual interpolation (with extrapolation damping)
    # =====================================================================
    print('\n-- Stage 2: Computing affine offsets + IDW residuals...')

    # Get all plot centroids and geometries in UTM
    plots_utm = village.plots.to_crs(utm)
    all_centroids = np.array([
        [g.centroid.x, g.centroid.y] for g in plots_utm.geometry
    ])
    all_geoms_utm = list(plots_utm.geometry)

    # Compute affine-predicted offset for every plot
    affine_dx = np.zeros(len(all_centroids))
    affine_dy = np.zeros(len(all_centroids))
    for i, (cx, cy) in enumerate(all_centroids):
        adx, ady = _affine_offset_at(affine, cx, cy)
        affine_dx[i] = adx
        affine_dy[i] = ady

    # Compute residuals at truth points (truth offset - affine prediction)
    known_points = np.array([[o['x'], o['y']] for o in truth_offsets])
    known_dx = np.array([o['dx'] for o in truth_offsets])
    known_dy = np.array([o['dy'] for o in truth_offsets])

    residual_dx = np.zeros(len(known_dx))
    residual_dy = np.zeros(len(known_dy))
    for i, o in enumerate(truth_offsets):
        adx, ady = _affine_offset_at(affine, o['x'], o['y'])
        residual_dx[i] = o['dx'] - adx
        residual_dy[i] = o['dy'] - ady

    print(f'  Truth residuals after affine: dx=[{residual_dx.min():.2f}, {residual_dx.max():.2f}]m, '
          f'dy=[{residual_dy.min():.2f}, {residual_dy.max():.2f}]m')

    # Interpolate residuals via IDW
    interp_res_dx, interp_res_dy = _idw_interpolate(
        known_points, residual_dx, residual_dy, all_centroids, power=2.0
    )

    # Raw affine + residual offset
    raw_dx = affine_dx + interp_res_dx
    raw_dy = affine_dy + interp_res_dy

    # Extrapolation damping: blend affine prediction with global median
    # based on distance from nearest truth point. Plots near truths trust
    # the affine fully; distant plots fall back toward the global median.
    truth_tree = cKDTree(known_points)
    dists_to_truth, _ = truth_tree.query(all_centroids, k=1)

    # Characteristic distance: median inter-truth spacing or max truth extent
    if len(known_points) >= 2:
        truth_extent = np.max(np.ptp(known_points, axis=0))
    else:
        truth_extent = 1000.0
    damp_radius = max(truth_extent * 0.75, 500.0)

    # Blend weight: 1.0 = fully trust affine, 0.0 = fully trust global median
    blend_weight = np.clip(1.0 - (dists_to_truth / damp_radius), 0.0, 1.0)

    interp_dx = blend_weight * raw_dx + (1.0 - blend_weight) * mdx
    interp_dy = blend_weight * raw_dy + (1.0 - blend_weight) * mdy

    n_damped = (blend_weight < 0.99).sum()
    print(f'  Extrapolation damping: {n_damped}/{len(all_centroids)} plots blended toward global median')
    print(f'  Blend weight range: [{blend_weight.min():.3f}, {blend_weight.max():.3f}]')
    print(f'  Final offsets for {len(interp_dx)} plots')
    print(f'  dx range: [{interp_dx.min():.1f}, {interp_dx.max():.1f}]m')
    print(f'  dy range: [{interp_dy.min():.1f}, {interp_dy.max():.1f}]m')

    # =====================================================================
    # Stage 3: Imagery edge cross-correlation refinement
    # =====================================================================
    print('\n-- Stage 3: Imagery edge cross-correlation refinement...')
    imagery_scores = np.full(len(village.plots), 0.0)
    imagery_corrections_dx = np.zeros(len(village.plots))
    imagery_corrections_dy = np.zeros(len(village.plots))

    src_imagery = rasterio.open(village.imagery_path)
    n_imagery_refined = 0

    for i, (pn, row) in enumerate(village.plots.iterrows()):
        geom = row['geometry']
        try:
            ddx, ddy, corr_score = _cross_correlate_offset(
                src_imagery, geom,
                interp_dx[i], interp_dy[i],
                utm,
                search_radius_px=4,
            )
            imagery_corrections_dx[i] = ddx
            imagery_corrections_dy[i] = ddy
            imagery_scores[i] = corr_score
            if abs(ddx) > 0.1 or abs(ddy) > 0.1:
                n_imagery_refined += 1
        except Exception:
            pass

        if (i + 1) % 500 == 0:
            print(f'  Processed {i + 1}/{len(village.plots)} plots...')

    src_imagery.close()
    print(f'  Imagery cross-correlation refined {n_imagery_refined} plots')
    print(f'  Imagery score range: [{imagery_scores.min():.3f}, {imagery_scores.max():.3f}]')

    # Apply imagery corrections adaptively by plot size and score
    IMAGERY_THRESHOLD = 0.6
    n_imagery_applied = 0
    for i in range(len(village.plots)):
        if imagery_scores[i] > IMAGERY_THRESHOLD:
            # Adaptive blend weight based on plot area:
            # Small plots (<1000m2) have noisy edge signal -> 15% correction
            # Medium plots (1000-5000m2) -> 30% correction
            # Large plots (>5000m2) have clear edges -> 50% correction
            plot_area = all_geoms_utm[i].area
            if plot_area < 1000:
                blend = 0.15
            elif plot_area < 5000:
                blend = 0.30
            else:
                blend = 0.50
            interp_dx[i] += imagery_corrections_dx[i] * blend
            interp_dy[i] += imagery_corrections_dy[i] * blend
            n_imagery_applied += 1

    print(f'  Applied imagery corrections to {n_imagery_applied} plots (threshold={IMAGERY_THRESHOLD})')

    # =====================================================================
    # Stage 4: Boundary-edge alignment (with guard)
    # =====================================================================
    has_boundaries = village.boundaries_path is not None
    boundary_scores = np.full(len(village.plots), 0.5)
    refined_dx = interp_dx.copy()
    refined_dy = interp_dy.copy()

    if has_boundaries:
        print('\n-- Stage 4: Boundary-edge alignment refinement...')
        src_boundaries = rasterio.open(village.boundaries_path)
        boundary_crs = str(src_boundaries.crs)
        n_refined = 0
        n_accepted = 0
        MIN_IMPROVEMENT = 0.05

        utm_to_boundary_tf = pyproj.Transformer.from_crs(utm, boundary_crs, always_xy=True)

        for i in range(len(village.plots)):
            geom_utm = all_geoms_utm[i]
            try:
                # Score the base position first
                base_shifted_utm = translate(geom_utm, interp_dx[i], interp_dy[i])
                base_shifted_bcrs = shp_transform(
                    lambda xs, ys, z=None: utm_to_boundary_tf.transform(xs, ys),
                    base_shifted_utm
                )
                base_score = _boundary_alignment_score_fast(src_boundaries, base_shifted_bcrs)

                # Adaptive search radius
                plot_area = geom_utm.area
                if plot_area < 2000:
                    search_r, step = 4.0, 2.0
                elif plot_area < 10000:
                    search_r, step = 6.0, 2.0
                else:
                    search_r, step = 8.0, 2.0

                best_dx, best_dy, best_score = _grid_search_offset_fast(
                    src_boundaries,
                    interp_dx[i], interp_dy[i],
                    utm_to_boundary_tf,
                    geom_utm,
                    search_radius_m=search_r,
                    step_m=step,
                )
                n_refined += 1

                if best_score > base_score + MIN_IMPROVEMENT:
                    refined_dx[i] = best_dx
                    refined_dy[i] = best_dy
                    boundary_scores[i] = best_score
                    n_accepted += 1
                else:
                    boundary_scores[i] = base_score

            except Exception:
                boundary_scores[i] = 0.5

            if (i + 1) % 500 == 0:
                print(f'  Processed {i + 1}/{len(village.plots)} plots...')

        src_boundaries.close()
        print(f'  Refined {n_refined} plots, accepted {n_accepted} improvements')
        print(f'  Boundary score range: [{boundary_scores.min():.3f}, {boundary_scores.max():.3f}]')
    else:
        print('\n-- Stage 4: No boundaries.tif, skipping.')

    # =====================================================================
    # Stage 5: Area-ratio diagnostics
    # =====================================================================
    print('\n-- Stage 5: Computing area-ratio diagnostics...')
    area_ratios = []
    for _, row in village.plots.iterrows():
        ratio = _compute_area_ratio(row)
        area_ratios.append(ratio)
    area_ratios = np.array(area_ratios, dtype=float)

    valid_ratios = area_ratios[~np.isnan(area_ratios)]
    if len(valid_ratios) > 0:
        print(f'  Area ratio stats: median={np.median(valid_ratios):.3f}, '
              f'mean={np.mean(valid_ratios):.3f}, '
              f'std={np.std(valid_ratios):.3f}')
        print(f'  Plots with area data: {len(valid_ratios)}/{len(village.plots)}')

    # =====================================================================
    # Stage 6: Apply shifts and compute confidence
    # =====================================================================
    print('\n-- Stage 6: Applying shifts and computing confidence...')

    transformer_to_4326 = pyproj.Transformer.from_crs(utm, 'EPSG:4326', always_xy=True)

    results = []
    shift_magnitudes = np.sqrt(refined_dx**2 + refined_dy**2)
    global_shift_mag = math.sqrt(mdx**2 + mdy**2)

    centroid_tree = cKDTree(all_centroids)

    for i, (pn, row) in enumerate(village.plots.iterrows()):
        geom = row['geometry']
        dx_i = refined_dx[i]
        dy_i = refined_dy[i]
        shift_mag = shift_magnitudes[i]
        area_ratio = area_ratios[i]
        boundary_score = boundary_scores[i]
        imagery_score = imagery_scores[i]

        # Shift in UTM and transform back to 4326
        geom_utm = all_geoms_utm[i]
        shifted_utm = translate(geom_utm, dx_i, dy_i)
        shifted_4326 = shp_transform(
            lambda xs, ys, z=None: transformer_to_4326.transform(xs, ys),
            shifted_utm
        )

        # -- Confidence calculation (6 signals) --
        conf_signals = []

        # Signal 1: Area ratio closeness to 1.0 (weight: 0.25)
        if not np.isnan(area_ratio):
            ratio_closeness = max(0.0, 1.0 - abs(area_ratio - 1.0) * 1.5)
            conf_signals.append(0.25 * ratio_closeness)
        else:
            conf_signals.append(0.25 * 0.4)

        # Signal 2: Boundary alignment score (weight: 0.20)
        conf_signals.append(0.20 * boundary_score)

        # Signal 3: Imagery edge correlation (weight: 0.15) -- NEW
        conf_signals.append(0.15 * imagery_score)

        # Signal 4: Shift magnitude consistency (weight: 0.20)
        if global_shift_mag > 0:
            shift_ratio = shift_mag / global_shift_mag
            shift_consistency = max(0.0, 1.0 - abs(shift_ratio - 1.0) * 0.8)
        else:
            shift_consistency = 0.5
        conf_signals.append(0.20 * shift_consistency)

        # Signal 5: Plot size (weight: 0.10)
        plot_area_m2 = geom_utm.area
        size_score = min(1.0, plot_area_m2 / 5000.0)
        conf_signals.append(0.10 * size_score)

        # Signal 6: Neighbor consistency (weight: 0.10)
        neighbors = centroid_tree.query_ball_point(all_centroids[i], 500.0)
        neighbors = [n for n in neighbors if n != i]
        if len(neighbors) >= 2:
            med_dx = np.median(refined_dx[neighbors])
            med_dy = np.median(refined_dy[neighbors])
            deviation = math.sqrt((dx_i - med_dx)**2 + (dy_i - med_dy)**2)
            neighbor_cons = max(0.0, 1.0 - deviation / 50.0)
        else:
            neighbor_cons = 0.5
        conf_signals.append(0.10 * neighbor_cons)

        confidence = sum(conf_signals)
        confidence = max(0.01, min(0.99, confidence))

        # -- Flagging logic --
        should_flag = False
        flag_reason = ''

        if not np.isnan(area_ratio) and (area_ratio < 0.3 or area_ratio > 3.0):
            should_flag = True
            flag_reason = f'area_ratio={area_ratio:.2f} (likely area error)'

        if confidence < 0.15:
            should_flag = True
            flag_reason = f'very low confidence ({confidence:.2f})'

        # -- Stage 7: Restraint --
        if shift_mag < 2.0 and not should_flag:
            results.append({
                'plot_number': str(pn),
                'status': 'corrected',
                'confidence': min(0.99, confidence + 0.1),
                'method_note': f'near-zero shift ({shift_mag:.1f}m), kept near original',
                'geometry': shifted_4326,
            })
        elif should_flag:
            results.append({
                'plot_number': str(pn),
                'status': 'flagged',
                'confidence': confidence,
                'method_note': f'flagged: {flag_reason}',
                'geometry': geom,
            })
        else:
            results.append({
                'plot_number': str(pn),
                'status': 'corrected',
                'confidence': round(confidence, 3),
                'method_note': (
                    f'affine+IDW+xcorr shift dx={dx_i:.1f}m dy={dy_i:.1f}m, '
                    f'boundary={boundary_score:.2f}, imagery={imagery_score:.2f}, '
                    f'area_ratio={"N/A" if np.isnan(area_ratio) else f"{area_ratio:.2f}"}'
                ),
                'geometry': shifted_4326,
            })

    # -- Build predictions GeoDataFrame --
    preds = gpd.GeoDataFrame(results, crs='EPSG:4326')
    preds = preds.set_index('plot_number', drop=False)

    n_corrected = (preds['status'] == 'corrected').sum()
    n_flagged = (preds['status'] == 'flagged').sum()
    print(f'\n  Predictions: {n_corrected} corrected, {n_flagged} flagged')

    if n_corrected > 0:
        corrected_confs = preds.loc[preds['status'] == 'corrected', 'confidence']
        print(f'  Confidence stats: min={corrected_confs.min():.3f}, '
              f'median={corrected_confs.median():.3f}, '
              f'max={corrected_confs.max():.3f}, '
              f'std={corrected_confs.std():.3f}')

    # -- Write output --
    out_path = Path(village_dir) / 'predictions.geojson'
    write_predictions(out_path, preds)
    print(f'\n  Wrote {len(preds)} predictions -> {out_path}')

    # -- Score against example truths --
    print('\n-- Self-scoring against example truths:')
    print(score(preds, village))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: uv run solve.py data/<village_slug>')
        print('  e.g.: uv run solve.py data/34855_vadnerbhairav_chandavad_nashik')
        sys.exit(1)
    solve(sys.argv[1])
