"""Regenerate logo.ico from logo.png and copy it into the app package. Rerun after
re-exporting the PNG from Inkscape."""

import shutil
from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent / "logo-blue.png"
DST = Path(__file__).parent / "logo.ico"
PACKAGE_DST = Path(__file__).parent.parent / "src" / "habito" / "ui" / "app_icon.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    img = Image.open(SRC).convert("RGBA")
    img.save(DST, format="ICO", sizes=SIZES)
    print(f"wrote {DST} with sizes {SIZES}")
    shutil.copyfile(DST, PACKAGE_DST)
    print(f"copied to {PACKAGE_DST}")


if __name__ == "__main__":
    main()
