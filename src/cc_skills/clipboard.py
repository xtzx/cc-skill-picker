from __future__ import annotations

import shutil
import subprocess


def copy_text(text: str) -> None:
    if shutil.which("pbcopy") is None:
        raise RuntimeError("当前系统找不到 pbcopy，无法复制到剪贴板")

    subprocess.run(
        ["pbcopy"],
        input=text.encode("utf-8"),
        check=True,
    )
