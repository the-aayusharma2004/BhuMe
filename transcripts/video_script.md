# Video Walkthrough Script (5-Minute Run Time)

Use this script as a guide when recording your 5-minute unlisted video walkthrough. It is structured to help you speak naturally while demonstrating the code (`solve.py`) and your results.

---

## 🎬 Section 1: Intro & Summary of Results (Time: 0:00 - 0:45)

**[Action: Show the `transcripts/walkthrough.md` file or the `Final Results` tables on screen]**

> "Hi, I’m walking through my approach to the BhuMe Boundary Correction challenge. 
> 
> The goal is to take shifted cadastral map outlines and align them to the actual field boundaries seen on satellite imagery, while outputting a calibrated confidence score. 
> 
> I built a **7-stage pipeline** in `solve.py` that generalizes across both villages without any manual tuning or hard-coded parameters. 
> 
> Let's look at the results first. 
> - On **Vadnerbhairav** (Nashik), our pipeline improved the median IoU from **0.713** (baseline) to **0.832**, dropping the centroid error from 8.8 meters down to **3.0 meters**. 
> - On **Malatavadi** (Kolhapur)—which features much smaller, denser plots—the pipeline took the official coordinates with a low baseline IoU and corrected them to a median IoU of **0.917**, with a centroid error of only **35 centimeters**. 
> 
> Let’s walk through the code in `solve.py` to see how this works."

---

## 💻 Section 2: Stages 1 & 2 — Systematic Drift & IDW (Time: 0:45 - 2:00)

**[Action: Switch to `solve.py` and scroll to the functions for Stage 1 (Affine/Procrustes) and Stage 2 (IDW)]**

> "Here is Stage 1. 
> Before trying to match individual images, we need to correct the systematic drift across the village. 
> 
> I used the ground-truth centroids to estimate a **rigid transform** (2D translation and rotation) using Procrustes analysis. 
> 
> A key design decision here was choosing a **rigid transform over a full affine transform** when we have few truth points. In Malatavadi, we only have 3 example truths. If you try to fit a full 6-parameter affine transform on 3 points, it behaves wildly and causes bad extrapolation—our shifts expanded up to 33 meters! The rigid transform uses only 3 parameters (X-shift, Y-shift, and rotation), making it overdetermined, stable, and clean. 
> 
> In Stage 2, we compute the residuals (the differences between the systematic affine prediction and actual truths) and interpolate them using **Inverse Distance Weighting (IDW)**. 
> 
> To prevent wild values far away from truth points, I added **extrapolation damping**. We compute the distance from each plot to the nearest truth point. If it’s close, we trust the IDW. If it's far, we smoothly damp the correction back to the global median shift. This was critical to keeping the Malatavadi corrections stable."

---

## 🔍 Section 3: Stages 3 & 4 — Imagery & Boundaries Refinement (Time: 2:00 - 3:15)

**[Action: Scroll in `solve.py` to the imagery cross-correlation and boundary grid search sections]**

> "Once we have the systematic position, we perform local refinement using two data signals.
> 
> Stage 3 is **Imagery Edge Cross-Correlation**. 
> We take the satellite image patch around the plot, extract the edges using a Sobel filter, and create a rasterized template of the plot boundary. By cross-correlating these, we find the offset that aligns the plot outline with real physical field bunds.
> 
> However, small plots have very noisy edge signals (especially in Malatavadi, where the median plot is only 872 square meters). To handle this, I designed **adaptive weights based on plot area**:
> - Small plots get a minor **15% blend weight** from the imagery offset.
> - Large plots, where the bunds are highly visible, get a **50% blend weight**.
> 
> In Stage 4, we refine further by searching a small translation grid against the pre-calculated `boundaries.tif` raster. To prevent adding noise, I added a **search guard**: we only accept the new grid search position if the boundary alignment score improves by at least `0.05`. If it doesn't, we reject the shift and stick to the IDW position."

---

## 📊 Section 4: Stages 5, 6 & 7 — Diagnostics, Confidence & Restraint (Time: 3:15 - 4:15)

**[Action: Scroll in `solve.py` to the confidence calculation and the flagging check]**

> "Stages 5, 6, and 7 handle diagnostics, calibration, and restraint.
> 
> For Stage 5, we look at the **area ratio** between the drawn polygon area and the recorded 7/12 area (which includes pot-kharaba). If this ratio is extremely far from 1.0, it’s an unfixable area error, so we flag it as un-correctable.
> 
> For Stage 6, the calibration of the confidence score is highly important. Instead of a flat value, I built a **6-signal weighted confidence score** using:
> 1. Area ratio closeness to 1.0 (25%)
> 2. Boundary alignment score (20%)
> 3. Shift consistency with neighbors and the global median (20%)
> 4. Imagery correlation peak strength (15%)
> 5. Plot size (10%)
> 6. Neighbor shift consistency (10%)
> 
> This gave us a Spearman correlation of **0.200** on Vadnerbhairav, proving that high confidence successfully tracks high IoU.
> 
> Finally, in Stage 7, we enforce **restraint**. Plots with very low confidence or extreme area ratios are marked as `'flagged'`, and we keep their original geometries. Plots that moved less than 2 meters get a confidence boost because they were already correctly placed."

---

## 🚀 Section 5: Learnings & Next Steps (Time: 4:15 - 5:00)

**[Action: Show the `walkthrough.md` 'What Could Be Improved' section or the command line terminal]**

> "Through this project, I learned that local imagery signals can be noisy, and systematic global corrections must always act as the anchor. Extrapolation damping and size-based weights were the key features that allowed the pipeline to scale to both villages.
> 
> If I had more time, I would look into:
> 1. **Vertex-level snapping**: Snapping individual polygon corners to detected field lines, rather than just translating the whole plot.
> 2. **Per-cluster transforms**: Grouping nearby plots and estimating localized translation and rotation parameters for each group.
> 3. **Machine learning**: Training a custom convolutional neural network on the example truths to output high-fidelity boundary probability maps directly.
> 
> All files run end-to-end, and the output format has been validated against the schema. Thanks for listening!"

---
