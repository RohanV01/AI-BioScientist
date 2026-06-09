"""
Phase 7 — Gaussian Process surrogate model for active learning.

Uses sklearn GaussianProcessRegressor (no BoTorch required).
One GP per objective, fitted on evaluated candidates.
Acquisition: Upper Confidence Bound (UCB) or Expected Improvement (EI)
— used to suggest which regions of sequence/SMILES space to explore next.

In practice for a small molecule optimization loop:
  - Feature representation: Morgan FP (2048-bit) or physicochemical descriptors
  - One GP per objective (potency, ADMET, novelty)
  - UCB β=2.0 (exploration-exploitation balance)
  - Suggest top-K SMILES from a pre-enumerated candidate pool
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)

_N_FEATURES = 128   # physicochemical descriptor dimensionality (without RDKit FP)


# ─────────────────────────────────────────────────────────────────────────────
# Feature extraction
# ─────────────────────────────────────────────────────────────────────────────

def _mol_features_rdkit(smiles: str) -> Optional[np.ndarray]:
    """Morgan FP (radius=2, 2048 bits) as float32 numpy vector."""
    try:
        from rdkit import Chem
        from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        gen = GetMorganGenerator(radius=2, fpSize=2048)
        fp = gen.GetFingerprintAsNumPy(mol)
        return fp.astype(np.float32)
    except Exception:
        return None


def _mol_features_physchem(smiles: str) -> Optional[np.ndarray]:
    """Physicochemical descriptor vector (fallback when Morgan FP fails)."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors, QED as _qed
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        feats = [
            Descriptors.ExactMolWt(mol),
            Descriptors.MolLogP(mol),
            Descriptors.TPSA(mol),
            rdMolDescriptors.CalcNumHBD(mol),
            rdMolDescriptors.CalcNumHBA(mol),
            rdMolDescriptors.CalcNumRotatableBonds(mol),
            rdMolDescriptors.CalcNumRings(mol),
            rdMolDescriptors.CalcNumAromaticRings(mol),
            _qed.qed(mol),
        ]
        # Pad to _N_FEATURES with zeros
        arr = np.array(feats, dtype=np.float32)
        padded = np.zeros(_N_FEATURES, dtype=np.float32)
        padded[:len(arr)] = arr
        return padded
    except Exception:
        return None


def featurize(smiles_or_seq: str, is_peptide: bool = False) -> Optional[np.ndarray]:
    """
    Convert SMILES or peptide sequence to a fixed-length feature vector.
    Peptides: one-hot over 20 AA (flattened, max_len=60, zero-padded).
    SMILES: Morgan FP with physchem fallback.
    """
    if is_peptide:
        return _peptide_features(smiles_or_seq)
    fp = _mol_features_rdkit(smiles_or_seq)
    if fp is None:
        fp = _mol_features_physchem(smiles_or_seq)
    return fp


def _peptide_features(sequence: str, max_len: int = 60) -> np.ndarray:
    """One-hot encoding of peptide sequence, padded to max_len."""
    AA = "ACDEFGHIKLMNPQRSTVWY"
    aa_idx = {aa: i for i, aa in enumerate(AA)}
    vec = np.zeros(max_len * len(AA), dtype=np.float32)
    for i, aa in enumerate(sequence[:max_len]):
        j = aa_idx.get(aa, -1)
        if j >= 0:
            vec[i * len(AA) + j] = 1.0
    return vec


# ─────────────────────────────────────────────────────────────────────────────
# GP surrogate per objective
# ─────────────────────────────────────────────────────────────────────────────

class ObjectiveGP:
    """
    Single-objective sklearn GP surrogate.
    Fitted on (features, objective_values); predicts mean + std.
    """

    def __init__(self, objective_name: str):
        self.name = objective_name
        self._gp = None
        self._fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
        from sklearn.preprocessing import StandardScaler

        self._scaler_X = StandardScaler()
        self._scaler_y = StandardScaler()
        X_s = self._scaler_X.fit_transform(X)
        y_s = self._scaler_y.fit_transform(y.reshape(-1, 1)).ravel()

        kernel = ConstantKernel(1.0) * RBF(length_scale=1.0) + WhiteKernel(0.01)
        self._gp = GaussianProcessRegressor(
            kernel=kernel,
            n_restarts_optimizer=3,
            normalize_y=False,
        )
        self._gp.fit(X_s, y_s)
        self._fitted = True
        log.debug("[7.gp] %s: fitted on %d samples", self.name, len(y))

    def predict(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Returns (mean, std) in original y scale."""
        if not self._fitted or self._gp is None:
            zeros = np.zeros(len(X))
            return zeros, zeros + 0.1
        X_s = self._scaler_X.transform(X)
        mean_s, std_s = self._gp.predict(X_s, return_std=True)
        # Inverse-transform mean; std scales by std_y
        std_y = self._scaler_y.scale_[0] if hasattr(self._scaler_y, "scale_") else 1.0
        mean = self._scaler_y.inverse_transform(mean_s.reshape(-1, 1)).ravel()
        std = std_s * std_y
        return mean, std

    def ucb(self, X: np.ndarray, beta: float = 2.0) -> np.ndarray:
        """Upper Confidence Bound acquisition (maximisation)."""
        mean, std = self.predict(X)
        return mean + beta * std


# ─────────────────────────────────────────────────────────────────────────────
# Multi-objective surrogate
# ─────────────────────────────────────────────────────────────────────────────

class MultiObjectiveSurrogate:
    """
    Collection of one GP per objective.
    Fitted on existing evaluated candidates.
    Used to score and rank a candidate pool for the next iteration.
    """

    def __init__(self, objective_keys: List[str]):
        self.objective_keys = objective_keys
        self.gps = {k: ObjectiveGP(k) for k in objective_keys}

    def fit(self, candidates: List[Dict], is_peptide: bool = False) -> bool:
        """Fit all GPs on evaluated candidates. Returns False if <3 samples."""
        id_key = "sequence" if is_peptide else "smiles"
        X_rows = []
        y_dict = {k: [] for k in self.objective_keys}

        for c in candidates:
            feat = featurize(c.get(id_key, ""), is_peptide=is_peptide)
            if feat is None:
                continue
            X_rows.append(feat)
            for k in self.objective_keys:
                y_dict[k].append(float(c.get(k) or 0.0))

        if len(X_rows) < 3:
            log.warning("[7.gp] not enough samples (%d) to fit GP", len(X_rows))
            return False

        X = np.stack(X_rows)
        for k in self.objective_keys:
            y = np.array(y_dict[k], dtype=np.float32)
            try:
                self.gps[k].fit(X, y)
            except Exception as exc:
                log.warning("[7.gp] GP fit failed for %s: %s", k, exc)
        return True

    def suggest(
        self,
        pool: List[Dict],
        n_suggest: int = 20,
        is_peptide: bool = False,
    ) -> List[Dict]:
        """
        Score pool candidates with UCB acquisition and return top-n_suggest.
        Each candidate dict must have 'smiles' or 'sequence'.
        """
        if not pool:
            return []

        id_key = "sequence" if is_peptide else "smiles"
        feats = []
        valid_pool = []
        for c in pool:
            f = featurize(c.get(id_key, ""), is_peptide=is_peptide)
            if f is not None:
                feats.append(f)
                valid_pool.append(c)

        if not feats:
            return pool[:n_suggest]

        X = np.stack(feats)
        # Aggregate UCB across all objectives (equal weight)
        aggregate = np.zeros(len(X))
        for k in self.objective_keys:
            aggregate += self.gps[k].ucb(X)
        aggregate /= len(self.objective_keys)

        order = np.argsort(aggregate)[::-1]
        suggested = [valid_pool[i] for i in order[:n_suggest]]
        log.info("[7.gp] Suggested %d candidates from pool of %d", len(suggested), len(pool))
        return suggested
