# ML / detection methods

**Honest status:** the detector now runs on real Sentinel imagery in real-data mode, but nothing here has been *validated* against ground truth (no labelled flood/damage extents are bundled). The rule-based detector is a standard, explainable SAR change-detection recipe; deep-learning detectors are interfaces only.

## Model registry
`GET /api/models`, `models/*.json`, `model_versions` table. Every detection stores `model_name` + `model_version`; every prediction stores its model/version. `accuracy` is `null` unless measured on registered ground truth - **never invented**.

| Model | Kind | Status |
|---|---|---|
| `disha-rule-based 1.0.0` (flood, wildfire, landslide, cyclone) | rule | active |
| `disha-random-forest 0.1.0` | ML | trainable (`RandomForestDetector.fit`), no weights bundled; unit-tested |
| `siamese-unet`, `changeformer` (adapter-0.1) | DL | **adapter only**: ONNX contract below; unavailable without `models/<file>.onnx` + `onnxruntime`; engine falls back to rule-based and records why |
| `disha-risk-propagation 0.1` | heuristic | active; hand-set coefficients, uncalibrated |
| `disha-photo-heuristics 0.1` | heuristic | active; colour/texture rules, **not a trained CV model** |

ONNX contract: inputs `pre`, `post` (1,C,H,W float32, per-channel standardised; channels = SAR dB, NDVI), output `change` (1,1,H,W) probability. Tiled inference at 256 px.

## Flood (primary module)
1. Speckle reduction: 5×5 boxcar in linear power domain.
2. Log-ratio `LR = post_dB − pre_dB` (negative = backscatter drop).
3. Adaptive thresholds: Otsu on `LR` (accepted only if separability ≥ 0.25 and within [−9, −2] dB, else −3 dB fallback) and on post backscatter (bounds [−20, −13] dB, fallback −15.5 dB). The method used is stored in `hazard_detections.stats`.
4. Masks: permanent water (dark pre-event), terrain (slope ≥ 5°), small blobs (< ~0.5 ha), SAR quality (shadow).
5. Optical (NDWI): on cloud-free pixels only, weighted by the sensor decision; agreement raises confidence, disagreement lowers it; optical-only additions are low-confidence.
6. Urban double-bounce rule: built-up pixels brightening > 2 dB → capped low-confidence flag (SAR under-detects flooded urban areas; stated in `stats.limitations`).
7. **Severity** = 0.6 × backscatter-drop index + 0.4 × DEM relative-depth proxy. It is an *inundation intensity index*, **not depth in metres**.
8. **Confidence** per pixel from distance past threshold relative to measured noise σ, neighbourhood agreement, slope, optical agreement.

## Other hazards (prototypes)
* **Wildfire**: dNBR (Otsu, bounds 0.10-0.45), VIIRS-style hotspots buffered ~375 m, SAR change support for cloud-covered pixels near confirmed burn. Outputs `fire_severity, burn_area_km2, hotspot_locations, confidence`.
* **Landslide**: logistic over dNDVI, slope and SAR change (bias compensation when optical is cloud-masked, confidence reduced); debris run-out as downslope halo. Outputs `landslide_probability, severity, confidence`.
* **Cyclone**: SAR change + dNDVI + built-up roof-change proxy + coastal low-lying surge rule. Outputs `damage_score, vegetation_damage, surge_indicator, confidence`.

## Uncertainty
`HIGH ≥ 0.80`, `MEDIUM ≥ 0.60`, `LOW ≥ 0.40`, else `INSUFFICIENT DATA`. Overall per-cell confidence fuses satellite, population, roads, weather, infrastructure (and field when present) weighted by quality × freshness; stale sources are penalised and missing sources lower the ceiling.

## Evaluation
`GET /api/events/{id}/evaluation`: for demonstration data returns *"Evaluation metrics unavailable for synthetic demonstration data."* For non-demo events a ground-truth GeoJSON can be registered (`POST`, needs `data.manage`) and accuracy, precision, recall, F1, IoU and false-positive rate are computed against the detection mask (`engines/evaluation.py`, unit-tested).
In development the simulator's truth mask was used only to sanity-check the detector (precision ≈ 0.97, recall ≈ 0.67-0.75 on the Kerala scene, limited by design: flooded built-up/forest and steep terrain are under-detected). **These numbers are not accuracy claims** - the scene and truth come from the same simulator.

## Real-data behaviour worth knowing
* The log-ratio threshold falls back to `-clip(3.5 x robust sigma, 2.5, 5) dB` when the histogram is not bimodal (typical for real scenes with little change), so thresholds follow the scene's own noise.
* Real Sentinel-1 RTC is multilooked in the linear domain to ~30 m before the 5x5 filter; flooded built-up / flooded vegetation remain under-detected.
* A removed scenario illustrates a limit: for the 2024 Wayanad landslide the rule detected nothing at 30 m with the only same-track pass, so it is not offered.

## Learning loop
Field verdicts adjust severity/confidence/exposure reversibly and are exportable as labels (`GET …/field-reports/training-export`: model severity vs observed verdict, with `simulated` flag) for future active learning. No automatic retraining is implemented.

## Planned (not built)
Training Siamese U-Net / ChangeFormer on xBD, Sen1Floods11, LEVIR-CD, Landslide4Sense, CaBuAr; calibrating the prediction model against observed event progression; a trained photo model.
