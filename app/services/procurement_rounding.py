from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Literal


@dataclass(frozen=True)
class ProcurementRoundingPolicy:
    rounding_mode: Literal["CEIL", "NEAREST", "FLOOR"] = "CEIL"
    min_packs: int = 1
    pack_multiple: int = 1


def normalize_policy(policy: ProcurementRoundingPolicy | None) -> ProcurementRoundingPolicy:
    if policy is None:
        return ProcurementRoundingPolicy()
    rounding_mode = policy.rounding_mode if policy.rounding_mode in {"CEIL", "NEAREST", "FLOOR"} else "CEIL"
    min_packs = policy.min_packs if isinstance(policy.min_packs, int) and policy.min_packs >= 1 else 1
    pack_multiple = policy.pack_multiple if isinstance(policy.pack_multiple, int) and policy.pack_multiple >= 1 else 1
    return ProcurementRoundingPolicy(rounding_mode=rounding_mode, min_packs=min_packs, pack_multiple=pack_multiple)


def compute_packs_needed(required_qty: Decimal, pack_size: Decimal, policy: ProcurementRoundingPolicy) -> Decimal:
    if pack_size <= 0:
        raise ValueError("pack_size must be > 0")

    raw = required_qty / pack_size
    if policy.rounding_mode == "FLOOR":
        packs = int(raw.to_integral_value(rounding=ROUND_FLOOR))
    elif policy.rounding_mode == "NEAREST":
        packs = int(raw.to_integral_value(rounding=ROUND_HALF_UP))
    else:
        packs = int(raw.to_integral_value(rounding=ROUND_CEILING))

    packs = max(packs, policy.min_packs)
    multiple = policy.pack_multiple
    packs = ((packs + multiple - 1) // multiple) * multiple
    return Decimal(packs)
