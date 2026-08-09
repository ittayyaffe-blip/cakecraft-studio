# Forecast Model Comparison — Ensemble Models & Modern Boosters

**Purpose:** the evidence backing the production forecasting model's selection, in a form suitable for presenting directly (methodology + results), with the raw machine-readable numbers behind it.

**Raw evidence:** [`docs/evaluation/forecast_model_comparison.json`](forecast_model_comparison.json) — the complete, unedited output of the run below (dataset stats, per-model configuration, every metric, environment versions, timestamp). This document is a narrative reading of that file; the JSON is the source of truth if the two ever disagree.

**How to reproduce:** `pip install -r tools/requirements-eval.txt` into the project's existing venv, then run `tools/evaluate_forecast_models.py` (unmodified — the same script that produced the numbers below). Requires `SUPABASE_URL`/`SUPABASE_KEY` for the same `orders` table the production app reads.

---

## Methodology

**Dataset.** One row per order from the live, seeded `orders` table (`created_at`, `total_price`, `status`, `pickup_date`), fetched in full — paginated past PostgREST's 1,000-row default response cap so the comparison genuinely covers the entire history, not an arbitrary subset.

**Daily-series construction.** Orders are aggregated into one row per **calendar day** (order count + revenue, zero-filled for days with no orders — no day is skipped). From that daily series, 16 features are engineered per day:
- **Calendar:** day of week, month, is-weekend
- **Trend:** a simple day-index capturing overall growth over time
- **Known-in-advance signal:** count of orders already confirmed for that date (a real "already on the books" fact, not a leak — confirmations happen ahead of pickup)
- **Lags:** order count and revenue from 1, 7, and 14 days prior
- **Rolling windows:** 7-day mean/std and 28-day mean of both order count and revenue

Each day's target is the *next* day's order count / revenue — i.e. every row predicts one day ahead, matching exactly what the production forecaster does.

**Train/test split.** **Time-based, 80/20** — the most recent 20% of days are held out as the test set; nothing is randomly shuffled, which would leak future information into training for a time series.

**Metrics.** **MAE** (Mean Absolute Error) and **RMSE** (Root Mean Squared Error) — the two metrics actually used to select the production model. **MAPE** (Mean Absolute Percentage Error) is reported as a supplementary sanity check only, computed over the subset of test days with nonzero actual orders (MAPE is undefined/explosive on zero-actual days, a real, common case for this dataset) — it did not factor into model selection.

---

## Dataset snapshot this comparison was run against

| | |
|---|---|
| Raw orders retrieved | **2,628** |
| Daily series | **1,094 calendar days**, 2023-08-10 → 2026-08-07 |
| Usable rows after lag/rolling warm-up | 1,066 |
| Train / test split | 852 / 214 days |
| Evaluated | 2026-08-09T10:43:59 UTC |
| Environment | Python 3.13.9 · scikit-learn 1.9.0 · xgboost 3.4.0 · lightgbm 4.7.0 · catboost 1.2.10 |

This is the **current, full production dataset** — the same 2,628 orders the live Backoffice dashboard reports.

---

## Results

**A note on the labels below:** *Rank* is a plain ordinal position by measured MAE/RMSE on this one test split — an objective fact from the numbers, not an interpretation. Any word like "closest competitor" or "clear margin" is a **presentation-oriented qualitative reading of the measured gap**, not a formal statistical significance claim — no significance test was run, and with 214 test days a few tenths of a unit could plausibly be noise. Treat the percentages as the real finding; the words are just how to talk about them out loud.

### Order Volume (predicted orders, next day)

| Rank | Model | MAE | RMSE | MAPE* | vs. best (MAE / RMSE) |
|---|---|--:|--:|--:|---|
| 1 | **Random Forest** | **1.46** | **2.17** | 46.0% | — (best on both) |
| 2 | CatBoost | 1.50 | 2.23 | 45.5% | +2.2% / +2.8% |
| 3 | XGBoost | 1.52 | 2.27 | 46.9% | +3.8% / +4.8% |
| 4 | LightGBM | 1.58 | 2.35 | 48.4% | +7.9% / +8.6% |

**Random Forest wins outright** — best MAE *and* best RMSE, ahead of every alternative including the modern boosting libraries, by a margin that widens from ~2% (vs. CatBoost) to ~9% (vs. LightGBM).

### Revenue (predicted revenue, next day)

| Rank | Model | MAE | RMSE | MAPE* | vs. best (MAE / RMSE) |
|---|---|--:|--:|--:|---|
| 1 | **CatBoost** | **237.26** | **345.82** | 64.0% | — (best on both) |
| 2 | Random Forest | 244.85 | 354.91 | 73.1% | +3.2% / +2.6% |
| 3 | LightGBM | 261.56 | 398.57 | 68.2% | +10.2% / +15.3% |
| 4 | XGBoost | 264.74 | 400.71 | 65.6% | +11.6% / +15.9% |

**CatBoost wins this target.** Random Forest is a clear second place — meaningfully ahead of LightGBM and XGBoost (10–16% worse than CatBoost), but genuinely behind CatBoost by **3.2% MAE / 2.6% RMSE**, not a tie.

*\*MAPE computed over nonzero-actual test days only; supplementary, not a selection criterion.*

---

## Production selection: Random Forest

**Random Forest remains the production model.** The reasoning, checked directly against the numbers above rather than assumed:

1. **Wins the primary target outright.** Order volume is what drives every downstream figure the system actually surfaces — `predictedOrders`, the workload bucket, the staffing recommendation in the AI Daily Briefing and AI Operations Agent. Random Forest is the best model here on both required metrics, not a close call.
2. **Competitive, not disqualifying, on the secondary target.** On revenue, Random Forest is 2nd of 4 — genuinely behind CatBoost (3.2% MAE / 2.6% RMSE), but clearly ahead of the other two candidates. A real, measured gap, honestly reported — not "within 1.5%" as an earlier version of this comparison stated (see note below).
3. **Zero new production dependency.** Random Forest's library (`scikit-learn`) is already required in production for the RAG module's TF-IDF retrieval — deploying it adds nothing to the dependency surface. XGBoost, LightGBM, and CatBoost are not installed in production and remain evaluation-only.
4. **Native, principled uncertainty quantification.** The spread across the forest's individual trees' predictions is what the Explainable AI confidence score is actually computed from (`forecast_service._confidence_from_trees`) — a natural byproduct of Random Forest's bagging design that the gradient-boosting alternatives don't provide the same way.
5. **Explainability and deployment simplicity** — one model family in production, retrained fresh on every request, no versioning/staleness to manage.

**On balance:** the strongest single-target result plus three structural advantages (dependency weight, native confidence quantification, simplicity) outweigh a real but modest second-place gap on the secondary target. XGBoost, LightGBM, and CatBoost remain documented, evaluated alternatives — not deployed.

**Correction to a previous version of this analysis:** `docs/BUSINESS_INTELLIGENCE_LAYER.md` previously stated Random Forest "stays within 1.5% of the best revenue result." That number was measured against a smaller, pre-dataset-scale-up snapshot (committed 2026-08-06, before the demo dataset was expanded to ~2,500+ orders on 2026-08-09) and is no longer accurate. Against the current, full 2,628-order production dataset, the actual gap is **3.2% MAE / 2.6% RMSE** — real and worth stating precisely, not rounded down. It does not change the selection (see above), but the earlier figure should not be cited going forward.
