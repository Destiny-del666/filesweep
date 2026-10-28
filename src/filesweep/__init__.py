"""filesweep - 把一堆乱文件按扩展名、类型或日期自动归档。"""

__version__ = "0.1.0"

from .core import CATEGORIES, Move, Plan, apply_plan, build_plan, latest_log, undo_log

__all__ = [
    "CATEGORIES",
    "Move",
    "Plan",
    "apply_plan",
    "build_plan",
    "latest_log",
    "undo_log",
    "__version__",
]
