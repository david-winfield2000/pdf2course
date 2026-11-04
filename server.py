import asyncio
import os
import pathlib
import queue
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from jupyter_client import AsyncKernelManager
from pydantic import BaseModel

ROOT = pathlib.Path(__file__).parent
LESSONS = ROOT / "hidden" / "course"
BOOK = ROOT / "hidden" / "handson-mlp"  # code runs here: the book expects datasets/ in its repo
CONN_FILE = ROOT / ".kernel" / "kernel.json"
ENV = {"MPLBACKEND": "module://matplotlib_inline.backend_inline"}

km: AsyncKernelManager
kc = None
lock = asyncio.Lock()  # one execution at a time
DIED = "The kernel died, most likely out of memory. It has restarted, so all variables are gone."
ran = set()  # code this kernel has run without error
results = {}  # cell id → its latest outputs; like `ran`, this lives and dies with the kernel


async def revive():
    await km.restart_kernel(now=True)
    await kc.wait_for_ready()
    ran.clear()
    results.clear()


async def start_kernel():
    global km, kc
    CONN_FILE.parent.mkdir(exist_ok=True)
    km = AsyncKernelManager(connection_file=str(CONN_FILE))
    await km.start_kernel(cwd=str(BOOK), env={**os.environ, **ENV})
    kc = km.client()
    kc.start_channels()
    await kc.wait_for_ready()
    print(f"\nTerminal access:  docker exec -it pdf2course jupyter console --existing {CONN_FILE}\n")


@asynccontextmanager
async def lifespan(_):
    await start_kernel()
    yield
    kc.stop_channels()
    await km.shutdown_kernel(now=True)


app = FastAPI(lifespan=lifespan)


class Code(BaseModel):
    code: str
    cell: str | None = None


@app.post("/api/run")
async def run(body: Code):
    outputs, count = [], None
    async with lock:
        msg_id = kc.execute(body.code)
        while True:
            try:
                msg = await kc.get_iopub_msg(timeout=1)
            except queue.Empty:
                if await km.is_alive():
                    continue
                await revive()
                return {"outputs": [{"type": "error", "text": DIED}], "count": None,
                        "result": "error", "kernel_died": True}
            if msg["parent_header"].get("msg_id") != msg_id:
                continue  # output from another client (e.g. the terminal)
            t, c = msg["msg_type"], msg["content"]
            if t == "execute_input":
                count = c["execution_count"]
            elif t == "stream":
                outputs.append({"type": c["name"], "text": c["text"]})
            elif t in ("execute_result", "display_data"):
                d = c["data"]
                if "image/png" in d:
                    outputs.append({"type": "image", "data": d["image/png"]})
                elif "text/plain" in d:
                    outputs.append({"type": "result", "text": d["text/plain"]})
            elif t == "error":
                outputs.append({"type": "error", "text": "\n".join(c["traceback"])})
            elif t == "status" and c["execution_state"] == "idle":
                break
    failed = any(o["type"] == "error" for o in outputs)
    if not failed:
        ran.add(body.code.strip())
    reply = {"outputs": outputs, "count": count, "result": "error" if failed else "ok"}
    if body.cell:
        results[body.cell] = reply
    return reply


@app.get("/api/state")
def state():
    return {"ran": sorted(ran), "results": results}


class Clear(BaseModel):
    cells: list[str]


@app.post("/api/clear")
def clear(body: Clear):
    for c in body.cells:
        results.pop(c, None)
    return {"ok": True}


class Complete(BaseModel):
    code: str
    pos: int


comp_lock = asyncio.Lock()


@app.post("/api/complete")
async def complete(body: Complete):
    async with comp_lock:
        msg_id = kc.complete(body.code, body.pos)
        try:
            while True:
                msg = await asyncio.wait_for(kc.get_shell_msg(), timeout=3)
                if msg["parent_header"].get("msg_id") == msg_id:
                    c = msg["content"]
                    return {"from": c["cursor_start"], "matches": c["matches"]}
        except asyncio.TimeoutError:
            return {"from": body.pos, "matches": []}


@app.post("/api/interrupt")
async def interrupt():
    if await km.is_alive():
        await km.interrupt_kernel()  # no lock: /api/run holds it for as long as the code runs
    return {"ok": True}


@app.post("/api/restart")
async def restart():
    if await km.is_alive():
        await km.interrupt_kernel()  # otherwise a long-running cell would hold the lock
    async with lock:
        await revive()
    return {"ok": True}


@app.get("/api/lessons")
def lessons():
    return sorted(p.stem for p in LESSONS.glob("*.md"))


@app.get("/api/lessons/{name}")
def lesson(name: str):
    return PlainTextResponse((LESSONS / f"{pathlib.Path(name).name}.md").read_text())


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/hidden", StaticFiles(directory=ROOT / "hidden"), name="hidden")


class NoCacheStatic(StaticFiles):
    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        r.headers["Cache-Control"] = "no-store"
        return r


app.mount("/static", NoCacheStatic(directory=ROOT / "static"), name="static")
