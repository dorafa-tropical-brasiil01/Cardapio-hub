from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cardapio_app import create_app

app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5500"))
    app.run(host="0.0.0.0", port=port, debug=True)
