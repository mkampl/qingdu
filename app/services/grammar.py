"""
Sentence-pattern detection for the reader.

Ships ~30 HSK 1–5 grammar patterns as inline annotations (Phase D shipped
the first 10, Phase 1.7 added the next 20).
The detector runs after jieba segmentation and emits per-pattern matches
with their token-range positions so the SPA can underline + popover them.

Why regex-on-text, not token equality:
    jieba happily fuses "越来越" into a single token and "因为" into a
    standalone one. Matching by token text would either miss the colloquial
    "越来越" form of 越…越 or require a lookup table for every fused variant.
    Matching on the raw sentence text and projecting the char span back to
    token indices is more robust and ages better as the corpus changes.

Adding patterns:
    Append a `PatternDef` to PATTERNS with a unique `id`, a regex, and a
    short explanation. The regex runs against the raw sentence text. Spans
    are token-aligned automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Sentence:
    """Minimal sentence shape the detector needs. `words` are jieba tokens
    in reading order; `text` is the joined original text."""

    words: list[str]
    text: str


@dataclass
class PatternMatch:
    pattern_id: str
    sentence_idx: int
    start_word_idx: int  # absolute index into the analyse response's `words`
    end_word_idx: int  # absolute index into `words` (inclusive)
    span_text: str


@dataclass
class PatternDef:
    id: str
    title: str
    pinyin: str
    hsk_level: int
    explanation: str
    example: str
    example_translation: str
    # Regex applied to Sentence.text. The pattern's full match span (group 0)
    # is what gets highlighted; named subgroups are ignored.
    regex: re.Pattern[str]


# Patterns ordered roughly by HSK level so the "first to match" semantics
# in the SPA pick the more elementary pattern when two overlap.

PATTERNS: list[PatternDef] = [
    PatternDef(
        id="shi-de",
        title="是…的",
        pinyin="shì … de",
        hsk_level=2,
        explanation=(
            "Used to emphasise when, where, how, or by whom a past action happened. "
            "The 是 introduces the emphasised element; 的 closes the structure."
        ),
        example="我是昨天来的。",
        example_translation='I came yesterday. (emphasis on "yesterday")',
        # Need at least one character between 是 and 的; bare 是的 ("yes") is
        # not the emphasis construction.
        regex=re.compile(r"是[^。！？!?…]{1,30}?的"),
    ),
    PatternDef(
        id="ba",
        title="把 disposal",
        pinyin="bǎ",
        hsk_level=3,
        explanation=(
            "Moves the object in front of the verb to emphasise what was done to it. "
            'Often translated as "take X and …" — "I took the book and read it."'
        ),
        example="我把书读完了。",
        example_translation="I finished reading the book.",
        # 把 + at least one follow-up character. False positives on idioms
        # like 一把 are tolerable — better to highlight than to miss.
        regex=re.compile(r"把[一-鿿]{1,8}"),
    ),
    PatternDef(
        id="bei",
        title="被 passive",
        pinyin="bèi",
        hsk_level=3,
        explanation=(
            "Marks the passive voice: the subject is acted upon. 被 introduces the "
            "agent (optional) and is followed by the verb."
        ),
        example="苹果被吃了。",
        example_translation="The apple was eaten.",
        regex=re.compile(r"被[一-鿿]{1,8}"),
    ),
    PatternDef(
        id="yue-yue",
        title="越…越…",
        pinyin="yuè … yuè …",
        hsk_level=3,
        explanation=(
            '"The more X, the more Y." Pairs two qualities or actions that increase '
            "together. The collocation 越来越 (increasingly) is the same structure."
        ),
        example="天气越来越冷。",
        example_translation="The weather is getting colder and colder.",
        # Two 越 with up to a handful of characters between. Sentence-end
        # punctuation breaks the run.
        regex=re.compile(r"越[一-鿿]{0,10}?越"),
    ),
    PatternDef(
        id="yibian-yibian",
        title="一边…一边…",
        pinyin="yìbiān … yìbiān …",
        hsk_level=3,
        explanation=(
            'Two simultaneous actions. "While doing X, also doing Y." Each verb '
            "phrase is preceded by 一边."
        ),
        example="他一边吃饭一边看电视。",
        example_translation="He eats while watching TV.",
        regex=re.compile(r"一边[一-鿿]{1,15}?一边[一-鿿]{1,15}"),
    ),
    PatternDef(
        id="yinwei-suoyi",
        title="因为…所以…",
        pinyin="yīnwèi … suǒyǐ …",
        hsk_level=2,
        explanation=(
            '"Because X, therefore Y." Cause-and-effect pair. Either half can be '
            "dropped in colloquial speech, but here we only highlight the complete form."
        ),
        example="因为下雨,所以我没去。",
        example_translation="Because it rained, I didn't go.",
        regex=re.compile(r"(?:因为|由于)[一-鿿,，]{1,30}?所以[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="suiran-danshi",
        title="虽然…但是…",
        pinyin="suīrán … dànshì …",
        hsk_level=3,
        explanation=(
            '"Although X, but Y." 但是 can be replaced with 可是 or 不过 with no change in meaning.'
        ),
        example="虽然累,但是很开心。",
        example_translation="Although tired, I'm very happy.",
        regex=re.compile(r"虽然[一-鿿,，]{1,30}?(?:但是|可是|不过)[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="budan-erqie",
        title="不但…而且…",
        pinyin="búdàn … érqiě …",
        hsk_level=3,
        explanation=(
            '"Not only X, but also Y." 不但 can be replaced with 不仅; the second '
            "half often uses 还 / 也 instead of 而且."
        ),
        example="他不但聪明,而且很努力。",
        example_translation="He's not only smart, but also hardworking.",
        regex=re.compile(r"(?:不但|不仅)[一-鿿,，]{1,25}?(?:而且|并且)[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="ruguo-jiu",
        title="如果…就…",
        pinyin="rúguǒ … jiù …",
        hsk_level=2,
        explanation=(
            '"If X, then Y." The most common conditional. 如果 can be replaced with 要是 or 假如.'
        ),
        example="如果你有时间,就来。",
        example_translation="If you have time, come over.",
        regex=re.compile(r"(?:如果|要是|假如)[一-鿿,，]{1,30}?就[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="le-aspect",
        title="了 — completed action",
        pinyin="le",
        hsk_level=1,
        explanation=(
            "Marks an action as completed (post-verbal 了) or a change of state "
            "(sentence-final 了). Worth re-reading whenever you spot it — the position "
            "shifts the meaning."
        ),
        example="我吃了饭。",
        example_translation="I have eaten.",
        # Highlight a verb + 了 cluster. We bound to 1 preceding CJK char to
        # keep the span tight; only the first occurrence per sentence fires.
        regex=re.compile(r"[一-鿿]了"),
    ),
    # --- Phase 1.7 expansion: HSK 2–5 patterns -------------------------------
    PatternDef(
        id="cong-dao",
        title="从…到…",
        pinyin="cóng … dào …",
        hsk_level=2,
        explanation=(
            '"From X to Y" — frames a range, whether physical (Beijing to Shanghai), '
            "temporal (Monday to Friday), or logical (beginner to advanced)."
        ),
        example="从北京到上海很远。",
        example_translation="It's far from Beijing to Shanghai.",
        regex=re.compile(r"从[一-鿿]{1,15}?到[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="gen-yiqi",
        title="跟/和…一起",
        pinyin="gēn / hé … yìqǐ",
        hsk_level=2,
        explanation=(
            '"Together with X." 跟 and 和 are interchangeable here; the 一起 closes '
            "the structure. Common with verbs of activity (eat, go, work)."
        ),
        example="我跟朋友一起吃饭。",
        example_translation="I'm eating together with friends.",
        regex=re.compile(r"(?:跟|和)[一-鿿]{1,15}?一起"),
    ),
    PatternDef(
        id="guo-experiential",
        title="…过 — experiential aspect",
        pinyin="guò",
        hsk_level=2,
        explanation=(
            'Marks "has experienced X before" — distinct from 了 (completed action). '
            "Often pairs with 没 in the negative: 没去过 = have never been."
        ),
        example="我去过中国。",
        example_translation="I have been to China (before).",
        regex=re.compile(r"[一-鿿]过"),
    ),
    PatternDef(
        id="bi-comparison",
        title="比…",
        pinyin="bǐ …",
        hsk_level=2,
        explanation=(
            'Basic comparison: "A 比 B + adjective" — A is more [adj] than B. '
            "Intensifiers 还 / 更 can sit before the adjective to mean 'even more'."
        ),
        example="他比我还高。",
        example_translation="He's even taller than me.",
        regex=re.compile(r"比[一-鿿]{1,8}?(?:还|更)?[一-鿿]"),
    ),
    PatternDef(
        id="zhe-durative",
        title="…着 — durative aspect",
        pinyin="zhe",
        hsk_level=3,
        explanation=(
            "Sits after a verb to mark an ongoing state or accompanying action. "
            'Think "while" — 笑着说 = "said while smiling".'
        ),
        example="他笑着说话。",
        example_translation="He spoke while smiling.",
        regex=re.compile(r"[一-鿿]着[一-鿿]"),
    ),
    PatternDef(
        id="de-resultative",
        title="…得 + result",
        pinyin="… de …",
        hsk_level=3,
        explanation=(
            "Verb + 得 + complement describes the manner or degree of the action: "
            '"runs fast", "speaks clearly". The complement is usually an adjective '
            "or short phrase."
        ),
        example="他跑得很快。",
        example_translation="He runs very fast.",
        regex=re.compile(r"[一-鿿]得[一-鿿]{1,8}"),
    ),
    PatternDef(
        id="you-you",
        title="又…又…",
        pinyin="yòu … yòu …",
        hsk_level=3,
        explanation=(
            '"Both X and Y" — pairs two qualities or actions that hold at the '
            "same time. 又 is repeated before each."
        ),
        example="她又聪明又漂亮。",
        example_translation="She's both smart and beautiful.",
        regex=re.compile(r"又[一-鿿]{1,6}?又[一-鿿]{1,6}"),
    ),
    PatternDef(
        id="rang-jiao",
        title="让/叫 + sb + verb",
        pinyin="ràng / jiào",
        hsk_level=3,
        explanation=(
            'Causative: "make / let / have someone do something". 让 and 叫 are '
            "near-synonyms here; 叫 is slightly more colloquial."
        ),
        example="妈妈让我学习。",
        example_translation="Mom has me study.",
        regex=re.compile(r"(?:让|叫)[一-鿿]{1,6}?[一-鿿]"),
    ),
    PatternDef(
        id="gei-benefactive",
        title="给 + sb + verb",
        pinyin="gěi",
        hsk_level=3,
        explanation=(
            'Marks the beneficiary or recipient of an action: "do X for / to someone". '
            "Distinguish from 给 as the main verb (=to give)."
        ),
        example="我给你打电话。",
        example_translation="I'll call you (for you).",
        regex=re.compile(r"给[一-鿿]{1,5}?(?:打|写|做|发|买|带|寄|讲|说)"),
    ),
    PatternDef(
        id="jiuyao-le",
        title="就要…了",
        pinyin="jiùyào … le",
        hsk_level=3,
        explanation=(
            'Imminent future: "about to do X". The 了 closes the structure. '
            "快要…了 and 快…了 are near-synonyms."
        ),
        example="火车就要开了。",
        example_translation="The train is about to leave.",
        regex=re.compile(r"(?:就要|快要|快)[一-鿿]{1,8}?了"),
    ),
    PatternDef(
        id="yi-jiu",
        title="一…就…",
        pinyin="yī … jiù …",
        hsk_level=3,
        explanation=(
            '"As soon as X, then Y." Both halves take a verb phrase. Common in '
            "narrative: 一到家就… = as soon as I get home, ..."
        ),
        example="我一回家就吃饭。",
        example_translation="As soon as I get home, I eat.",
        regex=re.compile(r"一[一-鿿]{1,8}?就[一-鿿]{1,8}"),
    ),
    PatternDef(
        id="gang-jiu",
        title="刚…就…",
        pinyin="gāng … jiù …",
        hsk_level=3,
        explanation=(
            '"Just (did X), and then Y immediately happened." Marks a tight '
            "temporal sequence — Y follows hard on the heels of X."
        ),
        example="我刚到家就下雨了。",
        example_translation="I had just got home when it started raining.",
        regex=re.compile(r"刚[一-鿿]{1,8}?就[一-鿿]{1,8}"),
    ),
    PatternDef(
        id="chule-yiwai",
        title="除了…以外",
        pinyin="chúle … yǐwài",
        hsk_level=3,
        explanation=(
            '"Apart from X" — followed by 还 / 也 (also Y) or 都 (everything but X). '
            "Watch the second clause; it flips the meaning entirely."
        ),
        example="除了汉语以外,他还会日语。",
        example_translation="Apart from Chinese, he also speaks Japanese.",
        regex=re.compile(r"除了[一-鿿,，]{1,20}?以外"),
    ),
    PatternDef(
        id="lian-ye",
        title="连…也/都…",
        pinyin="lián … yě / dōu …",
        hsk_level=4,
        explanation=(
            '"Even X (does/doesn\'t) Y" — focus marker that elevates X as '
            "surprising. The second half almost always carries 也 or 都."
        ),
        example="他连米饭也不吃。",
        example_translation="He won't even eat rice.",
        regex=re.compile(r"连[一-鿿]{1,10}?(?:也|都)[一-鿿]{1,8}"),
    ),
    PatternDef(
        id="zhiyao-jiu",
        title="只要…就…",
        pinyin="zhǐyào … jiù …",
        hsk_level=4,
        explanation=(
            '"As long as X, then Y" — sufficient condition. Distinguish from '
            "只有…才… (only if), which marks a necessary condition."
        ),
        example="只要努力,就会成功。",
        example_translation="As long as you try hard, you'll succeed.",
        regex=re.compile(r"只要[一-鿿,，]{1,20}?就[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="zhiyou-cai",
        title="只有…才…",
        pinyin="zhǐyǒu … cái …",
        hsk_level=4,
        explanation=(
            '"Only if X, can Y" — necessary condition. Compare 只要…就 (sufficient): '
            "this is strictly stronger and the 才 underlines the exclusivity."
        ),
        example="只有努力学习才能进步。",
        example_translation="Only with hard study can you progress.",
        regex=re.compile(r"只有[一-鿿,，]{1,20}?才[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="bushi-ershi",
        title="不是…而是…",
        pinyin="bù shì … ér shì …",
        hsk_level=4,
        explanation=(
            '"Not X, but rather Y" — corrective construction. The 而是 introduces '
            "the actual answer after rejecting an apparent one."
        ),
        example="这不是错误,而是新发现。",
        example_translation="This isn't an error — it's a new discovery.",
        regex=re.compile(r"不是[一-鿿,，]{1,20}?而是[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="yaome-yaome",
        title="要么…要么…",
        pinyin="yàome … yàome …",
        hsk_level=5,
        explanation=(
            '"Either X or Y" — exclusive alternatives. Each half can take a verb '
            "phrase; the two options are presented as mutually exclusive."
        ),
        example="要么去看电影,要么留在家里。",
        example_translation="Either go to the movies or stay home.",
        regex=re.compile(r"要么[一-鿿,，]{1,20}?要么[一-鿿]{1,15}"),
    ),
    PatternDef(
        id="dehua-jiu",
        title="…的话,就…",
        pinyin="… dehuà, jiù …",
        hsk_level=4,
        explanation=(
            'Conditional softener: "if X, then Y". The 的话 sits at the end of the '
            "condition clause; 就 (or 那) opens the consequence. Often more "
            "colloquial than 如果…就…."
        ),
        example="累的话,就休息一下。",
        example_translation="If you're tired, take a break.",
        regex=re.compile(r"[一-鿿]的话[,，]?[一-鿿]{0,3}?(?:就|那)"),
    ),
    PatternDef(
        id="kenenghui",
        title="可能 + verb",
        pinyin="kěnéng …",
        hsk_level=3,
        explanation=(
            'Speculative modal: "may / might X". Often paired with 会 (will) for '
            'future probability: 可能会下雨 = "it might rain".'
        ),
        example="他可能会来。",
        example_translation="He might come.",
        regex=re.compile(r"可能[一-鿿]{0,3}?(?:会|是|有|要|来|去|得)"),
    ),
]

_PATTERN_BY_ID = {p.id: p for p in PATTERNS}


def pattern_meta(pattern_id: str) -> dict:
    p = _PATTERN_BY_ID[pattern_id]
    return {
        "id": p.id,
        "title": p.title,
        "pinyin": p.pinyin,
        "hsk_level": p.hsk_level,
        "explanation": p.explanation,
        "example": p.example,
        "example_translation": p.example_translation,
    }


def _token_range_for_char_span(
    words: list[str], char_start: int, char_end: int
) -> tuple[int, int] | None:
    """
    Walk tokens until we find the smallest [first, last] index range whose
    combined character span covers [char_start, char_end). Returns None if
    the sentence text and the joined-tokens string don't align (shouldn't
    happen — the caller builds Sentence.text as "".join(words)).
    """
    pos = 0
    first = None
    last = None
    for i, w in enumerate(words):
        tok_start = pos
        tok_end = pos + len(w)
        # Token overlaps the requested char range?
        if tok_end > char_start and tok_start < char_end:
            if first is None:
                first = i
            last = i
        pos = tok_end
        if pos >= char_end and first is not None:
            break
    if first is None or last is None:
        return None
    return first, last


def detect_patterns(
    sentences: list[tuple[int, Sentence]],
) -> tuple[list[PatternMatch], list[dict]]:
    """
    Walk every sentence and collect pattern matches.

    `sentences` is a list of (sentence_start_word_idx, Sentence) — the
    caller knows the absolute word offset into `analysis_words` for each
    sentence so we can return globally-positioned spans.

    Returns (matches, unique_pattern_metas). `unique_pattern_metas` is the
    set of patterns that fired at least once, in the order they first
    appeared; the SPA uses it to render the sidebar panel.
    """
    matches: list[PatternMatch] = []
    seen_ids: set[str] = set()
    metas_in_order: list[dict] = []

    for sentence_idx, (offset, sentence) in enumerate(sentences):
        # le-aspect fires on basically every past-tense sentence; cap it at
        # one match per sentence so it remains a callout, not noise.
        le_seen_this_sentence = False
        for pattern in PATTERNS:
            for m in pattern.regex.finditer(sentence.text):
                if pattern.id == "le-aspect":
                    if le_seen_this_sentence:
                        continue
                    le_seen_this_sentence = True
                token_range = _token_range_for_char_span(sentence.words, m.start(), m.end())
                if token_range is None:
                    continue
                first, last = token_range
                matches.append(
                    PatternMatch(
                        pattern_id=pattern.id,
                        sentence_idx=sentence_idx,
                        start_word_idx=offset + first,
                        end_word_idx=offset + last,
                        span_text=m.group(0),
                    )
                )
                if pattern.id not in seen_ids:
                    seen_ids.add(pattern.id)
                    metas_in_order.append(pattern_meta(pattern.id))

    return matches, metas_in_order


__all__ = [
    "PATTERNS",
    "PatternDef",
    "PatternMatch",
    "Sentence",
    "detect_patterns",
    "pattern_meta",
]
