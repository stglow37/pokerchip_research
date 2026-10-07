"""Allow python -m pokerchip alongside the existing pokerchip CLI entry point."""
from .cli import main

if __name__=='__main__':
    raise SystemExit(main())
