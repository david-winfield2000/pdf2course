import asyncio
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from jupyter_client import AsyncKernelManager
from pydantic import BaseModel

ROOT = pathlib.Path(__file__).parent
LESSONS = ROOT / "lessons"
CONN_FILE = ROOT / ".kernel" / "kernel.json"
ENV = {"MPLBACKEND": "module://matplotlib_inline.backend_inline"}

km: AsyncKernelManager
kc = None
lock = asyncio.Lock()  # one execution at a time


async def start_kernel():
    global km, kc
    CONN_FILE.parent.mkdir(exist_ok=True)
    km = AsyncKernelManager(connection_file=str(CONN_FILE))
    await km.start_kernel(env={**__import__("os").environ, **ENV})
    kc = km.client()
    kc.start_channels()
    await kc.wait_for_ready()
    print(f"\nTerminal access:  uv run jupyter console --existing {CONN_FILE}\n")


@asynccontextmanager
async def lifespan(_):
    await start_kernel()
    yield
    kc.stop_channels()
    await km.shutdown_kernel(now=True)


app = FastAPI(lifespan=lifespan)


class Code(BaseModel):
    code: str


@app.post("/api/run")
async def run(body: Code):
    outputs = []
    async with lock:
        msg_id = kc.execute(body.code)
        while True:
            msg = await kc.get_iopub_msg()
            if msg["parent_header"].get("msg_id") != msg_id:
                continue  # output from another client (e.g. the terminal)
            t, c = msg["msg_type"], msg["content"]
            if t == "stream":
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
    return {"outputs": outputs}


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


@app.post("/api/restart")
async def restart():
    async with lock:
        await km.restart_kernel(now=True)
        await kc.wait_for_ready()
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
