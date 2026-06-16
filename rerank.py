#!/usr/bin/env python3
"""
Re-rank solver results by phrase coherence using a KenLM language model.

Reads results.txt (or a specified file), scores each phrase using a 3-gram
language model trained on the Brown corpus, and outputs a re-ranked list.

Usage:
    # From the venv (has kenlm installed):
    source venv/bin/activate
    python3 rerank.py [results_file]
"""

import sys
import re
from pathlib import Path

import kenlm

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_PATH = Path(__file__).parent / 'brown_3gram.bin'
COHERENCE_WEIGHT = 1.0  # how much LM score matters vs word quality score


# ---------------------------------------------------------------------------
# Language model scoring
# ---------------------------------------------------------------------------

def load_model():
    if not MODEL_PATH.exists():
        print(f"Language model not found at {MODEL_PATH}", file=sys.stderr)
        print("See README for instructions on building the model.", file=sys.stderr)
        sys.exit(1)
    return kenlm.Model(str(MODEL_PATH))


def phrase_coherence(model, words):
    """
    Score a phrase using the KenLM language model.
    Returns the full sentence log-probability (log10).
    More negative = less likely in natural English.
    """
    sentence = ' '.join(w.lower() for w in words)
    return model.score(sentence, bos=True, eos=True)


def per_word_scores(model, words):
    """Get per-word log-prob contributions for display."""
    sentence = ' '.join(w.lower() for w in words)
    return list(model.full_scores(sentence, bos=True, eos=True))


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
        m = re.match(r'#\s*\d+\s+score=\s*([\d.]+)\s+"(.+)"', line)
        if m:
            score = float(m.group(1))
            phrase = m.group(2)
            words = phrase.split()
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

    print(f"Loading language model from {MODEL_PATH}...")
    model = load_model()
    print(f"  Model order: {model.order}")
    print()

    print(f"Reading results from {filepath}...")
    results = parse_results(filepath)
    print(f"  {len(results)} results parsed.")
    print()

    ranked = []
    for orig_score, words, raw, mapping_str in results:
        lm_score = phrase_coherence(model, words)
        # Normalize LM score by number of words for fair comparison
        # (longer phrases naturally get lower log-probs)
        norm_lm = lm_score / len(words) if words else 0
        combined = orig_score + COHERENCE_WEIGHT * norm_lm
        ranked.append((combined, orig_score, lm_score, norm_lm, words, raw, mapping_str))

    ranked.sort(key=lambda r: -r[0])

    # Output
    top_n = 60
    print(f"Top {min(top_n, len(ranked))} results re-ranked by KenLM coherence:")
    print("=" * 78)
    for i, (combined, orig, lm, norm_lm, words, raw, mapping_str) in enumerate(ranked[:top_n]):
        phrase = ' '.join(words)
        # Get per-word breakdown
        scores = per_word_scores(model, words)
        word_details = []
        for (log_prob, ngram_len, oov), w in zip(scores, words):
            oov_marker = " [OOV]" if oov else ""
            word_details.append(f"{w}={log_prob:+.1f}/{ngram_len}g{oov_marker}")
        detail_str = '  '.join(word_details)

        print(f"  #{i+1:3d}  combined={combined:6.1f}  (words={orig:.1f}, lm={lm:.1f}, lm/word={norm_lm:.2f})")
        print(f"        \"{phrase}\"")
        print(f"        raw={raw}  [{mapping_str}]")
        print(f"        per-word: {detail_str}")
        print()

    # Save to file
    outpath = p.parent / f'reranked_{p.name}'
    with open(outpath, 'w') as f:
        f.write(f"Re-ranked results from {filepath}\n")
        f.write(f"Language model: {MODEL_PATH.name} (order {model.order})\n")
        f.write(f"Coherence weight: {COHERENCE_WEIGHT}\n")
        f.write("=" * 78 + "\n\n")
        for i, (combined, orig, lm, norm_lm, words, raw, mapping_str) in enumerate(ranked):
            phrase = ' '.join(words)
            scores = per_word_scores(model, words)
            word_details = []
            for (log_prob, ngram_len, oov), w in zip(scores, words):
                oov_marker = " [OOV]" if oov else ""
                word_details.append(f"{w}={log_prob:+.1f}/{ngram_len}g{oov_marker}")
            detail_str = '  '.join(word_details)

            f.write(f"#{i+1:5d}  combined={combined:6.1f}  (words={orig:.1f}, lm={lm:.1f}, lm/word={norm_lm:.2f})\n")
            f.write(f"        \"{phrase}\"\n")
            f.write(f"        raw={raw}  [{mapping_str}]\n")
            f.write(f"        per-word: {detail_str}\n\n")
    print(f"All re-ranked results saved to {outpath}")


if __name__ == '__main__':
    main()
