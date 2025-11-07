#!/usr/bin/env python3
"""
Compare school HSK list (tmp_list.txt) with GitHub vocabulary source
to find differences and missing words.
"""

import json
import httpx
import sys
from pathlib import Path

# Chinese level mapping
LEVEL_MAP = {
    '一级': '1',
    '二级': '2',
    '三级': '3',
    '四级': '4',
    '五级': '5',
    '六级': '6'
}

HSK_VOCAB_URL = "https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/refs/heads/main/complete.json"

def parse_school_list(file_path):
    """Parse tmp_list.txt and extract words with old HSK levels."""
    school_vocab = {}

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Format: 爱（一级）
            if '（' in line and '）' in line:
                word = line.split('（')[0]
                level_chinese = line.split('（')[1].split('）')[0]

                # Convert Chinese level to number
                level_num = LEVEL_MAP.get(level_chinese)
                if level_num:
                    school_vocab[word] = f'old-{level_num}'

    return school_vocab

def parse_github_source():
    """Download and parse GitHub HSK vocabulary source."""
    print("Downloading GitHub vocabulary source...")

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(HSK_VOCAB_URL)
            response.raise_for_status()
            raw_data = response.json()
    except Exception as e:
        print(f"Error downloading GitHub source: {e}")
        sys.exit(1)

    github_vocab = {}

    for entry in raw_data:
        if not isinstance(entry, dict):
            continue

        simplified = entry.get('simplified')
        if not simplified:
            continue

        levels = entry.get('level', [])
        if not levels:
            continue

        # Extract old HSK level
        level_old = None
        for level in levels:
            if isinstance(level, str) and level.startswith('old-'):
                level_old = level
                break

        if level_old:
            github_vocab[simplified] = level_old

    return github_vocab

def compare_vocabularies(school_vocab, github_vocab):
    """Compare two vocabulary sources and generate report."""

    # Words only in school list
    only_in_school = {}
    for word, level in school_vocab.items():
        if word not in github_vocab:
            only_in_school[word] = level

    # Words only in GitHub source
    only_in_github = {}
    for word, level in github_vocab.items():
        if word not in school_vocab:
            only_in_github[word] = level

    # Words with different levels
    different_levels = {}
    for word in school_vocab:
        if word in github_vocab:
            if school_vocab[word] != github_vocab[word]:
                different_levels[word] = {
                    'school': school_vocab[word],
                    'github': github_vocab[word]
                }

    # Words in both with same level
    same_in_both = {}
    for word in school_vocab:
        if word in github_vocab:
            if school_vocab[word] == github_vocab[word]:
                same_in_both[word] = school_vocab[word]

    return {
        'only_in_school': only_in_school,
        'only_in_github': only_in_github,
        'different_levels': different_levels,
        'same_in_both': same_in_both
    }

def print_report(comparison, school_vocab, github_vocab):
    """Print comparison report."""

    print("\n" + "="*80)
    print("HSK OLD VOCABULARY COMPARISON REPORT")
    print("="*80)

    print(f"\nTotal words in school list: {len(school_vocab)}")
    print(f"Total words in GitHub source (with old HSK): {len(github_vocab)}")

    # Level distribution in school list
    school_dist = {}
    for word, level in school_vocab.items():
        level_num = level.replace('old-', '')
        school_dist[level_num] = school_dist.get(level_num, 0) + 1

    print(f"\nSchool list distribution:")
    for level in sorted(school_dist.keys(), key=int):
        print(f"  Level {level}: {school_dist[level]} words")

    # Level distribution in GitHub source
    github_dist = {}
    for word, level in github_vocab.items():
        level_num = level.replace('old-', '')
        github_dist[level_num] = github_dist.get(level_num, 0) + 1

    print(f"\nGitHub source distribution:")
    for level in sorted(github_dist.keys(), key=int):
        print(f"  Level {level}: {github_dist[level]} words")

    print("\n" + "-"*80)
    print("COMPARISON RESULTS")
    print("-"*80)

    print(f"\n✅ Words in both sources (same level): {len(comparison['same_in_both'])}")
    print(f"⚠️  Words with different levels: {len(comparison['different_levels'])}")
    print(f"🏫 Words ONLY in school list: {len(comparison['only_in_school'])}")
    print(f"🌐 Words ONLY in GitHub source: {len(comparison['only_in_github'])}")

    # Show words with different levels
    if comparison['different_levels']:
        print("\n" + "-"*80)
        print("⚠️  WORDS WITH DIFFERENT LEVELS (first 50):")
        print("-"*80)
        count = 0
        for word, levels in sorted(comparison['different_levels'].items()):
            if count >= 50:
                remaining = len(comparison['different_levels']) - 50
                print(f"\n... and {remaining} more")
                break
            print(f"  {word}: School={levels['school']}, GitHub={levels['github']}")
            count += 1

    # Show words only in school list
    if comparison['only_in_school']:
        print("\n" + "-"*80)
        print("🏫 WORDS ONLY IN SCHOOL LIST (first 100):")
        print("-"*80)
        by_level = {}
        for word, level in comparison['only_in_school'].items():
            by_level.setdefault(level, []).append(word)

        count = 0
        for level in sorted(by_level.keys()):
            words = by_level[level]
            print(f"\n  {level}:")
            for word in words:
                if count >= 100:
                    remaining = len(comparison['only_in_school']) - 100
                    print(f"\n... and {remaining} more")
                    break
                print(f"    {word}")
                count += 1
            if count >= 100:
                break

    # Show words only in GitHub source
    if comparison['only_in_github']:
        print("\n" + "-"*80)
        print("🌐 WORDS ONLY IN GITHUB SOURCE (first 100):")
        print("-"*80)
        by_level = {}
        for word, level in comparison['only_in_github'].items():
            by_level.setdefault(level, []).append(word)

        count = 0
        for level in sorted(by_level.keys()):
            words = by_level[level]
            print(f"\n  {level}:")
            for word in words:
                if count >= 100:
                    remaining = len(comparison['only_in_github']) - 100
                    print(f"\n... and {remaining} more")
                    break
                print(f"    {word}")
                count += 1
            if count >= 100:
                break

def save_detailed_report(comparison, school_vocab, github_vocab):
    """Save detailed comparison to JSON files."""
    output_dir = Path('scripts/hsk_comparison_output')
    output_dir.mkdir(exist_ok=True)

    # Save full comparison
    with open(output_dir / 'full_comparison.json', 'w', encoding='utf-8') as f:
        json.dump({
            'only_in_school': comparison['only_in_school'],
            'only_in_github': comparison['only_in_github'],
            'different_levels': comparison['different_levels'],
            'statistics': {
                'school_total': len(school_vocab),
                'github_total': len(github_vocab),
                'same_count': len(comparison['same_in_both']),
                'different_count': len(comparison['different_levels']),
                'only_school_count': len(comparison['only_in_school']),
                'only_github_count': len(comparison['only_in_github'])
            }
        }, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Detailed report saved to: {output_dir}/full_comparison.json")

def main():
    """Main function."""
    script_dir = Path(__file__).parent.parent
    tmp_list_path = script_dir / 'tmp_list.txt'

    if not tmp_list_path.exists():
        print(f"Error: tmp_list.txt not found at {tmp_list_path}")
        sys.exit(1)

    print("Parsing school HSK list...")
    school_vocab = parse_school_list(tmp_list_path)
    print(f"✅ Loaded {len(school_vocab)} words from school list")

    print("\nParsing GitHub HSK source...")
    github_vocab = parse_github_source()
    print(f"✅ Loaded {len(github_vocab)} words with old HSK levels from GitHub")

    print("\nComparing vocabularies...")
    comparison = compare_vocabularies(school_vocab, github_vocab)

    print_report(comparison, school_vocab, github_vocab)
    save_detailed_report(comparison, school_vocab, github_vocab)

    print("\n" + "="*80)
    print("Comparison complete!")
    print("="*80)

if __name__ == '__main__':
    main()
