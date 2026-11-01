"""
Parser for Konfuzius Institut Old HSK vocabulary list

Format:
  汉字（级别）          - e.g., 说（一级）
  汉字（词性）（级别）  - e.g., 对（形容词）（二级）
"""

import re
from pathlib import Path

# Chinese number to Arabic conversion
CHINESE_TO_ARABIC = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
}


def parse_konfuzius_old_hsk(file_path: Path) -> dict[str, str]:
    """
    Parse Konfuzius Institut Old HSK list

    Returns:
        Dict mapping hanzi to level (e.g., {'说': 'old-1', '对': 'old-2'})
        For words with multiple entries (different word types), uses the lowest level
    """
    vocab = {}

    with open(file_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Parse format: 汉字（级别） or 汉字（词性）（级别）
            # Try to extract hanzi and level
            match = re.match(r"^(.+?)（.+）（([一二三四五六])级）$", line)
            if match:
                # Format: 汉字（词性）（级别）
                hanzi = match.group(1)
                level_chinese = match.group(2)
            else:
                # Try format: 汉字（级别）
                match = re.match(r"^(.+?)（([一二三四五六])级）$", line)
                if match:
                    hanzi = match.group(1)
                    level_chinese = match.group(2)
                else:
                    # Skip unparseable lines
                    continue

            # Convert Chinese level to numeric
            if level_chinese in CHINESE_TO_ARABIC:
                level_num = CHINESE_TO_ARABIC[level_chinese]
                level_str = f"old-{level_num}"

                # If word already exists, keep the lowest level
                if hanzi in vocab:
                    existing_level = int(vocab[hanzi].replace("old-", ""))
                    if level_num < existing_level:
                        vocab[hanzi] = level_str
                else:
                    vocab[hanzi] = level_str

    return vocab
