#!/usr/bin/env python3
"""Split user words that are not dictionary words (很多, 我来, 洗衣服) into
their parts. Dry run by default; see app/services/glue_migration.py.

    python tools/split_glue_words.py --db data/qingdu.db [--json]
    python tools/split_glue_words.py --db data/qingdu.db --apply

Inside the container (tools/ is not in the image):

    docker exec chinese_analyzer python -m app.services.glue_migration --db /app/data/qingdu.db
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.glue_migration import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
