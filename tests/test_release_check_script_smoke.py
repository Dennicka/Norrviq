from scripts.release_check import StepResult, format_summary_table


def test_format_summary_table_includes_headers_and_rows() -> None:
    table = format_summary_table(
        [
            StepResult(step="Lint", command="ruff check .", status="PASS", duration_s=1.23, output=""),
            StepResult(
                step="Doctor",
                command="python -m app.scripts.doctor",
                status="PASS",
                duration_s=0.87,
                output="",
                notes="configured=auto, active=weasyprint, weasyprint=1, playwright=0",
            ),
        ]
    )

    assert "Step" in table
    assert "Status" in table
    assert "Lint" in table
    assert "Doctor" in table
    assert "configured=auto" in table
