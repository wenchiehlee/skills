"""
align_transcript_to_fin.py  v6  — Landmark-based alignment
Usage: python align_transcript_to_fin.py <stem>

Background:
  For TSMC Q1-2026, Whisper large-v3 produced a catastrophic hallucination:
  the entire Prepared Remarks section was replaced with Q4-2025 financial data.
  Word-level alignment between FIN.srt and ASP therefore fails for ~40% of the
  call.  The solution is landmark-based alignment:

Strategy:
  1. Find structural transition phrases (greetings, speaker hand-offs) that appear
     verbatim in BOTH FIN.srt and the AlphaSpread transcript.
  2. Use these as anchors that pin specific FIN timestamps to specific ASP positions.
  3. Between consecutive anchors distribute ASP tokens proportionally over the FIN
     segments in that time span.
  4. Output one GT.srt line per FIN segment: FIN timestamp + proportional ASP text.

Landmark phrases searched (case-insensitive, partial match OK):
  - "Thank you" + "Jeff"      -> start of CFO remarks
  - "Thank you" + "Wendell"   -> start of CEO remarks
  - "concludes" + "prepared"  -> end of prepared remarks / start of Q&A

Handles two AlphaSpread transcript formats:
  Format A (old):  single uppercase letter / name / role header blocks
  Format B (new):  **Name** *(role)* markdown headers
"""

import re
import sys
import difflib
from pathlib import Path

WHISPER_DIR = Path(__file__).parent           # Mac-mini/mlx-api-server-whisper
MAC_MINI    = WHISPER_DIR.parent             # Mac-mini
IC_REPO     = MAC_MINI.parent / "InvestorConference"


# ── Parsers ────────────────────────────────────────────────────────────────────

def parse_fin(path: Path):
    """
    Return list of (ts_str, raw_text) from FIN.srt.
    Skips the [METADATA] block before the first '---' separator.
    """
    segs = []
    past_sep = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not past_sep:
            if line.strip() == "---":
                past_sep = True
            continue
        m = re.match(r"^\((\d+:\d+\.\d+)\)\s+(.*)", line)
        if m:
            text = m.group(2).strip()
            if text:
                segs.append((m.group(1), text))
    return segs


def parse_asp(path: Path) -> str:
    """
    Return flat plain text from *_alphaspread_transcript.md.
    Both transcript header formats are stripped.
    """
    txt = path.read_text(encoding="utf-8")

    # Remove [METADATA] block up to the first '---'
    txt = re.sub(r"\[METADATA\].*?---\s*\n", "", txt, flags=re.DOTALL)

    # Format A: single uppercase letter + name + role  (Q1-2026 style)
    #   J\nJeff Su\nexecutive\n
    txt = re.sub(
        r"^[A-Z]\n[^\n]+\n(?:executive|analyst|operator)\n",
        "",
        txt,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    # Format A-ext: name without single-letter prefix  (e.g. C.C. Wei\nexecutive\n)
    txt = re.sub(
        r"^[^\n]+\n(?:executive|analyst|operator)\n",
        "",
        txt,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    # Format B: **Name** *(role)*  (Q2–Q4 style markdown headers)
    txt = re.sub(r"^\*\*[^*]+\*\*\s*\*\([^)]+\)\*\s*\n", "", txt, flags=re.MULTILINE)

    # Bare "Operator" section header line
    txt = re.sub(r"^Operator\s*\n", "", txt, flags=re.MULTILINE)

    # Markdown headings  (## Prepared Remarks, etc.)
    txt = re.sub(r"^#{1,6}[^\n]*\n", "", txt, flags=re.MULTILINE)

    # Horizontal rules
    txt = re.sub(r"^---\s*\n", "", txt, flags=re.MULTILINE)

    # Collapse all whitespace to single spaces
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


# ── Normalization ──────────────────────────────────────────────────────────────

def norm(text: str):
    """Lowercase + strip non-alphanumeric → list of words for comparison."""
    return re.sub(r"[^a-z0-9]", " ", text.lower()).split()


# ── Landmark search ────────────────────────────────────────────────────────────

# Structural phrases that appear in both FIN and ASP as speaker-hand-off signals.
# Each entry is (label, fin_pattern, asp_pattern).
# Patterns are matched case-insensitively against the concatenated segment text.
_LANDMARKS = [
    # Q1-2026: "Thank you, Jeff. Good afternoon"  Q2-2025 FIN: "Thank you, Jeff." (no "good afternoon")
    ("wendell_start",  r"thank you.*jeff",
                       r"thank you.*jeff"),
    # Q1-2026/Q3-2025: "Thank you, Wendell. Good afternoon"
    # Q1-2025 FIN: "C.C. Thank you, Wendell." (no "good afternoon")
    # Q2-2025 FIN: phrase absent → skipped
    # Negative lookahead avoids analyst phrases like "thank you, CC, Wendell, and Jess"
    ("cc_start",       r"thank you.*wendell(?!,? and)",
                       r"thank you.*wendell"),
    # Q1-2026 FIN: "This concludes prepared statements"
    # Q2-2025 FIN: "Thank you, CC." (Jeff Su closing CC's remarks, right before Q&A)
    # Note: Q2-2025 lacks "good afternoon" after "Thank you, Wendell" so cc_start is skipped,
    # making qa_start the first (and only) boundary found.
    ("qa_start",       r"conclud.*prepared|thank you,? cc\.",
                       r"conclud.*prepared"),
]


def _find_fin_landmark(fin_segs, pattern):
    """
    Search fin_segs for the first segment whose text (or two adjacent segments
    concatenated) matches `pattern`.  Returns segment index or None.
    """
    pat = re.compile(pattern, re.IGNORECASE)
    for s in range(len(fin_segs)):
        window = " ".join(t for _, t in fin_segs[s: s + 3])
        if pat.search(window):
            return s
    return None


def _find_asp_landmark(asp_tokens, pattern):
    """
    Search a 50-token sliding window over asp_tokens for `pattern`.
    Returns the token index of the match start, or None.
    """
    pat = re.compile(pattern, re.IGNORECASE)
    for i in range(0, len(asp_tokens), 5):
        window = " ".join(asp_tokens[i: i + 60])
        if pat.search(window):
            # Refine to exact start within the window
            for j in range(i, min(i + 60, len(asp_tokens))):
                if pat.search(" ".join(asp_tokens[j: j + 20])):
                    return j
    return None


# ── Proportional distribution ─────────────────────────────────────────────────

def _distribute(fin_segs, s_lo, s_hi, asp_tokens, a_lo, a_hi):
    """
    Assign ASP tokens[a_lo:a_hi] to fin_segs[s_lo:s_hi] proportionally.
    Returns list of (ts_str, text) for those segments.
    """
    n_segs = s_hi - s_lo
    n_asp  = a_hi - a_lo
    result = []
    for k in range(n_segs):
        ts = fin_segs[s_lo + k][0]
        tok_start = a_lo + int(round(k * n_asp / n_segs))
        tok_end   = a_lo + int(round((k + 1) * n_asp / n_segs))
        tok_end   = max(tok_end, tok_start + 1)
        text = " ".join(asp_tokens[tok_start:tok_end]).strip()
        if text:
            result.append((ts, text))
        else:
            result.append((ts, fin_segs[s_lo + k][1]))  # fallback to FIN
    return result


# ── Main alignment ─────────────────────────────────────────────────────────────

def align(fin_segs, asp_text: str):
    """
    Align ASP text to FIN timestamps using structural landmark phrases.

    Steps:
      1. Find landmark transitions in FIN (segment indices) and ASP (token indices).
      2. Divide both into sections between consecutive landmarks.
      3. Within each section distribute ASP tokens proportionally over FIN segments.

    Returns list of (ts_str, text).
    """
    asp_tokens = asp_text.split()
    N_fin = len(fin_segs)
    N_asp = len(asp_tokens)

    # Discover landmarks
    fin_boundaries = [0]   # segment indices (inclusive start of each section)
    asp_boundaries = [0]   # token indices

    for label, fin_pat, asp_pat in _LANDMARKS:
        s_idx = _find_fin_landmark(fin_segs, fin_pat)
        a_idx = _find_asp_landmark(asp_tokens, asp_pat)
        if s_idx is not None and a_idx is not None:
            # Only accept if it advances both pointers monotonically
            if s_idx > fin_boundaries[-1] and a_idx > asp_boundaries[-1]:
                fin_boundaries.append(s_idx)
                asp_boundaries.append(a_idx)
                print(f"  Landmark [{label}]: FIN seg {s_idx} ({fin_segs[s_idx][0]}) "
                      f"-> ASP tok {a_idx} ({' '.join(asp_tokens[a_idx:a_idx+6])}...)")
            else:
                print(f"  Landmark [{label}]: skipped (non-monotone)")
        else:
            print(f"  Landmark [{label}]: not found "
                  f"(FIN={s_idx}, ASP={a_idx})")

    fin_boundaries.append(N_fin)
    asp_boundaries.append(N_asp)

    # Distribute ASP tokens across FIN segments section by section
    result = []
    for i in range(len(fin_boundaries) - 1):
        s_lo = fin_boundaries[i]
        s_hi = fin_boundaries[i + 1]
        a_lo = asp_boundaries[i]
        a_hi = asp_boundaries[i + 1]
        result.extend(_distribute(fin_segs, s_lo, s_hi, asp_tokens, a_lo, a_hi))

    return result


# ── Metadata helpers ───────────────────────────────────────────────────────────

def adapt_meta(fin_path: Path) -> str:
    """Copy METADATA block from FIN.srt and annotate it for GT use."""
    lines = []
    for line in fin_path.read_text(encoding="utf-8").splitlines():
        lines.append(line)
        if line.strip() == "---":
            break
    meta = "\n".join(lines)
    meta = re.sub(r"^(Provider:).*$",
                  r"\1 alphaspread+fin-align",
                  meta, flags=re.MULTILINE)
    meta = re.sub(r"^(Model:).*$",
                  r"\1 whisper-large-v3 (timestamps) + AlphaSpread (text)",
                  meta, flags=re.MULTILINE)
    meta = re.sub(r"^Model-Repo:.*\n",          "", meta, flags=re.MULTILINE)
    meta = re.sub(r"^Transcription-Time:.*\n",  "", meta, flags=re.MULTILINE)
    meta = re.sub(r"^RTF:.*\n",                 "", meta, flags=re.MULTILINE)
    meta = re.sub(r"\n{3,}", "\n", meta)
    return meta.strip()


def write_gt(path: Path, meta: str, segments):
    lines = [meta, ""]
    for ts, text in segments:
        lines.append(f"({ts}) {text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python align_transcript_to_fin.py <stem>")
        print("  stem example: 2330_2026_q1")
        sys.exit(1)

    stem      = sys.argv[1]
    stock_id  = stem.split("_")[0]
    stock_dir = IC_REPO / stock_id
    sandbox   = WHISPER_DIR / "whisper-sandbox"
    gt_dir    = WHISPER_DIR / "GroundTrue"

    fin_path = sandbox / f"{stem}_FIN.srt"
    if not fin_path.exists():
        fin_path = stock_dir / f"{stem}_FIN.srt"

    asp_path = stock_dir / f"{stem}_alphaspread_transcript.md"

    out_ic = stock_dir / f"{stem}_GT.srt"          # InvestorConference copy
    out_gt = gt_dir    / f"{stem}_GT.srt"          # mlx-api-server-whisper GroundTrue

    for p in (fin_path, asp_path):
        if not p.exists():
            sys.exit(f"ERROR: not found: {p}")

    print(f"FIN   : {fin_path}")
    print(f"ASP   : {asp_path}")
    print(f"OUT IC: {out_ic}")
    print(f"OUT GT: {out_gt}")

    fin_segs = parse_fin(fin_path)
    asp_text = parse_asp(asp_path)
    print(f"FIN segments : {len(fin_segs)}")
    print(f"ASP words    : {len(asp_text.split())}")

    print("Aligning …")
    segments = align(fin_segs, asp_text)
    print(f"GT segments  : {len(segments)}")

    meta = adapt_meta(fin_path)
    gt_dir.mkdir(parents=True, exist_ok=True)
    write_gt(out_ic, meta, segments)
    write_gt(out_gt, meta, segments)
    print(f"Written: {out_ic}")
    print(f"Written: {out_gt}")


if __name__ == "__main__":
    main()
