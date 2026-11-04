import os
import pathlib
import sys

import pymupdf
import pymupdf4llm
from tqdm import tqdm

CHUNK = 25

src = pathlib.Path(sys.argv[1])
doc = pymupdf.open(src)
bar_out = os.fdopen(os.dup(2), "w")  # private handle for the progress bar
devnull = os.open(os.devnull, os.O_WRONLY)
os.dup2(devnull, 1)  # silence library chatter at the fd level
os.dup2(devnull, 2)
parts = []
with tqdm(total=len(doc), unit="page", file=bar_out) as bar:
    for start in range(0, len(doc), CHUNK):
        pages = list(range(start, min(start + CHUNK, len(doc))))
        parts.append(pymupdf4llm.to_markdown(doc, pages=pages))
        bar.update(len(pages))
src.with_suffix(".md").write_text("".join(parts))
