# Environment and local paths

Copy `.env.example` to `.env`. Real `.env` files are ignored.

## Directory classes

- `data/raw/`: local source documents.
- `data/processed/`: normalized/chunked intermediate data.
- `data/index/`: local retrieval indexes.
- `.local/`: databases/checkpoints and other machine-local runtime state.
- `workspace/`: generated artifacts for current runs.

None of these locations should contain public secrets or be assumed to exist on another contributor's machine.

## Required local software

Base development: Python 3.12+, uv, Git.

LaTeX feature work: XeLaTeX/TeX Live. Exact packages will be documented once the first template is implemented.
