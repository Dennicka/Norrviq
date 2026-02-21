from pathlib import Path

import itsdangerous
import multipart


def test_no_shadow_imports():
    repo_root = Path(__file__).resolve().parents[1]

    multipart_path = Path(multipart.__file__).resolve()
    itsdangerous_path = Path(itsdangerous.__file__).resolve()

    assert repo_root not in multipart_path.parents
    assert repo_root not in itsdangerous_path.parents
