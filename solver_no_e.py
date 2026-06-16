#!/usr/bin/env python3
"""
HuragokForce2 — Substitution cipher solver for Halo subglyphs.

Sequence (from screenshots):
  Position:  0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18
  Glyph:     0  1  E  3  4  0  5  6  E  7  5  3  E  E  7  8  E  9  E

Glyph 2 is assumed to be 'E' (frequency analysis — appears 6/19 times).
Remaining unknowns: 0, 1, 3, 4, 5, 6, 7, 8, 9 (9 distinct glyphs).
Each maps to a unique letter (bijective substitution).

Strategy — dictionary-driven search:
  Instead of brute-forcing all letter assignments and checking if the result
  is English, we do the reverse: try to place dictionary words at each
  position and check if the implied glyph-to-letter mapping is consistent
  (bijective). This is vastly faster because the dictionary constrains the
  search immediately.
"""

import sys
import time
from pathlib import Path
from collections import defaultdict

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GLYPH_SEQUENCE = ['0', '1', '2', '3', '4', '0', '5', '6', '2',
                   '7', '5', '3', '2', '2', '7', '8', '2', '9', '2']
SEQ_LEN = len(GLYPH_SEQUENCE)  # 19

# Pre-solved mappings — none! No assumptions.
KNOWN_MAPPING = {}

# Only allow these as standalone 1-letter words
VALID_1LETTER = {'a', 'i'}

# Minimum word length (except for VALID_1LETTER)
MIN_WORD_LEN = 3

# Quality filters
MAX_WORDS = 5
MIN_AVG_WORD_LEN = 3.8
MAX_SHORT_WORDS = 1  # words of length <= 2 (only 'a' or 'i')
MIN_LONGEST_WORD = 5  # at least one word must be this long
MIN_LONG_WORDS = 2    # at least this many words must be >= 4 chars

TOP_N = 100

# ---------------------------------------------------------------------------
# Dictionary
# ---------------------------------------------------------------------------

def load_dictionary(path='/usr/share/dict/words', min_len=1, max_len=19):
    words = set()
    p = Path(path)
    if not p.exists():
        print(f"Dictionary not found at {path}", file=sys.stderr)
        sys.exit(1)
    with open(p) as f:
        for line in f:
            raw = line.strip()
            # Skip proper nouns (capitalized), possessives, abbreviations
            if not raw or raw[0].isupper():
                continue
            if "'" in raw or not raw.isalpha():
                continue
            w = raw.lower()
            if len(w) < MIN_WORD_LEN and w not in VALID_1LETTER:
                continue
            if min_len <= len(w) <= max_len:
                words.add(w)
    return words


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

COMMON_FREQS = {
    'the': 5.0, 'be': 4.5, 'to': 4.7, 'of': 4.7, 'and': 4.6, 'a': 4.8,
    'in': 4.5, 'that': 4.2, 'have': 4.1, 'i': 4.5, 'it': 4.3, 'for': 4.3,
    'not': 4.1, 'on': 4.2, 'with': 4.1, 'he': 4.1, 'as': 4.0, 'you': 4.2,
    'do': 3.9, 'at': 4.0, 'this': 4.1, 'but': 3.9, 'his': 3.9, 'by': 3.9,
    'from': 3.8, 'they': 3.9, 'we': 3.9, 'say': 3.5, 'her': 3.7, 'she': 3.7,
    'or': 3.8, 'an': 3.8, 'will': 3.7, 'my': 3.7, 'one': 3.7, 'all': 3.7,
    'would': 3.5, 'there': 3.6, 'their': 3.5, 'what': 3.6, 'so': 3.6,
    'up': 3.5, 'out': 3.5, 'if': 3.6, 'about': 3.4, 'who': 3.4,
    'get': 3.4, 'which': 3.3, 'go': 3.4, 'me': 3.5, 'when': 3.4,
    'make': 3.3, 'can': 3.5, 'like': 3.3, 'time': 3.3, 'no': 3.5,
    'just': 3.2, 'him': 3.3, 'know': 3.3, 'take': 3.2, 'people': 3.1,
    'into': 3.2, 'year': 3.1, 'your': 3.3, 'good': 3.1, 'some': 3.2,
    'could': 3.1, 'them': 3.2, 'see': 3.1, 'other': 3.1, 'than': 3.1,
    'then': 3.1, 'now': 3.2, 'look': 3.0, 'only': 3.1, 'come': 3.1,
    'its': 3.1, 'over': 3.0, 'think': 3.0, 'also': 3.0, 'back': 3.0,
    'after': 3.0, 'use': 3.0, 'two': 3.0, 'how': 3.1, 'our': 3.1,
    'work': 3.0, 'first': 3.0, 'well': 3.0, 'way': 3.0, 'even': 3.0,
    'new': 3.1, 'want': 2.9, 'because': 2.9, 'any': 3.0, 'these': 2.9,
    'give': 2.9, 'day': 3.0, 'most': 2.9, 'us': 3.1,
    'eye': 2.7, 'eyes': 2.7, 'ere': 2.2, 'ever': 2.8, 'every': 2.8,
    'here': 3.0, 'where': 3.0, 'were': 3.1, 'are': 3.5, 'ore': 2.3,
    'was': 3.8, 'has': 3.3, 'had': 3.3, 'been': 3.2, 'did': 3.1,
    'set': 2.9, 'let': 2.9, 'yet': 2.8, 'may': 3.0, 'must': 2.9,
    'old': 2.9, 'each': 2.8, 'tell': 2.8, 'does': 2.8, 'own': 3.0,
    'too': 3.0, 'more': 3.2, 'very': 3.0, 'made': 3.0, 'find': 2.8,
    'found': 2.8, 'hand': 2.8, 'long': 2.9, 'great': 2.8, 'help': 2.7,
    'through': 2.8, 'much': 2.9, 'before': 2.9, 'line': 2.7,
    'right': 2.8, 'still': 2.8, 'name': 2.8, 'world': 2.8,
    'life': 2.8, 'left': 2.7, 'three': 2.7, 'end': 2.8,
    'keep': 2.7, 'never': 2.8, 'last': 2.8, 'head': 2.7,
    'need': 2.8, 'house': 2.6, 'light': 2.7, 'home': 2.7,
    'side': 2.7, 'night': 2.7, 'away': 2.7, 'small': 2.6,
    'place': 2.7, 'under': 2.7, 'turn': 2.7, 'few': 2.8,
    'open': 2.7, 'seem': 2.6, 'while': 2.8, 'being': 2.7,
    'same': 2.7, 'another': 2.6, 'off': 2.9, 'run': 2.7,
    'fire': 2.6, 'war': 2.7, 'why': 2.9, 'try': 2.8, 'men': 2.7,
    'man': 2.9, 'child': 2.5, 'children': 2.5, 'high': 2.7,
    'real': 2.6, 'point': 2.7, 'part': 2.7, 'kind': 2.6,
    'leave': 2.6, 'move': 2.6, 'live': 2.7, 'love': 2.7, 'gave': 2.6,
    'power': 2.6, 'death': 2.5, 'force': 2.6, 'truth': 2.5,
    'peace': 2.5, 'hope': 2.6, 'word': 2.7, 'true': 2.7,
    'face': 2.7, 'game': 2.5, 'feel': 2.7, 'fear': 2.5,
    'free': 2.6, 'age': 2.6, 'best': 2.7, 'god': 2.6,
    'close': 2.6, 'dark': 2.5, 'once': 2.7, 'done': 2.7,
    'both': 2.7, 'half': 2.6, 'hard': 2.6, 'land': 2.6,
    'air': 2.6, 'far': 2.8, 'ask': 2.7, 'sure': 2.6,
    'water': 2.5, 'earth': 2.5, 'soul': 2.4, 'human': 2.4,
    'star': 2.4, 'key': 2.5, 'begin': 2.4, 'deep': 2.4,
    'stone': 2.4, 'sacred': 2.2, 'chosen': 2.2, 'oracle': 2.1,
    'relic': 2.0, 'ancient': 2.3, 'reclaim': 2.0, 'awaken': 2.0,
    'believe': 2.3, 'protect': 2.2, 'defend': 2.2, 'honor': 2.3,
    'shield': 2.2, 'blade': 2.1, 'forge': 2.1, 'seek': 2.4,
    'rise': 2.4, 'fall': 2.6, 'stand': 2.5, 'hold': 2.6,
}


def word_score(word):
    base = COMMON_FREQS.get(word, 1.0 + len(word) * 0.2)
    # Bonus for word length: longer words are much more meaningful
    # in a cipher context (less likely to be noise)
    length_bonus = len(word) * 0.5
    return base + length_bonus


# ---------------------------------------------------------------------------
# Pre-index: for each word length and each position in the sequence,
# which dictionary words are compatible with the glyph pattern?
# ---------------------------------------------------------------------------

def word_matches_pattern(word, start_pos):
    """
    Check if `word` (lowercase) is compatible with GLYPH_SEQUENCE at
    positions [start_pos .. start_pos+len(word)-1], considering only
    the KNOWN_MAPPING constraints and the structural constraint that
    same glyphs must map to same letters (and different glyphs to
    different letters).

    Returns a dict of {glyph_id: letter} implied by this placement,
    or None if incompatible.
    """
    implied = {}
    reverse = {}  # letter -> glyph_id (to check bijectivity)

    for i, ch in enumerate(word):
        glyph = GLYPH_SEQUENCE[start_pos + i]

        # Check known mappings
        if glyph in KNOWN_MAPPING:
            if ch != KNOWN_MAPPING[glyph]:
                return None
            continue

        # Check consistency: same glyph -> same letter
        if glyph in implied:
            if implied[glyph] != ch:
                return None
        else:
            # Check reverse: same letter -> same glyph (bijectivity)
            if ch in reverse:
                if reverse[ch] != glyph:
                    return None
            # Also check against known mapping values
            if ch in KNOWN_MAPPING.values() and glyph not in KNOWN_MAPPING:
                return None
            implied[glyph] = ch
            reverse[ch] = glyph

    return implied


def build_word_index(dictionary):
    """
    For each starting position in the sequence, find all dictionary words
    that could be placed there (matching the glyph pattern).
    Returns dict: start_pos -> list of (word, implied_mapping).
    """
    index = defaultdict(list)

    for start_pos in range(SEQ_LEN):
        max_len = SEQ_LEN - start_pos
        for word in dictionary:
            wlen = len(word)
            if wlen > max_len:
                continue
            mapping = word_matches_pattern(word, start_pos)
            if mapping is not None:
                index[start_pos].append((word, mapping))

    return index


# ---------------------------------------------------------------------------
# Solver: recursive word placement
# ---------------------------------------------------------------------------

def solve(word_index):
    """
    Recursively place words starting at position 0, building up a
    consistent glyph mapping. Each recursive call tries all compatible
    words at the current position.
    """
    results = []
    stats = {'calls': 0, 'found': 0}

    def is_compatible(current_mapping, new_mapping):
        """Check if new_mapping is consistent with current_mapping (bijective)."""
        # Build reverse of current mapping
        reverse = {v: k for k, v in current_mapping.items()}

        for glyph, letter in new_mapping.items():
            if glyph in current_mapping:
                if current_mapping[glyph] != letter:
                    return False
            else:
                # New glyph: check letter isn't already used by another glyph
                if letter in reverse and reverse[letter] != glyph:
                    return False
        return True

    def merge_mapping(current_mapping, new_mapping):
        merged = dict(current_mapping)
        merged.update(new_mapping)
        return merged

    def backtrack(pos, mapping, words, word_count, short_count):
        stats['calls'] += 1

        if stats['calls'] % 5_000_000 == 0:
            print(f"  [{stats['calls']:,} calls, {stats['found']} results so far]")

        if pos == SEQ_LEN:
            # Complete segmentation found
            avg_len = SEQ_LEN / word_count
            longest = max(len(w) for w in words)
            long_words = sum(1 for w in words if len(w) >= 4)
            if (avg_len >= MIN_AVG_WORD_LEN
                    and short_count <= MAX_SHORT_WORDS
                    and longest >= MIN_LONGEST_WORD
                    and long_words >= MIN_LONG_WORDS):
                score = sum(word_score(w) for w in words)
                results.append((score, list(words), mapping.copy()))
                stats['found'] += 1
                if stats['found'] <= 20 or stats['found'] % 500 == 0:
                    print(f"  FOUND #{stats['found']}: \"{' '.join(words)}\" "
                          f"(score={score:.1f})")
            return

        if word_count >= MAX_WORDS:
            return  # Too many words already

        remaining = SEQ_LEN - pos
        remaining_budget = MAX_WORDS - word_count
        # If remaining characters can't be covered even with max-length words,
        # or if minimum avg length can't be met, prune
        if remaining_budget <= 0:
            return

        candidates = word_index.get(pos, [])
        for word, implied in candidates:
            wlen = len(word)
            new_short = short_count + (1 if wlen <= 2 else 0)
            if new_short > MAX_SHORT_WORDS:
                continue
            new_word_count = word_count + 1
            # Check: can remaining chars after this word still form valid words?
            chars_after = SEQ_LEN - pos - wlen
            words_left = MAX_WORDS - new_word_count
            if chars_after > 0 and words_left <= 0:
                continue

            if is_compatible(mapping, implied):
                merged = merge_mapping(mapping, implied)
                words.append(word)
                backtrack(pos + wlen, merged, words, new_word_count, new_short)
                words.pop()

    print("Starting dictionary-driven search...")
    print("-" * 70)
    start = time.time()

    backtrack(0, {}, [], 0, 0)

    elapsed = time.time() - start
    print("-" * 70)
    print(f"Search complete in {elapsed:.1f}s")
    print(f"  Recursive calls: {stats['calls']:,}")
    print(f"  Results found:   {stats['found']}")
    print()

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("HuragokForce2 — Substitution Cipher Solver")
    print("=" * 70)
    print()
    print("Glyph sequence: " + ' '.join(GLYPH_SEQUENCE))
    print(f"String length:  {SEQ_LEN}")
    print(f"Known mapping:  {KNOWN_MAPPING}")
    print()

    print("Loading dictionary...")
    dictionary = load_dictionary()
    print(f"  {len(dictionary):,} words loaded.")
    print()

    print("Building word index (matching words to glyph patterns)...")
    word_index = build_word_index(dictionary)
    total_candidates = sum(len(v) for v in word_index.values())
    print(f"  {total_candidates:,} word-position candidates across {len(word_index)} positions.")
    for pos in sorted(word_index):
        print(f"    pos {pos:2d}: {len(word_index[pos]):,} candidate words")
    print()

    results = solve(word_index)

    if not results:
        print("No valid segmentations found.")
        return

    # Deduplicate and sort
    seen = set()
    unique = []
    for score, words, mapping in results:
        key = ' '.join(words)
        if key not in seen:
            seen.add(key)
            unique.append((score, words, mapping))
    unique.sort(key=lambda r: -r[0])

    # Write all results to file
    outpath = Path(__file__).parent / 'results_no_e.txt'
    with open(outpath, 'w') as f:
        f.write(f"HuragokForce2 Results — {len(unique)} unique segmentations\n")
        f.write("=" * 70 + "\n\n")
        for i, (score, words, mapping) in enumerate(unique):
            segmented = ' '.join(words)
            raw = ''
            for g in GLYPH_SEQUENCE:
                if g in KNOWN_MAPPING:
                    raw += KNOWN_MAPPING[g].upper()
                elif g in mapping:
                    raw += mapping[g].upper()
                else:
                    raw += '?'
            glyph_map = ', '.join(f"{g}={mapping[g].upper()}" for g in sorted(mapping))
            f.write(f"#{i+1:4d}  score={score:6.1f}  \"{segmented}\"\n")
            f.write(f"       raw={raw}  [{glyph_map}]\n\n")
    print(f"All results saved to {outpath}")

    print(f"\nTop {min(TOP_N, len(unique))} results (of {len(unique)} unique):")
    print("=" * 70)
    for i, (score, words, mapping) in enumerate(unique[:TOP_N]):
        segmented = ' '.join(words)
        raw = ''
        for g in GLYPH_SEQUENCE:
            if g in KNOWN_MAPPING:
                raw += KNOWN_MAPPING[g].upper()
            elif g in mapping:
                raw += mapping[g].upper()
            else:
                raw += '?'
        glyph_map = ', '.join(f"{g}={mapping[g].upper()}" for g in sorted(mapping))
        print(f"  #{i+1:3d}  score={score:6.1f}  \"{segmented}\"")
        print(f"        raw={raw}  [{glyph_map}]")
        print()


if __name__ == '__main__':
    main()
