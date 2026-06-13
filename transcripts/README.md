# AI Transcripts

This submission was developed with significant AI assistance. Below are the conversation records.

---

## Coding Assistant — Antigravity (Gemini)

**Tool:** Antigravity IDE (Gemini-powered AI coding assistant)

**What it was used for:**
- Understanding the assignment and data structure
- Designing and iterating on the 7-stage pipeline (`solve.py`)
- Debugging edge cases (rigid vs. affine transform, extrapolation damping, boundary guard)
- Performance analysis and calibration improvements
- Setting up the GitHub repo and preparing this submission

**Conversation summary:**

| Stage | Key decisions made |
|-------|--------------------|
| Data loading & exploration | Identified both village bundles, confirmed `boundaries.tif` present, understood `Village` dataclass |
| Stage 1 (Affine) | Chose rigid Procrustes transform for ≤4 truth points after full affine caused [-33, 24]m extrapolation on Malatavadi |
| Stage 2 (IDW) | Added extrapolation damping: distance-based blend toward global median for plots far from truth points |
| Stage 3 (Imagery xcorr) | Added Sobel edge cross-correlation; adaptive strength by plot area (15%/30%/50%) |
| Stage 4 (Boundary) | Added guard: only accept grid-search refinement if improvement ≥0.05 |
| Stage 5–6 (Confidence) | 6-signal weighted confidence: area_ratio, boundary_score, imagery_score, shift_consistency, plot_size, neighbor_consistency |
| Calibration analysis | Spearman 0.200 on Vadnerbhairav (6 truths); AUC undefined because all 6 truths corrected to IoU≥0.5 |

**Final scores on example truths:**

- **Vadnerbhairav:** Median IoU 0.832 (vs. baseline 0.713), centroid error 3.092m
- **Malatavadi:** Median IoU 0.917 (vs. official 0.510), centroid error 0.358m

> The full conversation log is internal to the Antigravity IDE session.
> This README summarizes the key decisions and iterations made during development.

---

## Note on AI Transcript Export

The Antigravity IDE does not provide a direct "share link" or exportable transcript file.
This README documents the AI-assisted workflow in full detail, per the assignment guidance:
*"For web chats that only give a share link, list those links in transcripts/README.md."*

All code decisions, iteration history, and calibration analysis are captured in the
[`walkthrough.md`](../walkthrough.md) (if present) and in the inline comments of
[`solve.py`](../solve.py).
