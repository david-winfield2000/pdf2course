# Workflow

1. Clone the book's repo to `hidden/handson-mlp`, with the book at `hidden/HOML.pdf`
2. Run everything: `./start.sh`, then open http://127.0.0.1:8000. It runs in the background until `./stop.sh`
3. Build the course, one lesson per chapter and one page per section. Chapter 17 is online-only, so it has its own PDF:
   ```sh
   for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 18 19; do uv run pdf2lesson.py hidden/HOML.pdf "Chapter $n"; done
   uv run pdf2lesson.py hidden/online/Chapter_17.pdf "Chapter 17"
   ```

The container downloads the datasets and online-only PDFs on startup (`fetch_resources.py`, safe to re-run).
Lessons, images and book data stay in `hidden/` (gitignored). Your progress (pages done, position, cell code) is saved in the `pdf2course-progress` Docker volume, so it survives restarts and rebuilds but is not in git. After changing `frontend/main.js`, run `npm run build` in `frontend/`.
