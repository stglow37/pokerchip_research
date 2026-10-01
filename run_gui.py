from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from pokerchip.gui import main

if __name__ == "__main__":
    import json
    config=Path(__file__).with_name('launch_config.json')
    default=json.loads(config.read_text(encoding='utf8')).get('default_project') if config.exists() else None
    main(sys.argv[1] if len(sys.argv)>1 else default)
