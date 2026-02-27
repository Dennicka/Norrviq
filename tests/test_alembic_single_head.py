import subprocess
import sys


def test_alembic_has_single_head():
    proc = subprocess.run([sys.executable, "-m", "alembic", "heads"], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    head_lines = [line for line in proc.stdout.splitlines() if "(head)" in line]
    assert len(head_lines) == 1, proc.stdout
