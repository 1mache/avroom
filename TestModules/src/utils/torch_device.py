from __future__ import annotations


def auto_device() -> str:
    """Pick ``"cuda"`` when a GPU is available, else ``"cpu"``.

    ``torch`` is imported lazily so strategies that never run this path
    (e.g. under test without torch installed) don't pay the import cost.
    """
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ModuleNotFoundError:
        return "cpu"
