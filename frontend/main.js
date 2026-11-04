import { marked } from "marked";
import { EditorView, basicSetup } from "codemirror";
import { keymap } from "@codemirror/view";
import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";
import { Prec, EditorState } from "@codemirror/state";
import { indentUnit } from "@codemirror/language";
import { vim, getCM } from "@replit/codemirror-vim";
import { autocompletion, acceptCompletion, startCompletion } from "@codemirror/autocomplete";
import { indentMore } from "@codemirror/commands";

const $ = (id) => document.getElementById(id);
const out = $("output");

async function run() {
  out.textContent = "Running…";
  const r = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: view.state.doc.toString() }) });
  const { outputs } = await r.json();
  out.innerHTML = "";
  for (const o of outputs) {
    if (o.type === "image") {
      const img = document.createElement("img");
      img.src = "data:image/png;base64," + o.data;
      out.append(img);
    } else {
      const pre = document.createElement("pre");
      pre.className = o.type;
      pre.textContent = o.text.replace(/\x1b\[[0-9;]*m/g, "");
      out.append(pre);
    }
  }
}

// Tab completes from the live kernel (like a terminal); falls back to indent
async function kernelComplete(ctx) {
  const r = await fetch("/api/complete", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: ctx.state.doc.toString(), pos: ctx.pos }) });
  const { from, matches } = await r.json();
  return matches.length ? { from, options: matches.map((label) => ({ label })) } : null;
}

const tab = (v) => {
  if (!getCM(v)?.state.vim?.insertMode) return true; // normal mode: Tab does nothing, never moves focus
  if (acceptCompletion(v)) return true;
  const { head } = v.state.selection.main;
  if (/[\w.]$/.test(v.state.sliceDoc(Math.max(0, head - 1), head))) return startCompletion(v);
  return indentMore(v);
};

const view = new EditorView({
  parent: $("editor"),
  doc: "# Click \"Load\" on a code block in the lesson, or type here.\n",
  extensions: [
    vim({ status: true }),
    indentUnit.of("    "),
    EditorState.tabSize.of(4),
    basicSetup,
    python(),
    oneDark,
    autocompletion({ override: [kernelComplete], activateOnTyping: true }),
    Prec.highest(keymap.of([{ key: "Tab", run: tab }, { key: "Mod-Enter", run: () => { run(); return true; } }])),
  ],
});

function load(code) {
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: code } });
  view.focus();
}

let lessonName, sections = [], current = 0, done = new Set(), shown = false;
const key = (i) => `code:${lessonName}:${i}`;
const save = (k, v) => { try { localStorage[k] = v; } catch {} };
const read = (k) => { try { return localStorage[k]; } catch {} };

async function openLesson(name) {
  lessonName = name;
  const md = await (await fetch(`/api/lessons/${name}`)).text();
  const [intro, ...rest] = md.split(/^(?=## )/m);
  sections = rest.map((s, i) => (i === 0 ? intro + s : s));
  done = new Set(JSON.parse(read(`done:${name}`) || "[]"));
  save("lesson", name);
  show(Number(read(`pos:${name}`)) || 0);
}

function show(i) {
  if (shown) save(key(current), view.state.doc.toString());
  shown = true;
  current = Math.max(0, Math.min(i, sections.length - 1));
  save(`pos:${lessonName}`, current);

  let md = sections[current], starter = "";
  md = md.replace(/```python starter\n([\s\S]*?)```\n?/, (_, code) => ((starter = code), ""));
  const el = $("lesson");
  el.innerHTML = marked.parse(md);
  el.querySelectorAll("pre > code.language-python").forEach((code) => {
    const btn = document.createElement("button");
    btn.textContent = "Load →";
    btn.onclick = () => load(code.textContent);
    code.parentElement.append(btn);
  });
  el.scrollTop = 0;
  load(read(key(current)) ?? starter ?? "");
  view.contentDOM.blur();
  out.textContent = "";
  renderProgress();
}

function renderProgress() {
  const bar = $("progress");
  bar.innerHTML = "";
  sections.forEach((_, i) => {
    const seg = document.createElement("i");
    seg.className = (done.has(i) ? "done " : "") + (i === current ? "current" : "");
    seg.onclick = () => show(i);
    bar.append(seg);
  });
  $("label").textContent = `${current + 1}/${sections.length} · ${done.size} done`;
  $("next").textContent = current === sections.length - 1 ? "Finish ✓" : "Next ›";
}

$("next").onclick = () => {
  done.add(current);
  save(`done:${lessonName}`, JSON.stringify([...done]));
  show(current + 1);
};
$("prev").onclick = () => show(current - 1);
$("run").onclick = run;
$("restart").onclick = async () => { await fetch("/api/restart", { method: "POST" }); out.textContent = "Kernel restarted."; };

const names = await (await fetch("/api/lessons")).json();
$("picker").innerHTML = names.map((n) => `<option>${n}</option>`).join("");
$("picker").onchange = (e) => openLesson(e.target.value);
const start = names.includes(read("lesson")) ? read("lesson") : names[0];
$("picker").value = start;
openLesson(start);
