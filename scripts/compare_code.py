"""Compare Cold Movers with another code base, to check that nothing was copied from it.

Usage:  python -I scripts/compare_code.py /path/to/other/repository [/path/to/an/unrelated/baseline]

Read-only: the other repository is only read as text, none of its code is imported or run.
Four measures, printed as Markdown:
  1. identical lines (30+ characters, common one-word statements left out),
  2. the longest identical code stretches (20+ Python tokens, names and values kept),
  3. the share of Cold Movers' 25-token runs found there with every name and value masked
     (this catches copies whose variables were renamed), and the same share for a baseline,
  4. identical 8-word runs between Cold Movers' texts (Markdown, Python) and the other project's texts.
"""

import io
import keyword
import os
import re
import sys
import tokenize

OURS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = ("/.git", "__pycache__", "node_modules", "/data/")
GENERIC = re.compile(r"^(import |from \S+ import|if __name__|return None|else:|try:|except|#\s*noqa|pass$)")


def walk(root, exts):
    for d, _, fs in os.walk(root):
        if any(s in d + "/" for s in SKIP):
            continue
        for f in sorted(fs):
            if f.endswith(exts):
                yield os.path.join(d, f)


def our_code():
    return [p for p in walk(OURS, (".py",)) if "/docs/" not in p]


def tokens(path, mask):
    out = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(open(path, errors="ignore").read()).readline):
            if t.type == tokenize.NAME:
                out.append((t.string if keyword.iskeyword(t.string) or not mask else "ID", t.start[0]))
            elif t.type in (tokenize.NUMBER, tokenize.STRING):
                out.append(("LIT" if mask else t.string, t.start[0]))
            elif t.type == tokenize.OP:
                out.append((t.string, t.start[0]))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return out


def runs(path, k, mask):
    t = [a for a, _ in tokens(path, mask)]
    return {tuple(t[i:i + k]) for i in range(len(t) - k + 1)}


def identical_lines(other):
    theirs = {}
    for p in walk(other, (".py", ".ts", ".tsx", ".js", ".md")):
        for ln in open(p, errors="ignore"):
            n = re.sub(r"\s+", " ", ln.strip())
            if len(n) >= 30:
                theirs.setdefault(n, os.path.relpath(p, other))
    total, hits = 0, []
    for p in our_code():
        for i, ln in enumerate(open(p, errors="ignore"), 1):
            n = re.sub(r"\s+", " ", ln.strip())
            if len(n) >= 30 and not GENERIC.match(n):
                total += 1
                if n in theirs:
                    hits.append((os.path.relpath(p, OURS), i, n, theirs[n]))
    return total, hits


def longest_stretches(other, k=20):
    theirs = set()
    for p in walk(other, (".py",)):
        theirs |= runs(p, k, mask=False)
    segs = []
    for p in our_code():
        tl = tokens(p, mask=False)
        t = [a for a, _ in tl]
        cov = [False] * len(t)
        for i in range(len(t) - k + 1):
            if tuple(t[i:i + k]) in theirs:
                cov[i:i + k] = [True] * k
        i = 0
        while i < len(t):
            if cov[i]:
                j = i
                while j < len(t) and cov[j]:
                    j += 1
                segs.append((j - i, os.path.relpath(p, OURS), tl[i][1], tl[j - 1][1]))
                i = j
            else:
                i += 1
    return sorted(segs, reverse=True)


def masked_share(other, k=25):
    theirs = set()
    for p in walk(other, (".py",)):
        theirs |= runs(p, k, mask=True)
    tot = hit = 0
    for p in our_code():
        r = runs(p, k, mask=True)
        tot += len(r)
        hit += sum(s in theirs for s in r)
    return hit, tot


def text_runs(other, k=8):
    def words(path):
        return re.findall(r"[a-z0-9]+(?:['’][a-z]+)?", open(path, errors="ignore").read().lower())
    theirs = {}
    for p in walk(other, (".md", ".ts", ".tsx", ".html", ".py", ".txt")):
        w = words(p)
        for i in range(len(w) - k + 1):
            theirs.setdefault(tuple(w[i:i + k]), os.path.relpath(p, other))
    found = {}
    for p in walk(OURS, (".md", ".py")):
        if p.endswith("CODE_COMPARISON.md"):  # quotes the other project on purpose
            continue
        w = words(p)
        last = -10
        for i in range(len(w) - k + 1):
            g = tuple(w[i:i + k])
            if g in theirs:
                key = os.path.relpath(p, OURS)
                if i == last + 1 and found.get(key):
                    found[key][-1][0].append(w[i + k - 1])
                else:
                    found.setdefault(key, []).append((list(g), theirs[g]))
                last = i
    return found


def main():
    other = sys.argv[1]
    baseline = sys.argv[2] if len(sys.argv) > 2 else None
    name = os.path.basename(other.rstrip("/"))
    print(f"# Code comparison: Cold Movers vs {name}\n")
    total, hits = identical_lines(other)
    print(f"## 1. Identical lines\n\n{len(hits)} of {total} Cold Movers code lines (30+ characters) also appear in {name}.\n")
    for f, i, n, src in hits:
        print(f"- `{f}:{i}` `{n[:110]}` (also in `{src}`)")
    segs = longest_stretches(other)
    print(f"\n## 2. Longest identical code stretches (20+ tokens, names and values kept)\n\n{len(segs)} stretches.\n")
    for n, f, a, b in segs[:12]:
        src = open(os.path.join(OURS, f)).read().splitlines()[a - 1:b]
        print(f"- {n} tokens, `{f}:{a}-{b}`: `{' ⏎ '.join(s.strip() for s in src)[:160]}`")
    hit, tot = masked_share(other)
    print(f"\n## 3. Renamed-copy check (25-token runs, names and values masked)\n\n- {name}: {hit} of {tot} "
          f"({hit / tot:.2%})")
    if baseline:
        bh, bt = masked_share(baseline)
        print(f"- baseline `{os.path.basename(baseline.rstrip('/'))}` (unrelated code, certainly not copied): "
              f"{bh} of {bt} ({bh / bt:.2%})")
    found = text_runs(other)
    print(f"\n## 4. Identical 8-word runs in texts\n")
    for f, items in sorted(found.items()):
        print(f"- `{f}`: " + "; ".join(f"“{' '.join(g)[:120]}” ({src})" for g, src in items[:6]))


if __name__ == "__main__":
    main()
