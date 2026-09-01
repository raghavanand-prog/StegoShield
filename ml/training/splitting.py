"""Leak-safe train/validation/test splitting.

The critical rule for this dataset: a crop and every stego derivative
of that crop (and every other crop from the same source photograph)
must land entirely within ONE split. If they were split independently
at random, the model could effectively "recognize" a specific source
photo's texture/noise fingerprint from the training set and cheat on
the test set, inflating reported accuracy without learning anything
generalizable about steganography. We therefore split by the
`source_image` group using scikit-learn's GroupShuffleSplit.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit


@dataclass
class DatasetSplit:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame

    def summary(self) -> dict:
        def _stats(df: pd.DataFrame) -> dict:
            return {
                "samples": int(len(df)),
                "clean": int((df["label"] == 0).sum()),
                "stego": int((df["label"] == 1).sum()),
                "source_images": sorted(df["source_image"].unique().tolist()),
            }

        return {"train": _stats(self.train), "val": _stats(self.val), "test": _stats(self.test)}


def group_train_val_test_split(
    df: pd.DataFrame,
    test_size: float = 0.2,
    val_size: float = 0.2,
    seed: int = 42,
) -> DatasetSplit:
    """Split `df` into train/val/test with zero group overlap between any two splits."""
    groups = df["source_image"]

    gss_test = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_val_idx, test_idx = next(gss_test.split(df, groups=groups))
    train_val_df = df.iloc[train_val_idx]
    test_df = df.iloc[test_idx]

    # val_size is expressed relative to the full dataset; convert to a
    # fraction of the remaining train_val portion.
    relative_val_size = val_size / (1 - test_size)
    gss_val = GroupShuffleSplit(n_splits=1, test_size=relative_val_size, random_state=seed)
    train_idx, val_idx = next(gss_val.split(train_val_df, groups=train_val_df["source_image"]))
    train_df = train_val_df.iloc[train_idx]
    val_df = train_val_df.iloc[val_idx]

    # Defensive assertion: no group should ever appear in more than one split.
    train_groups = set(train_df["source_image"])
    val_groups = set(val_df["source_image"])
    test_groups = set(test_df["source_image"])
    assert not (train_groups & val_groups), "Data leakage: group overlap between train and val"
    assert not (train_groups & test_groups), "Data leakage: group overlap between train and test"
    assert not (val_groups & test_groups), "Data leakage: group overlap between val and test"

    return DatasetSplit(train=train_df.reset_index(drop=True),
                         val=val_df.reset_index(drop=True),
                         test=test_df.reset_index(drop=True))
