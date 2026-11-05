"""Turn one book chapter into a lesson: the book's exact text, one page per section.

    uv run pdf2lesson.py hidden/HOML.pdf "Chapter 3"

Reads font and position data straight from the PDF instead of guessing from
rendered text, so code keeps its spacing and nothing is paraphrased. Figures and
equations are cropped from the page. Writes hidden/course/NN-slug.md, with pages
separated by `---`, and prints how much of the PDF's text made it across.
"""
import collections
import pathlib
import re
import sys

import pymupdf

OUT = pathlib.Path("hidden/course")
FOOTER_Y = 600
MERGE_BELOW = 400  # a section with less text than this joins the next page
SOFT_HYPHEN = "‐"  # the book's line-break hyphen, not part of the word
ICONS = {"bb6146": "Tip", "1f8258": "Note", "1aa31d": "Warning"}  # image digest → label
ESCAPE = re.compile(r"([\\`*_\[\]<])")


def font(span):
    return span["font"], round(span["size"], 1)


def text_of(line):
    return "".join(s["text"] for s in line["spans"])


def is_code(line):
    return all("Ubuntu" in s["font"] and s["size"] < 9 for s in line["spans"] if s["text"].strip())


def is_caption(line, word):
    first = line["spans"][0]
    return first["font"].endswith("-It") and re.match(rf"{word} \d+-\d+\.", text_of(line))


def page_lines(page):
    """Lines top to bottom, without footers or the duplicate list markers the PDF contains."""
    lines, seen = [], set()
    for block in page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        for line in block.get("lines", []):
            line["spans"] = [s for s in line["spans"] if s["text"]]
            if not line["spans"] or not text_of(line).strip():
                continue
            x, y = line["bbox"][:2]
            if y > FOOTER_Y and "Myriad" in line["spans"][0]["font"]:
                continue
            lines.append(line)
            seen.add((round(y), text_of(line).strip()))
    lines = [l for l in lines if not (
        re.fullmatch(r"(\d+|[a-z])\.|•", text_of(l).strip())
        and any(y == round(l["bbox"][1]) and t != text_of(l).strip() and t.startswith(text_of(l).strip())
                for y, t in seen))]
    return sorted(lines, key=lambda l: (round(l["bbox"][1]), l["bbox"][0]))


def crop(page, rect, name):
    OUT.joinpath("images").mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=200, clip=rect).save(OUT / "images" / f"{name}.png")
    return f"/hidden/course/images/{name}.png"


def figures(page, lines, tag):
    """Crop each captioned figure. Returns (items, regions whose text belongs to the image)."""
    clusters = [pymupdf.Rect(c) for c in page.cluster_drawings()] if page.get_drawings() else []
    images = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
    items, cut = [], []
    for line in lines:
        if not is_caption(line, "Figure"):
            continue
        top = line["bbox"][1]
        above = [c for c in clusters if -8 < top - c.y1 < 12]
        if not above:  # the drawing is lost in a page-wide frame, so go by the picture
            above = [i + (-3, -3, 3, 3) for i in images if -8 < top - i.y1 < 12]
            clusters = [c for c in clusters if not any(c.contains(a) for a in above)]
        if not above:
            print(f"  no figure found above: {text_of(line)[:50]}", file=sys.stderr)
            continue
        rect = above[0]
        if rect in clusters:
            clusters.remove(rect)
        inside = [i for i in images if rect.contains(i)]
        if len(inside) == 1:  # the cluster is a page-wide frame; keep just the picture
            rect = inside[0] + (-3, -3, 3, 3)
        name = re.match(r"Figure (\S+?)\.", text_of(line))[1]
        items.append({"kind": "image", "y": top - 1, "src": crop(page, rect, f"{tag}-fig-{name}"),
                      "alt": f"Figure {name}"})
        cut.append(above[0])
    return items, cut, clusters


def tables(page, lines, tag):
    """Crop each captioned table: extracting the text loses spacing and the drawn ratings."""
    captions = [l for l in lines if is_caption(l, "Table")]
    found = page.find_tables().tables if captions else []
    items, cut = [], []
    for table in found:
        rect = pymupdf.Rect(table.bbox) + (-4, -4, 4, 4)
        above = [l for l in captions if l["bbox"][1] < rect.y0]
        if not above:
            continue
        name = re.match(r"Table (\S+?)\.", text_of(above[-1]))[1]
        items.append({"kind": "image", "y": rect.y0, "src": crop(page, rect, f"{tag}-table-{name}"),
                      "alt": f"Table {name}"})
        cut.append(rect)
    return items, cut


def equations(page, lines, tag):
    items, cut = [], []
    for i, line in enumerate(lines):
        if not is_caption(line, "Equation"):
            continue
        rect = pymupdf.Rect()
        boxes = [top for top, _ in callouts(page) if top > line["bbox"][1]]
        for other in lines[i + 1:]:
            if other["bbox"][0] < 75 or other["spans"][0]["size"] > 10.2:
                break
            if boxes and other["bbox"][1] > boxes[0] - 6:
                break
            rect |= pymupdf.Rect(other["bbox"])
        name = re.match(r"Equation (\S+?)\.", text_of(line))[1]
        rect += (-4, -4, 4, 4)
        items.append({"kind": "image", "y": rect.y0, "src": crop(page, rect, f"{tag}-eq-{name}"),
                      "alt": f"Equation {name}"})
        cut.append(rect)
    return items, cut


def callouts(page):
    """Icon position → label, for the tip/note/warning boxes."""
    found = []
    for info in page.get_image_info(hashes=True):
        label = ICONS.get(info["digest"].hex()[:6])
        if label:
            found.append((info["bbox"][1], label))
    return found


def style(span, body_size):
    name = span["font"]
    if "Ubuntu" in name:
        return "code"
    if "Bold" in name:
        return "bold"
    if span["size"] < body_size * 0.7 and span["text"].strip().isalnum():
        return "sub" if span["size"] > 6.1 else "sup"
    return "em" if name.endswith("-It") else ""


def inline(lines):
    """Join a paragraph's lines into markdown, undoing line-break hyphenation."""
    body = max(s["size"] for l in lines for s in l["spans"])
    runs = []
    for i, line in enumerate(lines):
        for span in line["spans"]:
            kind = style(span, body)
            if runs and runs[-1][0] == kind:
                runs[-1][1] += span["text"]
            else:
                runs.append([kind, span["text"]])
        last = runs[-1][1].rstrip()
        if i == len(lines) - 1:
            continue
        if last.endswith(SOFT_HYPHEN):
            runs[-1][1] = last[:-1]
        elif last.endswith(("-", "—", "/")):
            runs[-1][1] = last
        else:
            runs[-1][1] = last + " "
    out = ""
    wrap = {"em": "*{}*", "bold": "**{}**", "sup": "<sup>{}</sup>", "sub": "<sub>{}</sub>"}
    for kind, text in runs:
        core = text.strip()
        if not core:
            out += text
        elif kind == "code":
            out += text[: len(text) - len(text.lstrip())] + f"`{core}`" + text[len(text.rstrip()):]
        elif kind:
            lead = text[: len(text) - len(text.lstrip())]
            out += lead + wrap[kind].format(ESCAPE.sub(r"\\\1", core)) + text[len(text.rstrip()):]
        else:
            out += ESCAPE.sub(r"\\\1", text)
    return out.strip()


def parse_page(page, tag):
    lines = page_lines(page)
    items, cut, boxes = figures(page, lines, tag)
    eq_items, eq_cut = equations(page, lines, tag)
    table_items, table_cut = tables(page, lines, tag)
    items += eq_items + table_items
    cut += eq_cut + table_cut
    labels = callouts(page)
    footnotes, in_note, para, code = [], False, None, None

    def flush():
        nonlocal para, code
        if para:
            items.append(para)
        if code:
            items.append(code)
        para = code = None

    for line in lines:
        x, y, _, bottom = line["bbox"]
        middle = pymupdf.Point(line["bbox"][0] + 5, (y + bottom) / 2)
        if any(middle in r for r in cut):
            continue
        first = line["spans"][0]
        name, size = font(first)
        raw = text_of(line)

        if "Myriad" in name:
            flush()
            if size >= 25:
                if items and items[-1].get("level") == 1:  # a title wrapped onto two lines
                    items[-1]["text"] += " " + raw.strip()
                else:
                    items.append({"kind": "h", "level": 1, "text": raw.strip(), "y": y})
            elif 16.5 <= size < 18:
                continue  # "CHAPTER 3" label
            else:
                level = 2 if size > 18 else 3 if size > 15.5 else 4
                items.append({"kind": "h", "level": level, "text": raw.strip(), "y": y,
                              "box": level == 4})
            continue
        if size == 7.0 and x < 76 and raw[0].isdigit():
            flush()
            in_note = True
            footnotes.append([line])
            continue
        if in_note:
            footnotes[-1].append(line)
            continue

        boxed = any(middle in r for r in boxes)
        quoted = boxed or x > 130 and size == 9.6
        if is_code(line):
            if para:
                flush()
            if code and abs(y - code["bottom"]) < 1:  # one line the PDF stores in two pieces
                code["lines"][-1] += raw.rstrip()
                continue
            if code is None:
                code = {"kind": "code", "lines": [], "y": y, "quoted": quoted, "bottom": y}
            elif y - code["bottom"] > 15:
                code["lines"].append("")
            code["lines"].append(raw.rstrip())
            code["bottom"] = y
            continue
        if code:
            flush()

        item = re.match(r"(\d+)\.\s|([a-z])\.\s|•\s*", raw) if x < 110 else None
        prior_gap = para and y - para["lines"][-1]["bbox"][1]
        indented = para and not para["list"] and abs(x - para["x"]) > 5  # definition lists
        if item or para is None or prior_gap > 15 or para["quoted"] != quoted or indented:
            flush()
            para = {"kind": "p", "lines": [], "y": y, "quoted": quoted, "x": x, "list": None}
            if item:
                para["list"] = "num" if item[1] else "alpha" if item[2] else "bullet"
        para["lines"].append(line)
    flush()

    for item in items:  # attach each callout's label to its first paragraph
        if item["kind"] == "p" and item["quoted"] and item["x"] > 130:
            near = [l for top, l in labels if abs(top - item["y"]) < 40]
            item["label"] = near[0] if near else None
    items.sort(key=lambda i: i["y"])
    return items, footnotes


def joinable(previous, para):
    return (previous["kind"] == "p" and previous["quoted"] == para["quoted"]
            and not para["list"] and not para.get("label")
            and not re.search(r"[.:?!”)]$", text_of(previous["lines"][-1]).strip()))


def assemble(pages):
    """Merge paragraphs split across pages, then render markdown blocks."""
    items = []
    for page_items in pages:
        for n, item in enumerate(page_items):
            if n == 0 or (item["kind"] == "p" and items and items[-1]["kind"] == "image"):
                if item["kind"] == "p":
                    back = next((i for i in reversed(items) if i["kind"] != "image"), None)
                    if back and joinable(back, item):
                        back["lines"] += item["lines"]
                        continue
                elif item["kind"] == "code" and items and items[-1]["kind"] == "code":
                    items[-1]["lines"] += item["lines"]
                    continue
            items.append(item)
    return items


def render(item):
    q = "> " if item.get("quoted") or item.get("box") else ""
    if item["kind"] == "h":
        return q + "#" * item["level"] + " " + item["text"]
    if item["kind"] == "image":
        return f"![{item['alt']}]({item['src']})"
    if item["kind"] == "code":
        return "\n".join(q + l for l in ["```python", *item["lines"], "```"])
    text = inline(item["lines"])
    if item["list"] == "num":
        text = re.sub(r"^(\*\*)?(\d+\.)\s*(\*\*)?\s*", r"\2 ", text)
    elif item["list"] == "alpha":
        text = "   - " + text
    elif item["list"] == "bullet":
        text = "- " + text.lstrip("• ")
    elif item["x"] > 100 and not q:
        text = "     " + text  # continuation of a sub-item
    if item.get("label"):
        text = f"**{item['label']}:** {text}"
    return "\n".join(q + l for l in text.split("\n"))


def weight(section):
    if any(i["kind"] in ("code", "image") for i in section):
        return MERGE_BELOW
    return sum(len(inline(i["lines"])) for i in section if i["kind"] == "p")


def split_pages(items):
    """One page per h2/h3 heading; near-empty parent sections join their first child."""
    sections = [[]]
    for item in items:
        if item["kind"] == "h" and item["level"] in (2, 3) and sections[-1]:
            sections.append([])
        sections[-1].append(item)
    merged = []
    carry = []
    for section in sections:
        section = carry + section
        carry = section if weight(section) < MERGE_BELOW and section is not sections[-1] else []
        if not carry:
            merged.append(section)
    return merged


def coverage(doc, start, end, out_text):
    """PDF words missing from the lesson. Text drawn inside figures is expected here."""
    words = lambda s: collections.Counter(re.findall(r"[a-z0-9]+", s.lower()))
    source = collections.Counter()
    for n in range(start, end):
        text = "\n".join(text_of(line).rstrip() for line in page_lines(doc[n]))
        source.update(words(text.replace(SOFT_HYPHEN + "\n", "")))
    lesson = words(re.sub(r"\\|\(/hidden[^)]*\)", "", out_text))
    return source, source - lesson


def main():
    pdf, wanted = sys.argv[1], sys.argv[2]
    doc = pymupdf.open(pdf)
    toc = doc.get_toc()
    index = next(i for i, t in enumerate(toc) if t[1].startswith(wanted + ".") or t[1].startswith(wanted + " "))
    level, title, start = toc[index]
    end = next((t[2] for t in toc[index + 1:] if t[0] <= level), len(doc) + 1) - 1
    number = int(re.search(r"\d+", title)[0])
    tag = f"{number:02d}"

    pages, notes = [], []
    for n in range(start - 1, end):
        items, footnotes = parse_page(doc[n], tag)
        pages.append(items)
        notes.append(footnotes)

    # Footnotes go at the end of the page that cites them
    note_text = {}
    for footnotes in notes:
        for lines in footnotes:
            first = lines[0]["spans"][0]["text"].strip()
            lines[0]["spans"] = lines[0]["spans"][1:]
            note_text[first] = inline(lines)

    blocks = []
    for section in split_pages(assemble(pages)):
        body = "\n\n".join(render(i) for i in section)
        cited = re.findall(r"<sup>(\d+)</sup>", body)
        body += "".join(f"\n\n<small><sup>{c}</sup> {note_text[c]}</small>" for c in cited if c in note_text)
        blocks.append(body)

    slug = re.sub(r"[^a-z0-9]+", "-", title.split(".", 1)[-1].lower()).strip("-")
    path = OUT / f"{tag}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n\n---\n\n".join(blocks) + "\n"
    path.write_text(text)

    source, missing = coverage(doc, start - 1, end, text)
    share = 1 - sum(missing.values()) / sum(source.values())
    print(f"{path}: {len(blocks)} pages, {share:.1%} of PDF words present")
    print("missing (usually text inside figures):", " ".join(sorted(missing)[:60]))


if __name__ == "__main__":
    main()
