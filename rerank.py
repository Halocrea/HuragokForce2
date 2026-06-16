#!/usr/bin/env python3
"""
Re-rank solver results by phrase coherence using bigram probabilities.

Reads results.txt (or a specified file), scores each phrase by how likely
its word transitions are in natural English, and outputs a re-ranked list.

The bigram model is a simple log-probability table of common word pairs.
Words not in the table get a small backoff score. The coherence score is
the average bigram log-probability across all consecutive word pairs.
"""

import sys
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Bigram log-probabilities (higher = more natural transition)
#
# These approximate how commonly word B follows word A in English text.
# Scale: 0 = very common pair, -1 = plausible, -2 = unusual, -3 = weird
# ---------------------------------------------------------------------------

BIGRAMS = {
    # Determiners -> nouns/adjectives
    ('the', 'end'): -0.3, ('the', 'one'): -0.5, ('the', 'way'): -0.5,
    ('the', 'time'): -0.5, ('the', 'world'): -0.6, ('the', 'first'): -0.5,
    ('the', 'last'): -0.5, ('the', 'same'): -0.5, ('the', 'other'): -0.5,
    ('the', 'new'): -0.6, ('the', 'old'): -0.6, ('the', 'great'): -0.6,
    ('the', 'right'): -0.6, ('the', 'best'): -0.6, ('the', 'only'): -0.6,
    ('the', 'dark'): -0.7, ('the', 'light'): -0.7, ('the', 'truth'): -0.7,
    ('the', 'night'): -0.7, ('the', 'land'): -0.7, ('the', 'fire'): -0.7,
    ('the', 'door'): -0.7, ('the', 'need'): -0.8, ('the', 'name'): -0.7,
    ('a', 'new'): -0.5, ('a', 'long'): -0.6, ('a', 'great'): -0.6,
    ('a', 'good'): -0.6, ('a', 'small'): -0.7, ('a', 'need'): -0.7,
    ('a', 'seed'): -1.0, ('a', 'deed'): -1.0, ('a', 'feed'): -1.2,
    ('a', 'weed'): -1.2, ('a', 'reed'): -1.2,

    # Pronouns -> verbs
    ('i', 'am'): -0.2, ('i', 'was'): -0.3, ('i', 'have'): -0.3,
    ('i', 'had'): -0.4, ('i', 'will'): -0.3, ('i', 'would'): -0.4,
    ('i', 'can'): -0.4, ('i', 'need'): -0.3, ('i', 'know'): -0.4,
    ('i', 'think'): -0.4, ('i', 'feel'): -0.5, ('i', 'see'): -0.5,
    ('i', 'want'): -0.4, ('i', 'did'): -0.5, ('i', 'do'): -0.5,
    ('i', 'must'): -0.5, ('i', 'fear'): -0.7, ('i', 'seek'): -0.8,
    ('i', 'come'): -0.7, ('i', 'found'): -0.6,
    ('he', 'was'): -0.2, ('he', 'had'): -0.3, ('he', 'is'): -0.3,
    ('he', 'said'): -0.3, ('he', 'did'): -0.5,
    ('she', 'was'): -0.2, ('she', 'had'): -0.3, ('she', 'is'): -0.3,
    ('she', 'said'): -0.3,
    ('we', 'are'): -0.2, ('we', 'were'): -0.3, ('we', 'have'): -0.3,
    ('we', 'need'): -0.4, ('we', 'will'): -0.4, ('we', 'can'): -0.5,
    ('we', 'must'): -0.5,
    ('they', 'are'): -0.2, ('they', 'were'): -0.3, ('they', 'have'): -0.3,
    ('they', 'will'): -0.4, ('they', 'need'): -0.5,
    ('it', 'is'): -0.2, ('it', 'was'): -0.2, ('it', 'will'): -0.4,

    # Verb -> complement patterns
    ('need', 'to'): -0.3, ('need', 'a'): -0.5, ('need', 'the'): -0.5,
    ('need', 'more'): -0.6, ('need', 'help'): -0.6, ('need', 'not'): -0.7,
    ('need', 'were'): -2.5,  # grammatically weird
    ('need', 'here'): -1.8,
    ('need', 'mere'): -2.8,
    ('need', 'sere'): -3.0,
    ('needs', 'eye'): -2.5,
    ('needs', 'ere'): -3.0,
    ('needs', 'eve'): -2.5,
    ('needs', 'ewe'): -2.5,
    ('needs', 'eke'): -3.0,
    ('needy', 'ere'): -2.5,
    ('needy', 'eve'): -2.5,
    ('needy', 'ewe'): -2.5,
    ('needy', 'eye'): -2.0,
    ('have', 'a'): -0.3, ('have', 'the'): -0.4, ('have', 'been'): -0.3,
    ('have', 'to'): -0.4, ('have', 'not'): -0.4,
    ('come', 'to'): -0.4, ('come', 'from'): -0.4, ('come', 'here'): -0.4,
    ('come', 'back'): -0.5,
    ('see', 'the'): -0.4, ('see', 'it'): -0.5, ('see', 'here'): -0.7,
    ('see', 'there'): -0.6,
    ('find', 'the'): -0.4, ('find', 'a'): -0.5,
    ('know', 'the'): -0.5, ('know', 'that'): -0.4, ('know', 'what'): -0.5,
    ('take', 'the'): -0.4, ('take', 'a'): -0.5,
    ('make', 'the'): -0.5, ('make', 'a'): -0.5, ('make', 'it'): -0.5,
    ('give', 'the'): -0.5, ('give', 'a'): -0.6, ('give', 'me'): -0.5,
    ('tell', 'the'): -0.5, ('tell', 'me'): -0.4,
    ('keep', 'the'): -0.5, ('keep', 'it'): -0.6,
    ('hold', 'the'): -0.5,
    ('open', 'the'): -0.4, ('open', 'a'): -0.6,

    # noticed / observed patterns
    ('noticed', 'i'): -1.2,  # unusual — "noticed I" needs context
    ('noticed', 'the'): -0.5, ('noticed', 'a'): -0.6,
    ('noticed', 'that'): -0.4, ('noticed', 'it'): -0.6,

    # Adjective -> noun
    ('old', 'man'): -0.6, ('dark', 'night'): -0.7,
    ('great', 'power'): -0.8, ('deep', 'water'): -0.9,

    # Common transitions
    ('not', 'the'): -0.5, ('not', 'a'): -0.5, ('not', 'be'): -0.5,
    ('not', 'to'): -0.6, ('not', 'yet'): -0.7, ('not', 'here'): -0.7,
    ('not', 'sleds'): -3.0,
    ('in', 'the'): -0.2, ('in', 'a'): -0.4,
    ('of', 'the'): -0.2, ('of', 'a'): -0.4,
    ('to', 'the'): -0.3, ('to', 'be'): -0.3, ('to', 'a'): -0.5,
    ('on', 'the'): -0.3, ('on', 'a'): -0.5,
    ('for', 'the'): -0.3, ('for', 'a'): -0.4,
    ('with', 'the'): -0.3, ('with', 'a'): -0.4,
    ('from', 'the'): -0.3, ('from', 'a'): -0.5,
    ('at', 'the'): -0.3,
    ('by', 'the'): -0.4,
    ('is', 'the'): -0.4, ('is', 'a'): -0.4, ('is', 'not'): -0.4,
    ('was', 'the'): -0.4, ('was', 'a'): -0.4, ('was', 'not'): -0.4,
    ('are', 'the'): -0.5, ('are', 'not'): -0.5,
    ('were', 'the'): -0.5, ('were', 'not'): -0.5,
    ('all', 'the'): -0.4, ('all', 'of'): -0.5,
    ('one', 'of'): -0.4, ('one', 'who'): -0.6,
    ('out', 'of'): -0.3, ('out', 'the'): -0.6,

    # "then" patterns
    ('then', 'the'): -0.5, ('then', 'he'): -0.5, ('then', 'she'): -0.5,
    ('then', 'i'): -0.5, ('then', 'we'): -0.6, ('then', 'they'): -0.6,
    ('then', 'stayed'): -1.5, ('then', 'staked'): -2.0,
    ('then', 'staved'): -2.0, ('then', 'staled'): -2.5,
    ('then', 'staged'): -1.3,

    # "one" patterns
    ('one', 'floated'): -1.8, ('one', 'gloated'): -1.8,
    ('one', 'shoaled'): -2.5, ('one', 'spoiled'): -1.3,

    # "she" patterns
    ('she', 'rustled'): -1.5, ('she', 'posited'): -1.5,

    # "her" patterns
    ('her', 'packed'): -1.5, ('her', 'backed'): -1.5,
    ('her', 'lacked'): -1.5, ('her', 'tacked'): -1.8,
    ('her', 'jacked'): -1.8, ('her', 'magnet'): -1.8,
    ('her', 'tabled'): -1.5, ('her', 'fabled'): -1.5,
    ('her', 'gabled'): -2.0, ('her', 'cabled'): -2.0,
    ('her', 'tabued'): -2.5,

    # "_ed a" patterns
    ('floated', 'a'): -0.6, ('coated', 'a'): -0.7,
    ('boated', 'a'): -1.5, ('loafed', 'a'): -1.5,
    ('soaked', 'a'): -0.8, ('coaxed', 'a'): -1.0,
    ('coaled', 'a'): -2.0, ('foaled', 'a'): -2.0,
    ('foamed', 'a'): -1.2, ('hoaxed', 'a'): -1.2,
    ('stayed', 'a'): -1.0, ('staged', 'a'): -0.8,
    ('spoiled', 'i'): -1.8,

    # "planet a" etc
    ('planet', 'a'): -1.5, ('lies', 'planet'): -2.0,

    # Ending patterns (last word in phrase — no bigram to score)
    # These handle the X->end transition implicitly via the backoff

    # Bad/nonsensical transitions (heavy penalty)
    ('sleds', 'need'): -2.0, ('sleds', 'needy'): -2.2,
    ('etc', 'meet'): -2.5, ('etc', 'meets'): -2.5, ('etc', 'feet'): -2.5,
    ('caskets', 'wee'): -2.5,
    ('gaskets', 'wee'): -2.5, ('baskets', 'wee'): -2.5,
    ('bashed', 'steed'): -2.0, ('cashed', 'steed'): -2.0,
    ('mashed', 'steed'): -2.0, ('lashed', 'steed'): -2.0,
    ('masked', 'steed'): -2.0, ('basked', 'steed'): -2.0,

    # Creeds/breeds/greets + eye — strange but not impossible
    ('creeds', 'eye'): -2.0, ('breeds', 'eye'): -2.0,
    ('greets', 'eye'): -2.3,

    # "steed were" etc.
    ('steed', 'were'): -2.0, ('steed', 'here'): -2.0,
}

# Backoff score for unknown bigrams — based on part-of-speech heuristics
# We categorize the first word to give slightly better backoff estimates
FUNCTION_WORDS = {
    'the', 'a', 'an', 'i', 'he', 'she', 'we', 'they', 'it', 'you',
    'me', 'him', 'her', 'us', 'them', 'my', 'his', 'our', 'their',
    'this', 'that', 'these', 'those', 'is', 'am', 'are', 'was', 'were',
    'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'shall', 'should', 'can', 'could', 'may', 'might',
    'must', 'not', 'no', 'if', 'but', 'and', 'or', 'so', 'yet',
    'for', 'of', 'in', 'on', 'at', 'to', 'by', 'with', 'from',
    'up', 'out', 'off', 'all', 'each', 'every', 'both', 'few',
    'more', 'most', 'other', 'some', 'any', 'many', 'much',
    'than', 'then', 'when', 'where', 'here', 'there', 'now',
    'how', 'what', 'which', 'who', 'whom', 'why',
}

# Default backoff: function word -> content word is plausible (-1.2),
# content word -> content word is less likely (-1.8),
# content word -> function word is moderate (-1.5).
def backoff_score(w1, w2):
    if w1 in FUNCTION_WORDS and w2 not in FUNCTION_WORDS:
        return -1.2
    if w1 not in FUNCTION_WORDS and w2 in FUNCTION_WORDS:
        return -1.5
    if w1 in FUNCTION_WORDS and w2 in FUNCTION_WORDS:
        return -1.3
    # content -> content
    return -1.8


def bigram_score(w1, w2):
    """Score the transition from w1 to w2. Higher = more natural."""
    key = (w1.lower(), w2.lower())
    if key in BIGRAMS:
        return BIGRAMS[key]
    return backoff_score(w1.lower(), w2.lower())


def phrase_coherence(words):
    """
    Score a phrase's coherence as the average bigram log-probability.
    Returns (coherence_score, [individual_bigram_scores]).
    A single-word phrase gets score 0 (neutral).
    """
    if len(words) <= 1:
        return 0.0, []

    scores = []
    for i in range(len(words) - 1):
        scores.append(bigram_score(words[i], words[i + 1]))

    return sum(scores) / len(scores), scores


# ---------------------------------------------------------------------------
# Parse results file
# ---------------------------------------------------------------------------

def parse_results(filepath):
    """Parse a results.txt file into a list of (original_score, words, raw, mapping_str)."""
    results = []
    lines = Path(filepath).read_text().splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        # Match lines like: #   1  score=  27.3  "the noticed i need were"
        m = re.match(r'#\s*\d+\s+score=\s*([\d.]+)\s+"(.+)"', line)
        if m:
            score = float(m.group(1))
            phrase = m.group(2)
            words = phrase.split()
            # Next line has raw and mapping
            raw_line = lines[i + 1] if i + 1 < len(lines) else ''
            rm = re.match(r'\s+raw=(\S+)\s+\[(.+)\]', raw_line)
            raw = rm.group(1) if rm else ''
            mapping_str = rm.group(2) if rm else ''
            results.append((score, words, raw, mapping_str))
            i += 2
        else:
            i += 1

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'results.txt'
    p = Path(filepath)
    if not p.exists():
        print(f"File not found: {filepath}", file=sys.stderr)
        print(f"Usage: python3 rerank.py [results_file]", file=sys.stderr)
        sys.exit(1)

    print(f"Reading results from {filepath}...")
    results = parse_results(filepath)
    print(f"  {len(results)} results parsed.")
    print()

    # Compute combined score: original_score + coherence_weight * coherence
    # Coherence is on a negative scale (0 = best, -3 = worst), so we scale it
    COHERENCE_WEIGHT = 5.0  # how much coherence matters vs word quality

    ranked = []
    for orig_score, words, raw, mapping_str in results:
        coherence, bigram_details = phrase_coherence(words)
        combined = orig_score + COHERENCE_WEIGHT * coherence
        ranked.append((combined, orig_score, coherence, words, raw, mapping_str, bigram_details))

    ranked.sort(key=lambda r: -r[0])

    # Output
    top_n = 60
    print(f"Top {min(top_n, len(ranked))} results re-ranked by coherence:")
    print("=" * 78)
    for i, (combined, orig, coherence, words, raw, mapping_str, bigram_details) in enumerate(ranked[:top_n]):
        phrase = ' '.join(words)
        bigram_str = '  '.join(
            f"{words[j]}->{words[j+1]}={bigram_details[j]:+.1f}"
            for j in range(len(bigram_details))
        )
        print(f"  #{i+1:3d}  combined={combined:6.1f}  (words={orig:.1f}, coherence={coherence:+.2f})")
        print(f"        \"{phrase}\"")
        print(f"        raw={raw}  [{mapping_str}]")
        print(f"        bigrams: {bigram_str}")
        print()

    # Save to file
    outpath = p.parent / f'reranked_{p.name}'
    with open(outpath, 'w') as f:
        f.write(f"Re-ranked results from {filepath}\n")
        f.write(f"Coherence weight: {COHERENCE_WEIGHT}\n")
        f.write("=" * 78 + "\n\n")
        for i, (combined, orig, coherence, words, raw, mapping_str, bigram_details) in enumerate(ranked):
            phrase = ' '.join(words)
            bigram_str = '  '.join(
                f"{words[j]}->{words[j+1]}={bigram_details[j]:+.1f}"
                for j in range(len(bigram_details))
            )
            f.write(f"#{i+1:5d}  combined={combined:6.1f}  (words={orig:.1f}, coherence={coherence:+.2f})\n")
            f.write(f"        \"{phrase}\"\n")
            f.write(f"        raw={raw}  [{mapping_str}]\n")
            f.write(f"        bigrams: {bigram_str}\n\n")
    print(f"All re-ranked results saved to {outpath}")


if __name__ == '__main__':
    main()
