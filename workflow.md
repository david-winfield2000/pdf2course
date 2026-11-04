# Workflow

1. Clone the book's repo to `hidden/handson-mlp`, with the book at `hidden/HOML.pdf`
2. Run everything: `./start.sh`, then open http://127.0.0.1:8000
3. Convert another chapter, one page per section (while running):
   `docker exec -it pdf2course python pdf2lesson.py hidden/HOML.pdf "Chapter 4"`

The container downloads the datasets and online-only PDFs on startup (`fetch_resources.py`, safe to re-run).
Lessons, images and book data stay in `hidden/` (gitignored). After changing `frontend/main.js`, run `npm run build` in `frontend/`.
