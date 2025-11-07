# HSK Comparison Script

## Overview

This script compares your school's old HSK vocabulary list (`tmp_list.txt`) with the GitHub vocabulary source to find differences and missing words.

## Usage

```bash
# Run the comparison script
python3 scripts/compare_hsk_sources.py
```

## What It Does

1. **Parses school list** (`tmp_list.txt`)
   - Format: `爱（一级）` → word "爱" at level 1
   - Converts Chinese levels (一级, 二级, etc.) to numeric levels (1, 2, etc.)

2. **Downloads GitHub source**
   - Fetches vocabulary from: https://github.com/drkameleon/complete-hsk-vocabulary
   - Extracts all words with old HSK levels

3. **Compares both sources**
   - Finds words only in school list
   - Finds words only in GitHub source
   - Finds words with different levels in each source
   - Counts words that match in both

4. **Generates report**
   - Console output with summary and samples
   - Detailed JSON file: `scripts/hsk_comparison_output/full_comparison.json`

## Output

The script will show:
- Total word counts for each source
- Level distribution statistics
- Words with different levels (first 50)
- Words only in school list (first 100)
- Words only in GitHub source (first 100)

Full detailed data is saved to JSON for further analysis.

## Example Output

```
================================================================================
HSK OLD VOCABULARY COMPARISON REPORT
================================================================================

Total words in school list: 5000
Total words in GitHub source (with old HSK): 6500

School list distribution:
  Level 1: 150 words
  Level 2: 150 words
  ...

COMPARISON RESULTS
--------------------------------------------------------------------------------

✅ Words in both sources (same level): 4500
⚠️  Words with different levels: 200
🏫 Words ONLY in school list: 300
🌐 Words ONLY in GitHub source: 2000
```

## Requirements

- Python 3.7+
- httpx library (install with: `pip install httpx`)

## Output Files

- `scripts/hsk_comparison_output/full_comparison.json` - Complete comparison data
