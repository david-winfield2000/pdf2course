import os
import pathlib
import re
import sys

import pymupdf
import pymupdf4llm
from tqdm import tqdm

src = pathlib.Path(sys.argv[1])
only = sys.argv[2] if len(sys.argv) > 2 else None  # optional: only titles containing this
out = src.with_suffix("")  # hidden/HOML/
doc = pymupdf.open(src)

# Section boundaries: every level-1 entry plus every "Chapter N." entry (1-based pages)
toc = [(t, p) for lvl, t, p in doc.get_toc() if lvl == 1 or t.startswith("Chapter ")]
starts = sorted({p for _, p in toc if p > 1} | {len(doc) + 1})
keep = [(t, p) for t, p in toc if t.startswith(("Chapter ", "Preface", "Appendix "))]
sections = [(i, t, p, min(s for s in starts if s > p) - 1) for i, (t, p) in enumerate(keep)]
if only:
    sections = [x for x in sections if only.lower() in x[1].lower()]

(out / "images").mkdir(parents=True, exist_ok=True)
total = sum(e - s + 1 for _, _, s, e in sections)
bar_out = os.fdopen(os.dup(2), "w")  # private handle for the progress bar
devnull = os.open(os.devnull, os.O_WRONLY)
os.dup2(devnull, 1)  # silence library chatter at the fd level
os.dup2(devnull, 2)
with tqdm(total=total, unit="page", file=bar_out) as bar:
    for i, title, s, e in sections:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        md = pymupdf4llm.to_markdown(
            doc,
            pages=list(range(s - 1, e)),
            write_images=True,
            image_path=str(out / "images"),
            image_format="png",
            dpi=200,
            use_ocr=False,  # OCR text gets drawn over figures
            filename=slug,
        )
        md = md.replace(f"]({out}/images/", "](images/")  # make image links relative
        (out / f"{i:02d}-{slug}.md").write_text(md)
        bar.update(e - s + 1)
