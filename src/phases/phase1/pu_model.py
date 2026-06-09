"""
Phase 1 — Positive-Unlabeled (PU) Learning: target scoring.

Strategy: Bagging-PU (Mordelet & Vert, 2014).
  - Bootstrap R subsets of the unlabeled set (size = n_positives each).
  - Train one LightGBM on (positives=1, bootstrap_subset=0) per bag.
  - Final P(target) = mean probability across R bags.

This avoids the spy-technique heuristic and works well with 5–15 positives
on moderately-sized feature matrices (< 50k genes × 600 features).

Evaluation: leave-one-positive-out AUROC (each positive held out once;
P(target) compared against all unlabeled genes).

SHAP: LightGBM's built-in pred_contrib gives exact tree-SHAP values without
requiring the shap library — so there is no numba/llvmlite dependency here.
"""
from __future__ import annotations
import logging
import warnings
from typing import Dict, List, Optional, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_DEFAULT_N_BAGS = 30
_DEFAULT_LGB_PARAMS: Dict = {
    "objective": "binary",
    "metric": "auc",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 15,        # shallower trees — 16 features, ~5 positives
    "min_child_samples": 3,  # allow splits with few samples
    "subsample": 0.8,
    "colsample_bytree": 0.8, # use 80% of 16 features per tree (~13 features)
    "reg_alpha": 0.5,        # stronger L1 for sparse biological signals
    "reg_lambda": 2.0,       # stronger L2
    "verbose": -1,
    "n_jobs": -1,
}


def run_pu_learning(
    matrix: pd.DataFrame,
    known_positives: List[str],
    *,
    n_bags: int = _DEFAULT_N_BAGS,
    lgb_params: Optional[Dict] = None,
    random_state: int = 42,
) -> pd.DataFrame:
    """
    Score every gene in `matrix` with a PU probability.

    Returns (result_df, shap_map):
      result_df: columns [symbol, pu_probability, pu_percentile, is_positive],
                 sorted descending by pu_probability; scalar metrics in .attrs.
      shap_map:  {str(matrix_row_index): [{"feature", "value"}, ...]} for every gene.
    """
    params = {**_DEFAULT_LGB_PARAMS, **(lgb_params or {})}
    rng = np.random.default_rng(random_state)

    pos_mask = matrix.index.isin(known_positives)
    n_pos = pos_mask.sum()
    if n_pos == 0:
        raise ValueError("No known_positives found in matrix index. Check gene symbols.")
    if n_pos < 3:
        log.warning("[PU] Only %d positives found — model reliability will be low. "
                    "Aim for ≥5.", n_pos)

    X = matrix.values.astype(np.float32)
    pos_idx = np.where(pos_mask)[0]
    unl_idx = np.where(~pos_mask)[0]
    log.info("[PU] %d positives, %d unlabeled, %d bags", n_pos, len(unl_idx), n_bags)

    # ── Bagging-PU ────────────────────────────────────────────────────────────
    bag_probs = np.zeros((len(matrix), n_bags), dtype=np.float32)
    bag_size = max(n_pos, 10)   # undersample unlabeled to n_pos per bag

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")
        for b in range(n_bags):
            neg_sample = rng.choice(unl_idx, size=min(bag_size, len(unl_idx)), replace=False)
            tr_idx = np.concatenate([pos_idx, neg_sample])
            y = np.concatenate([
                np.ones(len(pos_idx), dtype=np.float32),
                np.zeros(len(neg_sample), dtype=np.float32),
            ])
            model = lgb.LGBMClassifier(**params, random_state=int(rng.integers(0, 2**31)))
            model.fit(X[tr_idx], y)
            bag_probs[:, b] = model.predict_proba(X)[:, 1]

    mean_prob = bag_probs.mean(axis=1)

    # ── Leave-one-positive-out AUROC ──────────────────────────────────────────
    auroc = _loo_auroc(X, pos_idx, unl_idx, params, rng, n_bags // 3)
    log.info("[PU] Leave-one-positive-out AUROC: %.3f", auroc)

    # ── SHAP attributions on the full ensemble (top genes) ────────────────────
    # Train one final model on all positives vs a balanced unlabeled sample.
    final_neg = rng.choice(unl_idx, size=min(len(unl_idx), n_pos * 10), replace=False)
    final_idx = np.concatenate([pos_idx, final_neg])
    final_y = np.concatenate([np.ones(len(pos_idx)), np.zeros(len(final_neg))])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")
        final_model = lgb.LGBMClassifier(**params, random_state=random_state)
        final_model.fit(X[final_idx], final_y)
        shap_vals = _get_shap(final_model, X, matrix.columns.tolist())

    # ── Assemble result ───────────────────────────────────────────────────────
    percentiles = _to_percentile(mean_prob)
    result = pd.DataFrame({
        "symbol": matrix.index,
        "pu_probability": mean_prob.astype(np.float32),
        "pu_percentile": percentiles.astype(np.float32),
        "is_positive": pos_mask,
    }).sort_values("pu_probability", ascending=False).reset_index(drop=True)
    result.attrs["auroc_loo"] = float(auroc)
    result.attrs["n_positives"] = int(n_pos)
    result.attrs["n_bags"] = n_bags
    # IMPORTANT: shap_vals is returned SEPARATELY, never stored on result.attrs.
    # pandas deep-copies a frame's .attrs onto every Series produced by
    # iterrows()/boolean-indexing/.head(); a ~20k-key SHAP map there makes
    # downstream ranking O(n^2) and hangs for minutes. Keep .attrs scalar-only.
    return result, shap_vals


# ── Helpers ───────────────────────────────────────────────────────────────────

def _loo_auroc(X, pos_idx, unl_idx, params, rng, n_bags_per_fold):
    """Estimate AUROC by leaving one positive out at a time."""
    from sklearn.metrics import roc_auc_score
    scores = []
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")
        for hold in pos_idx:
            train_pos = pos_idx[pos_idx != hold]
            if len(train_pos) == 0:
                continue
            bag_size = max(len(train_pos), 10)
            fold_probs = np.zeros(len(X))
            for _ in range(max(1, n_bags_per_fold)):
                neg_s = rng.choice(unl_idx, size=min(bag_size, len(unl_idx)), replace=False)
                tr = np.concatenate([train_pos, neg_s])
                y = np.concatenate([np.ones(len(train_pos)), np.zeros(len(neg_s))])
                m = lgb.LGBMClassifier(**params, random_state=int(rng.integers(0, 2**31)))
                m.fit(X[tr], y)
                fold_probs += m.predict_proba(X)[:, 1]
            fold_probs /= max(1, n_bags_per_fold)
            eval_idx = np.concatenate([[hold], unl_idx])
            eval_y = np.concatenate([[1], np.zeros(len(unl_idx))])
            try:
                auc = roc_auc_score(eval_y, fold_probs[eval_idx])
                scores.append(auc)
            except Exception:
                pass
    return float(np.mean(scores)) if scores else float("nan")


def _get_shap(model: lgb.LGBMClassifier, X: np.ndarray, feature_names: List[str]) -> Dict:
    """
    Return per-gene SHAP contributions using LightGBM's pred_contrib.
    All 16 features are individually interpretable — return top-8 by |value|.
    pred_contrib shape: (n_samples, n_features + 1); last col is bias.
    """
    try:
        contribs = model.booster_.predict(X, pred_contrib=True)
        contribs = contribs[:, :-1].astype(np.float32)
        top_k = min(8, len(feature_names))
        top_idx = np.argsort(np.abs(contribs), axis=1)[:, -top_k:][:, ::-1]
        shap_map: Dict[str, list] = {}
        for i, row_idx in enumerate(top_idx):
            shap_map[str(i)] = [
                {"feature": feature_names[fi], "value": round(float(contribs[i, fi]), 6)}
                for fi in row_idx
            ]
        return shap_map
    except Exception as exc:
        log.warning("[PU] SHAP extraction failed: %s", exc)
        return {}


def _to_percentile(arr: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata
    ranks = rankdata(arr, method="average")
    return (ranks / len(arr)).astype(np.float32)


def get_top_shap(
    shap_map: Dict,
    symbol: str,
    matrix_index: pd.Index,
) -> List[Dict]:
    """Retrieve pre-computed SHAP contributions for one gene from the shap map."""
    try:
        row_pos = matrix_index.get_loc(symbol)
        return shap_map.get(str(row_pos), [])
    except KeyError:
        return []
