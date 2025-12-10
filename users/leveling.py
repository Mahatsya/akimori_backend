# Линейно-квадратичная прогрессия уровней
# XP_next(n) = round(100 * n^1.5), n >= 1
from bisect import bisect_right
from typing import List

MAX_LEVEL = 30
K = 100  # 100 * n^1.5

def xp_for_level(level: int) -> int:
    if level < 1:
        return 0
    return int(round(K * (level ** 1.5)))

# Предрасчёт таблиц
XP_NEXT_TABLE: List[int] = [0] * (MAX_LEVEL + 1)
TOTAL_XP_TABLE: List[int] = [0] * (MAX_LEVEL + 1)
for n in range(1, MAX_LEVEL + 1):
    XP_NEXT_TABLE[n] = xp_for_level(n)
    TOTAL_XP_TABLE[n] = TOTAL_XP_TABLE[n - 1] + XP_NEXT_TABLE[n]

def total_xp_for_level(level: int) -> int:
    if level <= 0:
        return 0
    if level >= MAX_LEVEL:
        return TOTAL_XP_TABLE[MAX_LEVEL]
    return TOTAL_XP_TABLE[level]

def level_for_xp(xp: int) -> int:
    if xp <= 0:
        return 0
    if xp >= TOTAL_XP_TABLE[MAX_LEVEL]:
        return MAX_LEVEL
    idx = bisect_right(TOTAL_XP_TABLE, int(xp))
    return max(0, min(MAX_LEVEL, idx - 1))

def next_level_requirement(xp: int) -> int:
    lvl = level_for_xp(xp)
    if lvl >= MAX_LEVEL:
        return 0
    return XP_NEXT_TABLE[lvl + 1]

def progress_to_next(xp: int) -> float:
    lvl = level_for_xp(xp)
    if lvl >= MAX_LEVEL:
        return 1.0
    base = TOTAL_XP_TABLE[lvl]
    need = XP_NEXT_TABLE[lvl + 1]
    done = max(0, int(xp) - base)
    if need <= 0:
        return 0.0
    return max(0.0, min(1.0, done / need))
