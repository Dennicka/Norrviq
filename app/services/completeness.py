from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.company_profile import CompanyProfile, get_or_create_company_profile
from app.models.completeness_rule import CompletenessRule
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.project import Project
from app.services.pricing import compute_project_baseline
from app.services.takeoff import get_or_create_project_takeoff_settings


@dataclass
class MissingCompletenessItem:
    check_key: str
    severity: str
    weight: int
    message: str
    hint_link: str | None


@dataclass
class CompletenessReport:
    score: int
    level: str
    missing: list[MissingCompletenessItem]
    can_issue_fixed_price: bool
    can_issue_mode: bool


def _level(score: int) -> str:
    if score < 50:
        return "LOW"
    if score < 80:
        return "MEDIUM"
    return "HIGH"


def _check_value(project: Project, baseline, company_profile: CompanyProfile, check_key: str) -> bool:
    if check_key == "HAS_WORK_ITEMS":
        return len(project.work_items) > 0
    if check_key == "HAS_LABOR_HOURS":
        return baseline.labor_hours_total > Decimal("0")
    if check_key == "HAS_ROOMS":
        return len(project.rooms) > 0
    if check_key == "HAS_TOTAL_M2":
        total_m2 = sum((Decimal(str(room.floor_area_m2 or 0)) for room in project.rooms), Decimal("0"))
        return total_m2 > Decimal("0")
    if check_key == "HAS_ROOM_WALL_HEIGHT":
        if not project.rooms:
            return False
        return all(Decimal(str(room.wall_height_m or 0)) > Decimal("0") for room in project.rooms)
    if check_key == "HAS_PERIMETER_AND_HEIGHT_FOR_WALL_AREA":
        if not project.rooms:
            return False
        return all((room.wall_perimeter_m is not None and Decimal(str(room.wall_perimeter_m or 0)) > 0 and room.wall_height_m is not None and Decimal(str(room.wall_height_m or 0)) > 0) for room in project.rooms)
    if check_key == "HAS_FLOOR_AREA_FOR_CEILING_OR_FLOOR":
        if not project.rooms:
            return False
        return all(Decimal(str(room.floor_area_m2 or 0)) > Decimal("0") for room in project.rooms)
    if check_key == "HAS_BUFFERS_ENABLED":
        cfg = project.buffer_settings
        return bool(cfg and cfg.include_risk and cfg.include_setup_cleanup_travel)
    if check_key == "HAS_SPEED_PROFILE_SET":
        profile = project.execution_profile
        return bool(profile and profile.speed_profile_id)
    if check_key == "HAS_COMPANY_PROFILE_FIELDS":
        required = [company_profile.legal_name, company_profile.org_number, company_profile.address_line1, company_profile.postal_code, company_profile.city, company_profile.email]
        return all((x or "").strip() for x in required)
    if check_key == "HAS_COMPANY_PAYMENT_METHOD":
        return company_profile.has_any_payment_method()
    if check_key == "HAS_TERMS_PAYMENT_DAYS":
        return bool(company_profile.payment_terms_days and company_profile.payment_terms_days > 0)
    return True


def compute_completeness(db: Session, project_id: int, mode: str, segment: str, lang: str = "ru") -> CompletenessReport:
    project = db.get(Project, project_id)
    if not project:
        return CompletenessReport(score=0, level="LOW", missing=[], can_issue_fixed_price=False, can_issue_mode=False)

    baseline = compute_project_baseline(db, project_id, include_materials=True, include_travel_setup_buffers=True)
    company_profile = get_or_create_company_profile(db)
    rules = (
        db.query(CompletenessRule)
        .filter(CompletenessRule.is_active.is_(True))
        .filter(CompletenessRule.segment.in_(["ANY", segment]))
        .filter(CompletenessRule.pricing_mode.in_(["ANY", mode]))
        .all()
    )
    total_weight = sum(max(0, int(rule.weight or 0)) for rule in rules)
    passed_weight = 0
    missing: list[MissingCompletenessItem] = []

    takeoff = get_or_create_project_takeoff_settings(db, project_id)

    for rule in rules:
        weight = max(0, int(rule.weight or 0))
        if rule.check_key == "HAS_PERIMETER_AND_HEIGHT_FOR_WALL_AREA" and takeoff.m2_basis not in {"WALL_AREA", "PAINTABLE_TOTAL"}:
            continue
        if rule.check_key == "HAS_FLOOR_AREA_FOR_CEILING_OR_FLOOR" and takeoff.m2_basis not in {"FLOOR_AREA", "CEILING_AREA"}:
            continue
        ok = _check_value(project, baseline, company_profile, rule.check_key)
        if ok:
            passed_weight += weight
            continue
        message = rule.message_sv if lang == "sv" else rule.message_ru
        hint = (rule.hint_link or "").replace("{project_id}", str(project.id)) or None
        missing.append(MissingCompletenessItem(rule.check_key, rule.severity, weight, message, hint))

    score = 100 if total_weight == 0 else int((Decimal(passed_weight) / Decimal(total_weight) * Decimal("100")).quantize(Decimal("1")))
    policy = get_or_create_pricing_policy(db)
    threshold_map = {
        "FIXED_TOTAL": int(policy.min_completeness_score_for_fixed or 70),
        "PER_M2": int(policy.min_completeness_score_for_per_m2 or 60),
        "PER_ROOM": int(policy.min_completeness_score_for_per_room or 60),
    }
    has_block = any(item.severity == "BLOCK" for item in missing)
    can_issue_mode = (not has_block) and score >= threshold_map.get(mode, 0)

    missing.sort(key=lambda x: (0 if x.severity == "BLOCK" else 1, -x.weight, x.check_key))
    return CompletenessReport(
        score=score,
        level=_level(score),
        missing=missing,
        can_issue_fixed_price=(mode != "FIXED_TOTAL" or can_issue_mode),
        can_issue_mode=can_issue_mode,
    )
