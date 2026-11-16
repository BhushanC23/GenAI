"""Reusable application logic for KubeCoach."""

# On Windows, initialize hnswlib OpenMP runtime before sklearn imports to avoid DLL conflicts
try:
    import hnswlib
    import numpy as np

    _warmup_idx = hnswlib.Index(space="l2", dim=4)
    _warmup_idx.init_index(max_elements=1)
    _warmup_idx.add_items(np.zeros((1, 4), dtype=np.float32), [0])
    _warmup_idx.knn_query(np.zeros((1, 4), dtype=np.float32), k=1)
    del _warmup_idx
except Exception:
    pass

