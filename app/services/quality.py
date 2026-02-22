from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.sanity_rule import SanityRule
from app.models.settings import get_or_create_settings


@dataclass
class QualityIssue:
    severity: str
    code: str
    entity: str
    entity_id: int | None
    field: str
    message: str
    current_value: str
    go_fix_url: str | None = None


@dataclass
class QualityReport:
    issues: list[QualityIssue]

    @property
    def warnings_count(self) -> int:
        return len([i for i in self.issues if i.severity == "WARNING"])

    @property
    def blocks_count(self) -> int:
        return len([i for i in self.issues if i.severity == "BLOCK"])

    @property
    def can_issue_documents(self) -> bool:
        return self.blocks_count == 0


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _rule_message(rule: SanityRule, lang: str = "ru") -> str:
    return rule.message_sv if lang == "sv" else rule.message_ru


def _eval_min_max(rule: SanityRule, value: Decimal | None) -> bool:
    if value is None:
        return False
    if rule.min_value is not None and value < rule.min_value:
        return True
    if rule.max_value is not None and value > rule.max_value:
        return True
    return False


def _eval_ratio_max(value_a: Decimal | None, value_b: Decimal | None, max_ratio: Decimal | None) -> bool:
    if value_a is None or value_b in (None, Decimal("0")) or max_ratio is None:
        return False
    return value_a > value_b * max_ratio


def _eval_delta_max(value_a: Decimal | None, value_b: Decimal | None, max_delta: Decimal | None) -> bool:
    if value_a is None or value_b is None or max_delta is None:
        return False
    return abs(value_a - value_b) > max_delta


def evaluate_room_quality(room: Room, rules: list[SanityRule], *, lang: str = "ru") -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    values = {
        "wall_height_m": _to_decimal(room.wall_height_m),
        "wall_perimeter_m": _to_decimal(room.wall_perimeter_m),
        "floor_area_m2": _to_decimal(room.floor_area_m2),
        "wall_area_m2": _to_decimal(room.wall_area_m2),
        "ceiling_area_m2": _to_decimal(room.ceiling_area_m2),
        "baseboard_length_m": _to_decimal(room.baseboard_length_m),
    }
    for rule in rules:
        triggered = False
        current_value = ""
        if rule.rule_type == "MIN_MAX":
            value = values.get(rule.field)
            triggered = _eval_min_max(rule, value)
            current_value = str(value) if value is not None else ""
        elif rule.rule_type == "RATIO_MAX" and rule.field == "wall_area_m2_to_floor_area_m2":
            wall_area = values.get("wall_area_m2")
            floor_area = values.get("floor_area_m2")
            triggered = _eval_ratio_max(wall_area, floor_area, _to_decimal(rule.max_value))
            current_value = f"wall={wall_area}, floor={floor_area}"
        elif rule.rule_type == "DELTA_MAX" and rule.field == "ceiling_area_m2_to_floor_area_m2":
            ceiling = values.get("ceiling_area_m2")
            floor_area = values.get("floor_area_m2")
            triggered = _eval_delta_max(ceiling, floor_area, _to_decimal(rule.max_value))
            current_value = f"ceiling={ceiling}, floor={floor_area}"
        if triggered:
            issues.append(
                QualityIssue(
                    severity=rule.severity,
                    code=f"{rule.entity}_{rule.field}_{rule.rule_type}",
                    entity="ROOM",
                    entity_id=room.id,
                    field=rule.field,
                    message=_rule_message(rule, lang),
                    current_value=current_value,
                    go_fix_url=f"/projects/{room.project_id}/rooms/{room.id}/edit" if room.id else None,
                )
            )
    return issues


def evaluate_work_item_quality(item: ProjectWorkItem, rules: list[SanityRule], *, lang: str = "ru") -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for rule in rules:
        if rule.rule_type != "MIN_MAX":
            continue
        value = _to_decimal(getattr(item, rule.field, None))
        if not _eval_min_max(rule, value):
            continue
        issues.append(
            QualityIssue(
                severity=rule.severity,
                code=f"{rule.entity}_{rule.field}_{rule.rule_type}",
                entity="WORK_ITEM",
                entity_id=item.id,
                field=rule.field,
                message=_rule_message(rule, lang),
                current_value=str(value) if value is not None else "",
                go_fix_url=f"/projects/{item.project_id}/items/{item.id}/edit" if item.id else None,
            )
        )
    return issues


def evaluate_project_quality(db: Session, project_id: int, *, lang: str = "ru") -> QualityReport:
    project = db.get(Project, project_id)
    if not project:
        return QualityReport(issues=[])

    rules = db.query(SanityRule).filter(SanityRule.is_active.is_(True)).all()
    room_rules = [r for r in rules if r.entity == "ROOM"]
    work_item_rules = [r for r in rules if r.entity == "WORK_ITEM"]
    project_rules = [r for r in rules if r.entity == "PROJECT"]

    issues: list[QualityIssue] = []
    for room in project.rooms:
        issues.extend(evaluate_room_quality(room, room_rules, lang=lang))
    for item in project.work_items:
        issues.extend(evaluate_work_item_quality(item, work_item_rules, lang=lang))

    settings = get_or_create_settings(db)
    project_values = {
        "rooms_count": Decimal(len(project.rooms)),
        "work_items_count": Decimal(len(project.work_items)),
        "hourly_rate_company": _to_decimal(settings.hourly_rate_company),
    }
    for rule in project_rules:
        if rule.rule_type != "MIN_MAX":
            continue
        value = project_values.get(rule.field)
        if not _eval_min_max(rule, value):
            continue
        issues.append(
            QualityIssue(
                severity=rule.severity,
                code=f"{rule.entity}_{rule.field}_{rule.rule_type}",
                entity="PROJECT",
                entity_id=project.id,
                field=rule.field,
                message=_rule_message(rule, lang),
                current_value=str(value) if value is not None else "",
                go_fix_url=f"/projects/{project.id}",
            )
        )

    return QualityReport(issues=issues)
