from __future__ import annotations

import sys

from fixer.__main__ import main


if __name__ == "__main__":
    main(["tray", *sys.argv[1:]])
