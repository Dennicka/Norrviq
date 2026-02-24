from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.settings import get_or_create_settings
from app.services.pricing import compute_pricing_scenarios
from app.services.offer_totals import OfferTotalsInput, compute_offer_totals

MONEY = Decimal("0.01")
LINE_ITEM_PUBLIC_KEYS = ("description", "qty", "unit", "unit_price", "total")


@dataclass
class OfferCommercial:
    mode: str
    segment: str
    units: dict
    rate: dict
    price_ex_vat: Decimal
    vat_amount: Decimal
    price_inc_vat: Decimal
    line_items: list[dict]
    warnings: list[str]
    math_breakdown: dict
    sections: list[dict]
    summary: dict
    metadata: dict


def _q(value: Decimal) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _basis_label(lang: str, basis: str) -> str:
    labels = {
        "sv": {
            "FLOOR_AREA": "golvyta",
            "CEILING_AREA": "takyta",
            "WALL_AREA": "väggyta",
            "PAINTABLE_TOTAL": "målningsbar yta",
        },
        "ru": {
            "FLOOR_AREA": "площадь пола",
            "CEILING_AREA": "площадь потолка",
            "WALL_AREA": "площадь стен",
            "PAINTABLE_TOTAL": "окрашиваемая площадь",
        },
    }
    return labels.get(lang, labels["sv"]).get(basis, basis)


def _internal_line_items(mode: str, selected, baseline, lang: str) -> list[dict]:
    if mode == "FIXED_TOTAL":
        return [{"source_ref": "generated:fixed", "description": "Fast pris för målning enligt överenskommelse" if lang == "sv" else "Фиксированная цена на малярные работы", "qty": Decimal("1.00"), "unit": "st", "unit_price": selected.price_ex_vat, "total": selected.price_ex_vat, "category": "painting", "split": "labour", "visible": True}]
    if mode == "PER_M2":
        return [{"source_ref": f"generated:m2:{baseline.m2_basis}", "description": f"Målning {_basis_label(lang, baseline.m2_basis)}", "qty": baseline.total_m2, "unit": "m²", "unit_price": _q(Decimal(str(selected.input_params.get('rate_per_m2') or 0))), "total": selected.price_ex_vat, "category": "painting", "split": "labour", "visible": True}]
    if mode == "PER_ROOM":
        return [{"source_ref": "generated:per_room", "description": "Målning per rum", "qty": Decimal(str(baseline.rooms_count)), "unit": "rum", "unit_price": _q(Decimal(str(selected.input_params.get('rate_per_room') or 0))), "total": selected.price_ex_vat, "category": "painting", "split": "labour", "visible": True}]
    if mode == "PIECEWORK":
        return [{"source_ref": "generated:piecework", "description": "Arbete enligt styckpris", "qty": Decimal(str(baseline.items_count)), "unit": "st", "unit_price": _q(Decimal(str(selected.input_params.get('rate_per_piece') or 0))), "total": selected.price_ex_vat, "category": "painting", "split": "labour", "visible": True}]
    return [{"source_ref": "generated:hourly", "description": "Arbete (löpande räkning)", "qty": baseline.labor_hours_total, "unit": "h", "unit_price": _q(Decimal(str(selected.input_params.get('hourly_rate') or 0))), "total": selected.price_ex_vat, "category": "painting", "split": "labour", "visible": True}]




def _public_line_item(item: dict) -> dict:
    return {key: item[key] for key in LINE_ITEM_PUBLIC_KEYS if key in item}


def _public_line_items(items: list[dict]) -> list[dict]:
    return [_public_line_item(item) for item in items]

def _project_marker(project: Project) -> str:
    pricing = project.pricing
    source = {
        "project_id": project.id,
        "work_items": len(project.work_items),
        "rooms": len(project.rooms),
        "mode": pricing.mode if pricing else None,
        "hourly": str(pricing.hourly_rate_override) if pricing else None,
        "fixed": str(pricing.fixed_total_price) if pricing else None,
        "m2": str(pricing.rate_per_m2) if pricing else None,
        "room": str(pricing.rate_per_room) if pricing else None,
        "piece": str(pricing.rate_per_piece) if pricing else None,
    }
    return hashlib.sha256(json.dumps(source, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _to_payload(offer: OfferCommercial) -> dict:
    def norm(v):
        if isinstance(v, Decimal):
            return str(_q(v))
        if isinstance(v, list):
            return [norm(x) for x in v]
        if isinstance(v, dict):
            return {k: norm(val) for k, val in v.items()}
        return v

    return norm({
        "mode": offer.mode,
        "segment": offer.segment,
        "units": offer.units,
        "rate": offer.rate,
        "price_ex_vat": offer.price_ex_vat,
        "vat_amount": offer.vat_amount,
        "price_inc_vat": offer.price_inc_vat,
        "line_items": _public_line_items(offer.line_items),
        "warnings": offer.warnings,
        "math_breakdown": offer.math_breakdown,
        "sections": [
            {**section, "lines": _public_line_items(section.get("lines", []))} for section in (offer.sections or [])
        ],
        "summary": offer.summary,
        "metadata": offer.metadata,
    })


def serialize_offer_commercial(offer: OfferCommercial) -> str:
    return json.dumps(_to_payload(offer), ensure_ascii=False, sort_keys=True)


def deserialize_offer_commercial(payload: str | None) -> dict | None:
    if not payload:
        return None
    return json.loads(payload)


def compute_offer_commercial(db: Session, project_id: int, *, lang: str = "sv") -> OfferCommercial:
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")
    baseline, scenarios = compute_pricing_scenarios(db, project_id)
    mode = (project.pricing.mode if project.pricing else "HOURLY").upper()
    selected = next((s for s in scenarios if s.mode == mode), scenarios[0])
    settings = get_or_create_settings(db)
    vat_pct = Decimal(str(settings.moms_percent if settings.moms_percent is not None else 25))
    vat_amount = _q(selected.price_ex_vat * vat_pct / Decimal("100"))
    price_inc_vat = _q(selected.price_ex_vat + vat_amount)
    internal_line_items = _internal_line_items(mode, selected, baseline, lang)
    line_items = _public_line_items(internal_line_items)
    totals = compute_offer_totals(
        OfferTotalsInput(
            labour_subtotal=selected.price_ex_vat,
            materials_subtotal=baseline.materials_cost_internal,
            other_subtotal=baseline.travel_setup_cost_internal,
            vat_percent=vat_pct,
            rot_enabled=bool(project.use_rot),
        )
    )
    sections = [{"id": "painting", "title": "", "order": 10, "lines": line_items}]
    if baseline.materials_cost_internal > 0:
        sections.append(
            {
                "id": "materials",
                "title": "Materials",
                "order": 50,
                "lines": [
                    {
                        "description": "Materials",
                        "qty": Decimal("1.00"),
                        "unit": "lot",
                        "unit_price": _q(baseline.materials_cost_internal),
                        "total": _q(baseline.materials_cost_internal),
                    }
                ],
            }
        )

    return OfferCommercial(
        mode=mode,
        segment=(project.client.client_segment if project.client and project.client.client_segment else "ANY"),
        units={"m2_basis": baseline.m2_basis, "total_m2": baseline.total_m2, "rooms_count": baseline.rooms_count, "items_count": baseline.items_count},
        rate={
            "hourly_rate": selected.input_params.get("hourly_rate"),
            "fixed_total": selected.input_params.get("fixed_total_price"),
            "rate_per_m2": selected.input_params.get("rate_per_m2"),
            "rate_per_room": selected.input_params.get("rate_per_room"),
            "rate_per_piece": selected.input_params.get("rate_per_piece"),
        },
        price_ex_vat=selected.price_ex_vat,
        vat_amount=vat_amount,
        price_inc_vat=price_inc_vat,
        line_items=line_items,
        warnings=list(selected.warnings),
        math_breakdown={
            "baseline_hours": str(baseline.labor_hours_total),
            "internal_total_cost": str(baseline.internal_total_cost),
            "buffers_hours_total": str(baseline.buffers_hours_total),
            "buffers_cost_total": str(baseline.buffers_cost_total),
            "speed_profile_code": baseline.speed_profile_code,
        },
        sections=sections,
        summary={
            "labour_subtotal": totals.labour_subtotal,
            "materials_subtotal": totals.materials_subtotal,
            "other_subtotal": totals.other_subtotal,
            "discount": totals.discount_amount,
            "subtotal_ex_vat": totals.subtotal_ex_vat,
            "vat_amount": totals.vat_amount,
            "total_inc_vat": totals.total_inc_vat,
            "rot_ready_base": totals.rot_base,
        },
        metadata={
            "rounding_policy": "SEK 0.01 HALF_UP: line components rounded before VAT and totals",
            "project_marker": _project_marker(project),
        },
    )


def is_offer_snapshot_stale(db: Session, project_id: int, snapshot_payload: dict | None) -> bool:
    if not snapshot_payload:
        return False
    marker = (((snapshot_payload or {}).get("metadata") or {}).get("project_marker"))
    if not marker:
        return False
    project = db.get(Project, project_id)
    if not project:
        return False
    return marker != _project_marker(project)


def assert_offer_matches_selected_scenario(db: Session, project_id: int, *, offer: OfferCommercial, tolerance: Decimal = Decimal("0.01")) -> None:
    _, scenarios = compute_pricing_scenarios(db, project_id)
    selected = next((s for s in scenarios if s.mode == offer.mode), None)
    if selected is None:
        raise ValueError("Offer totals mismatch pricing scenario")
    if abs(selected.price_ex_vat - offer.price_ex_vat) > tolerance:
        raise ValueError("Offer totals mismatch pricing scenario")
