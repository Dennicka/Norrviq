from pathlib import Path
import re

RUNBOOK_DIR = Path("runbook")


def test_runbook_files_exist():
    expected = [
        "00-overview.md",
        "01-config.md",
        "02-deploy.md",
        "03-migrations.md",
        "04-backup-restore.md",
        "05-upgrade.md",
        "06-troubleshooting.md",
        "07-security.md",
        "08-release-checklist.md",
    ]
    for name in expected:
        assert (RUNBOOK_DIR / name).is_file(), f"Missing runbook file: {name}"


def test_runbook_local_markdown_links_resolve():
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    markdown_files = sorted(RUNBOOK_DIR.glob("*.md"))

    for md_file in markdown_files:
        text = md_file.read_text(encoding="utf-8")
        for target in link_re.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            resolved = (md_file.parent / path_part).resolve()
            assert resolved.exists(), f"Broken link in {md_file}: {target}"
