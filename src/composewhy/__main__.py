"""composewhy module execution entry point (python -m composewhy)."""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
