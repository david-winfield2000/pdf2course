import { marked } from "marked";
import { EditorView, basicSetup } from "codemirror";
import { keymap } from "@codemirror/view";
import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";
import { Prec, EditorState } from "@codemirror/state";
import { indentUnit } from "@codemirror/language";
import { vim, getCM } from "@replit/codemirror-vim";
import { autocompletion, acceptCompletion, startCompletion, moveCompletionSelection } from "@codemirror/autocomplete";
import { indentMore } from "@codemirror/commands";

const $ = (id) => document.getElementById(id);
const post = (path, body) => fetch(`/api/${path}`, { method: "POST", keepalive: true,
  headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

// Progress lives in progress/progress.json on the server; writes are batched
let progress = {}, unsaved = {}, saveTimer;
const read = (k) => progress[k];
const save = (k, v) => {
  progress[k] = v;
  unsaved[k] = v;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flush, 500);
};
async function flush() {
  clearTimeout(saveTimer);
  if (!Object.keys(unsaved).length) return;
  const changes = unsaved;
  unsaved = {};
  await post("progress", changes);
}
const clean = (text) => text.replace(/\x1b\[[0-9;]*m/g, "");

let lessons = [], lessonName, sections = [], blocks = [], current = 0, done = new Set();
let notebooks = new Map(); // page → cells; outputs live here, only the code is persisted
let ran = new Set(); // code the kernel has already run
let saved = {}; // cell id → results the kernel has for it
let busy = 0, queue = Promise.resolve(), epoch = 0;
let yanked = null, pendingKey = ""; // command mode: yanked cell, first key of dd/yy/gg

// The book shows REPL sessions with their output; keep only what you would type, one cell per run of prompt lines
function runnable(text) {
  if (!/^>>> /m.test(text)) return [text];
  const cells = [];
  let open = false; // true while the previous line was a prompt line
  for (const l of text.split("\n")) {
    if (/^(>>>|\.\.\.)( |$)/.test(l)) {
      if (open) cells[cells.length - 1] += "\n" + l.slice(4); else cells.push(l.slice(4));
      open = true;
    } else open = false; // output: the next prompt starts a new cell
  }
  return cells;
}

function codeBlocks(md) {
  const el = document.createElement("div");
  el.innerHTML = marked.parse(md);
  return [...el.querySelectorAll("pre > code.language-python")].flatMap((c) => runnable(c.textContent));
}

// ---- running code: one job at a time; an error drops whatever was queued behind it

function controls() {
  $("interrupt").hidden = !busy;
  const missing = blocks.slice(0, current).flat().filter((c) => !ran.has(c.trim())).length;
  $("catchup").hidden = busy > 0 || !missing;
  $("catchup").textContent = `Catch up (${missing})`;
  if (!busy) $("status").textContent = $("status").dataset.keep ?? "";
}

function enqueue(job, cancelled) {
  const ticket = epoch;
  delete $("status").dataset.keep;
  busy++;
  controls();
  queue = queue.then(async () => {
    if (ticket === epoch) await job(); else cancelled?.();
    busy--;
    controls();
  });
}

function forgetKernel() {
  ran = new Set();
  saved = {};
  for (const list of notebooks.values()) for (const c of list) {
    c.count = c.result = c.outputs = undefined;
    drawOutputs(c);
  }
}

async function execute(code, cell) {
  const reply = await (await post("run", { code, cell })).json();
  const failed = reply.outputs.find((o) => o.type === "error");
  if (reply.kernel_died) forgetKernel();
  if (failed) epoch++; else ran.add(code.trim());
  return { ...reply, failed };
}

function drawOutputs(cell) {
  if (!cell.dom) return;
  cell.dom.prompt.textContent = cell.queued ? "[*]:" : `[${cell.count ?? " "}]:`;
  cell.dom.prompt.dataset.result = (!cell.queued && cell.result) || "";
  cell.dom.outputs.replaceChildren(...(cell.outputs ?? []).map((o) => {
    if (o.type === "image") {
      const img = document.createElement("img");
      img.src = "data:image/png;base64," + o.data;
      return img;
    }
    const pre = document.createElement("pre");
    pre.className = o.type;
    pre.textContent = clean(o.text);
    return pre;
  }));
}

function runCell(cell) {
  const code = cell.view.state.doc.toString();
  if (!code.trim()) return;
  cell.queued = true;
  cell.result = undefined;
  drawOutputs(cell);
  enqueue(async () => {
    const { outputs, count, result } = await execute(code, cell.id);
    saved[cell.id] = { outputs, count, result };
    Object.assign(cell, saved[cell.id], { queued: false });
    drawOutputs(cell);
  }, () => { cell.queued = false; drawOutputs(cell); });
}

// ---- cells

async function kernelComplete(ctx) {
  const r = await post("complete", { code: ctx.state.doc.toString(), pos: ctx.pos });
  const { from, matches } = await r.json();
  return matches.length ? { from, options: matches.map((label) => ({ label })), validFor: /^\w*$/ } : null;
}

const tab = (v) => {
  if (!getCM(v)?.state.vim?.insertMode) return true; // normal mode: Tab does nothing, never moves focus
  if (acceptCompletion(v)) return true;
  const { head } = v.state.selection.main;
  if (/[\w.]$/.test(v.state.sliceDoc(Math.max(0, head - 1), head))) return startCompletion(v);
  return indentMore(v);
};

const cells = () => notebook(current);

const selectCell = (cell) => cell && cell.dom.root.focus();

function isVimNormal(view) {
  const vimState = getCM(view)?.state.vim;
  return vimState && !vimState.insertMode && !vimState.visualMode;
}

function removeCell(cell) {
  const list = cells();
  const index = list.indexOf(cell);
  list.splice(index, 1);
  cell.dom.root.remove();
  cell.view.destroy();
  if (!list.length) addCell("", 0);
  persist();
  return list[index] ?? list.at(-1);
}

// Command mode: Esc from vim normal mode selects the cell itself, as in Jupyter
function cellKey(cell, e) {
  const list = cells();
  const index = list.indexOf(cell);
  const code = () => cell.view.state.doc.toString();
  const twice = (key) => { const hit = pendingKey === key; pendingKey = hit ? "" : key; return hit; };
  const paste = (at) => { if (yanked !== null) selectCell(addCell(yanked, at)); };
  const keys = {
    j: () => selectCell(list[index + 1]),
    k: () => selectCell(list[index - 1]),
    G: () => selectCell(list.at(-1)),
    g: () => { if (twice("g")) selectCell(list[0]); },
    y: () => { if (twice("y")) yanked = code(); },
    d: () => { if (twice("d")) { yanked = code(); selectCell(removeCell(cell)); } },
    p: () => paste(index + 1),
    P: () => paste(index),
    a: () => selectCell(addCell("", index)),
    b: () => selectCell(addCell("", index + 1)),
    O: () => selectCell(addCell("", index)),
    o: () => selectCell(addCell("", index + 1)),
    i: () => cell.view.focus(),
  };
  if (e.key === "Enter") {
    e.preventDefault();
    if (e.shiftKey) { runCell(cell); selectCell(list[index + 1] ?? addCell("", list.length)); }
    else if (e.metaKey || e.ctrlKey) runCell(cell);
    else cell.view.focus();
    return;
  }
  if (e.metaKey || e.ctrlKey || !keys[e.key]) return;
  e.preventDefault();
  if (!"gyd".includes(e.key)) pendingKey = "";
  keys[e.key]();
}

function persist(page = current) {
  const list = notebook(page).map((c) => ({ id: c.id, code: c.view?.state.doc.toString() ?? c.code }));
  save(`cells:${lessonName}:${page}`, JSON.stringify(list));
}

function advance(cell) {
  const list = cells();
  const next = list[list.indexOf(cell) + 1] ?? addCell("", list.length);
  next.view.focus();
  next.dom.root.scrollIntoView({ block: "nearest" });
}

function mount(cell) {
  const root = document.createElement("div");
  root.className = "cell";
  root.tabIndex = -1;
  root.onkeydown = (e) => { if (e.target === root) cellKey(cell, e); };
  root.innerHTML = `<div class="row"><div class="prompt"></div><div class="input"></div><div class="actions">
    <button title="Run">▶</button><button title="Add a cell below">+</button><button title="Delete cell">×</button></div></div>
    <div class="outputs"></div>`;
  const [run, add, remove] = root.querySelectorAll("button");
  cell.dom = { root, prompt: root.querySelector(".prompt"), outputs: root.querySelector(".outputs") };
  cell.view = new EditorView({
    parent: root.querySelector(".input"),
    doc: cell.code,
    extensions: [
      vim(),
      indentUnit.of("    "),
      EditorState.tabSize.of(4),
      basicSetup,
      python(),
      oneDark,
      autocompletion({ override: [kernelComplete], activateOnTyping: true, defaultKeymap: false }),
      EditorView.updateListener.of((u) => { if (u.docChanged) persist(); }),
      Prec.highest(keymap.of([
        { key: "Tab", run: tab },
        { key: "ArrowDown", run: moveCompletionSelection(true) },
        { key: "ArrowUp", run: moveCompletionSelection(false) },
        { key: "Ctrl-n", run: moveCompletionSelection(true) },
        { key: "Ctrl-p", run: moveCompletionSelection(false) },
        { key: "Escape", run: (v) => { if (!isVimNormal(v)) return false; selectCell(cell); return true; } },
        { key: "Mod-Enter", run: () => { runCell(cell); return true; } },
        { key: "Shift-Enter", run: () => { runCell(cell); advance(cell); return true; } },
      ])),
    ],
  });
  run.onclick = () => runCell(cell);
  add.onclick = () => addCell("", cells().indexOf(cell) + 1).view.focus();
  remove.onclick = () => removeCell(cell);
  drawOutputs(cell);
  return root;
}

const newCell = (code, id = Math.random().toString(36).slice(2)) => ({ id, code, ...saved[id] });

function addCell(code, index) {
  const list = cells();
  const cell = newCell(code);
  const before = list[index]?.dom.root ?? $("add");
  list.splice(index, 0, cell);
  $("cells").insertBefore(mount(cell), before);
  persist();
  return cell;
}

function notebook(page) {
  if (!notebooks.has(page)) {
    const stored = JSON.parse(read(`cells:${lessonName}:${page}`) || "null");
    const old = read(`code:${lessonName}:${page}`); // from the single-editor version
    notebooks.set(page, (stored ?? (old ? [old] : [""])).map((c) => newCell(c.code ?? c, c.id)));
  }
  return notebooks.get(page);
}

function drawCells() {
  document.querySelectorAll(".cell").forEach((el) => el.remove());
  for (const list of notebooks.values()) for (const c of list) {
    if (c.view) { c.code = c.view.state.doc.toString(); c.view.destroy(); }
    c.view = c.dom = null;
  }
  for (const cell of cells()) $("cells").insertBefore(mount(cell), $("add"));
  persist(); // new cells need their ids saved, or a refresh would orphan their results
  $("cells").scrollTop = 0;
}

function loadCode(code) {
  const list = cells();
  const last = list.at(-1);
  const cell = last.view.state.doc.length ? addCell(code, list.length) : last;
  if (cell === last) last.view.dispatch({ changes: { from: 0, insert: code } });
  cell.view.focus();
  cell.dom.root.scrollIntoView({ block: "nearest" });
}

// ---- dashboard: progress is whatever the lesson pages saved

const pagesDone = (l) => JSON.parse(read(`done:${l.name}`) || "[]").filter((i) => i < l.pages).length;

function chapterRow(l, done) {
  const finished = done === l.pages;
  const li = document.createElement("li");
  li.innerHTML = `<a class="${finished ? "complete" : ""}"><span class="num"></span><span class="title"></span>
    <span class="meter"><i></i></span><span class="state"></span></a>`;
  li.firstChild.href = `#${l.name}`;
  li.querySelector(".num").textContent = parseInt(l.name);
  li.querySelector(".title").textContent = l.title;
  li.querySelector(".meter i").style.width = `${100 * done / l.pages}%`;
  li.querySelector(".state").textContent = finished ? "✓ Done" : `${done}/${l.pages}`;
  return li;
}

function renderDashboard() {
  const counts = lessons.map(pagesDone);
  const sum = (list) => list.reduce((a, b) => a + b, 0);
  const pages = sum(lessons.map((l) => l.pages)), done = sum(counts);
  const percent = Math.round(100 * done / pages);
  $("headline").textContent = `${lessons.filter((l, i) => counts[i] === l.pages).length} of ${lessons.length} chapters complete`;
  $("subline").textContent = `${done} of ${pages} pages · ${percent}%`;
  document.querySelector("#total i").style.width = `${100 * done / pages}%`;
  const last = lessons.find((l) => l.name === read("lesson"));
  const next = last ?? lessons[0];
  $("resume").href = `#${next.name}`;
  $("resume").textContent = last ? `Continue chapter ${parseInt(last.name)} ›` : "Start ›";
  $("chapters").replaceChildren(...lessons.map((l, i) => chapterRow(l, counts[i])));
}

function route() {
  const name = location.hash.slice(1);
  const inLesson = lessons.some((l) => l.name === name);
  $("dashboard").hidden = inLesson;
  $("lessonbar").hidden = !inLesson;
  document.querySelector("main").hidden = !inLesson;
  if (!inLesson) return renderDashboard();
  if (name !== lessonName) openLesson(name);
}

// ---- lesson pages

async function openLesson(name) {
  const md = await (await fetch(`/api/lessons/${name}`)).text();
  if (location.hash.slice(1) !== name) return; // already gone elsewhere
  for (const list of notebooks.values()) for (const c of list) c.view?.destroy();
  lessonName = name;
  sections = md.split(/^---$/m).map((s) => s.trim());
  blocks = sections.map(codeBlocks);
  notebooks = new Map();
  done = new Set(JSON.parse(read(`done:${name}`) || "[]"));
  save("lesson", name);
  show(Number(read(`pos:${name}`)) || 0);
}

function show(i) {
  current = Math.max(0, Math.min(i, sections.length - 1));
  save(`pos:${lessonName}`, current);
  const el = $("lesson");
  el.innerHTML = marked.parse(sections[current]);
  el.querySelectorAll("pre > code.language-python").forEach((code) => {
    const btn = document.createElement("button");
    btn.textContent = "Load →";
    btn.onclick = () => runnable(code.textContent).forEach((c) => loadCode(c.trimEnd()));
    code.parentElement.append(btn);
  });
  el.scrollTop = 0;
  drawCells();
  renderProgress();
  controls();
}

function renderProgress() {
  const bar = $("progress");
  bar.innerHTML = "";
  sections.forEach((s, i) => {
    const seg = document.createElement("i");
    seg.className = (done.has(i) ? "done " : "") + (i === current ? "current" : "");
    seg.title = s.match(/^#+ (.*)$/m)?.[1] ?? "";
    seg.onclick = () => show(i);
    bar.append(seg);
  });
  $("label").textContent = `${current + 1}/${sections.length} · ${done.size} done`;
  $("next").textContent = current === sections.length - 1 ? "Finish ✓" : "Next ›";
}

$("next").onclick = () => {
  done.add(current);
  save(`done:${lessonName}`, JSON.stringify([...done]));
  if (current === sections.length - 1) location.hash = "";
  else show(current + 1);
};
$("prev").onclick = () => show(current - 1);
$("add").onclick = () => addCell("", cells().length).view.focus();

// Sections build on each other, so run what the kernel missed on earlier pages
$("catchup").onclick = () => {
  const todo = blocks.slice(0, current).flatMap((list, page) => list.map((code, at) => ({ page, code, at })))
    .filter(({ code }) => !ran.has(code.trim()));
  const name = lessonName;
  enqueue(async () => {
    for (const [i, { page, code, at }] of todo.entries()) {
      if (lessonName !== name) return; // the user moved on; don't mix this lesson's cells into another
      $("status").textContent = `Catching up: block ${i + 1} of ${todo.length}…`;
      // Run it in a cell on its own page, so it gets a number and an ok/error mark like any other
      const list = notebook(page);
      let cell = list.find((c) => (c.view?.state.doc.toString() ?? c.code).trim() === code.trim());
      if (!cell) {
        if (list.length === 1 && !list[0].code.trim()) cell = list[0];
        else { cell = newCell(""); list.splice(Math.min(at, list.length), 0, cell); } // lesson order, not the end
        cell.code = code;
      }
      const { outputs, count, result, failed } = await execute(code, cell.id);
      saved[cell.id] = { outputs, count, result };
      Object.assign(cell, saved[cell.id]);
      persist(page);
      if (failed) {
        $("status").dataset.keep = `Catch up stopped on page ${page + 1}: ` + clean(failed.text).trim().split("\n").at(-1);
        return;
      }
    }
  });
};
$("runall").onclick = () => cells().forEach(runCell);
$("clear").onclick = () => {
  const list = cells();
  post("clear", { cells: list.map((c) => c.id) });
  for (const c of list) {
    delete saved[c.id];
    c.count = c.result = c.outputs = undefined;
    drawOutputs(c);
  }
};
$("interrupt").onclick = () => post("interrupt");
$("reset").onclick = async () => {
  if (!confirm(`Clear all progress on ${lessonName}, including the code in your cells? This also restarts the kernel.`)) return;
  for (const key of Object.keys(progress)) {
    if (key.endsWith(`:${lessonName}`) || key.includes(`:${lessonName}:`)) save(key, null);
  }
  await flush();
  epoch++;
  await post("restart");
  location.reload();
};
$("restart").onclick = async () => {
  epoch++;
  await post("restart");
  forgetKernel();
  $("status").dataset.keep = "Kernel restarted.";
  controls();
};

window.addEventListener("pagehide", flush);
progress = await (await fetch("/api/progress")).json();
if (!Object.keys(progress).length) {
  for (const key of Object.keys(localStorage)) save(key, localStorage[key]); // import from before the file existed
}
const state = await (await fetch("/api/state")).json();
ran = new Set(state.ran);
saved = state.results;
lessons = await (await fetch("/api/lessons")).json();
window.onhashchange = route;
route();

// Draggable divider between lesson and notebook
{
  const div = $("divider"), main = document.querySelector("main");
  div.onpointerdown = (e) => {
    div.setPointerCapture(e.pointerId);
    div.classList.add("drag");
    document.body.classList.add("dragging");
  };
  div.onpointermove = (e) => {
    if (!div.hasPointerCapture(e.pointerId)) return;
    const r = main.getBoundingClientRect();
    const x = Math.min(Math.max(e.clientX - r.left, 250), r.width - 250);
    main.style.setProperty("--left", `${x}px`);
  };
  div.ondblclick = () => main.style.removeProperty("--left");
  div.onpointerup = () => {
    div.classList.remove("drag");
    document.body.classList.remove("dragging");
  };
}
