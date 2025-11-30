import csv
from io import StringIO

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.services.stats import (
    get_profit_by_client,
    get_profit_by_month,
    get_profit_by_worktype_category,
)

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/")
async def stats_overview(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    by_month = get_profit_by_month(db)
    by_client = get_profit_by_client(db)
    by_worktype = get_profit_by_worktype_category(db)

    context = template_context(request, lang)
    context.update(
        {"profit_by_month": by_month, "profit_by_client": by_client, "profit_by_worktype": by_worktype}
    )
    return templates.TemplateResponse("stats/overview.html", context)


@router.get("/export/monthly.csv")
async def export_monthly_csv(db: Session = Depends(get_db)):
    rows = get_profit_by_month(db)

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["year", "month", "revenue", "total_cost", "profit"])
    for row in rows:
        writer.writerow([row["year"], row["month"], row["revenue"], row["total_cost"], row["profit"]])

    return Response(content=output.getvalue(), media_type="text/csv")
