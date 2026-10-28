<div align="center">

<img src="docs/assets/banner.svg" alt="Yggdrasil — Code Knowledge Map. Understand software through evidence, not guesswork." width="100%">

# Yggdrasil

**Static repository analysis and code knowledge mapping, with an interactive graph and evidence-backed AI-assisted exploration.**

![Status](https://img.shields.io/badge/status-in%20development-64748b?style=for-the-badge)
![Version](https://img.shields.io/badge/version-0.7.0-58d6a7?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-19-149ECA?style=for-the-badge&logo=react&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-58d6a7?style=for-the-badge)

[Overview](#-overview) · [Features](#-features) · [Architecture](#-architecture) · [Getting started](#-getting-started) · [API](#-api) · [Roadmap](#-roadmap)

🌐 [Português (Brasil)](README.md) · English

</div>

---

## 📸 Demo

Yggdrasil has an interactive React interface for exploring repository analyses, graph nodes, findings, and source evidence. A real screenshot or recording has not yet been committed; this section will be updated when a demonstration captured from a running build is available.

<!-- TODO: Capture a real run and add it to docs/assets/demo.gif.
<p align="center"><img src="docs/assets/demo.gif" alt="Real Yggdrasil workflow: analyze a GitHub repository, explore its graph, review evidence, and export a report." width="900"></p>
-->

## 📖 Overview

Understanding an unfamiliar codebase means moving between files, definitions, imports, tests, configuration, and documentation. A README rarely explains every relationship, and a static-analysis finding is useful only when its evidence can be checked.

**Yggdrasil** turns a public GitHub repository into a commit-pinned inventory, a navigable graph, structured findings, and Markdown reports. It extracts supported Python structure without executing the analyzed project, then lets developers explore components and ask evidence-grounded questions through an optional AI provider.

The graph is central to the experience: users can navigate the structure and relationships between components, while AI helps investigate evidence related to a question. Yggdrasil is an evolving local-first MVP—not a promise of complete code comprehension or vulnerability-free software.

## ✨ Features

- 🌳 **Commit-pinned analysis** — resolves a Git reference to a commit SHA so results can be traced to a specific repository revision.
- 🗂️ **Bounded repository inventory** — records discovered files and directories, applied limits, and reasons for exclusions or partial coverage.
- 🐍 **Static Python parsing** — extracts supported modules, classes, functions, methods, imports, test-file indicators, and selected endpoint patterns without importing or executing target code.
- 🕸️ **Interactive knowledge graph** — explores files and symbols, with source locations and provenance for deterministic versus inferred relationships.
- 🔎 **Question-guided exploration** — retrieves definitions, related tests and examples, relevant documentation, and graph relationships before querying AI.
- 🧭 **Visual analysis trace** — surfaces observable analysis events and helps relate discovered components to evidence; it does not represent or expose private model reasoning.
- 🛡️ **Initial AppSec checks** — identifies patterns that may indicate exposed secrets, redacts recognized patterns before source content is persisted, and creates findings for human review.
- 🧪 **Test-file inventory** — recognizes simple Python test-file conventions; it does not execute tests or measure coverage.
- 📍 **Verifiable citations** — validates references against retrieved evidence and may return an inconclusive result when support is insufficient.
- 📡 **Live analysis updates** — persisted events and Server-Sent Events (SSE) communicate progress and allow clients to resume from a known event position.
- 📝 **Markdown reports** — generates reports from persisted data rather than an unverified free-form conversation.
- 🧭 **Human review of findings** — records confirmation, false positives, accepted risk, non-reproducibility, or a fix in another revision.
- ⚙️ **SQLite by default** — starts without a database server; PostgreSQL is also supported.
- 📏 **Offline RAG retrieval evaluation** — includes a labelled corpus and Hit@k, Recall@k, MRR, and intent metrics, without provider calls during retrieval evaluation.
- 🖥️ **Experimental Windows desktop package** — includes a PyInstaller-packaged launcher; clean-machine acceptance and the package's AI flow still need further validation.

## 🧰 Tech stack

<p align="center">
  <img src="https://skillicons.dev/icons?i=python,fastapi,react,ts,vite,postgres,sqlite,docker&perline=8" alt="Technologies used: Python, FastAPI, React, TypeScript, Vite, PostgreSQL, SQLite, and Docker">
</p>

| Layer | Technology | Role |
|---|---|---|
| Web UI | React 19, TypeScript, Vite | Interactive single-page application |
| Graph canvas | `@xyflow/react` | Graph navigation, selection, zoom, and pan |
| API | Python 3.11+, FastAPI, Pydantic | HTTP API, validation, and analysis orchestration |
| Static analysis | Python `ast` | Extracts supported Python syntax without executing target code |
| Persistence | SQLAlchemy, Alembic, SQLite / PostgreSQL | Stores analysis snapshots, graph data, events, findings, and exports |
| Progress | Server-Sent Events | Streams analysis events to the browser |
| AI (optional) | Configurable OpenAI-compatible interface, including the Gemini API path | Evidence-grounded question answering; disabled by default |
| Windows desktop | PyInstaller | Experimental packaging for the local launcher |
| Optional local stack | Docker Compose | PostgreSQL, API, and web UI |

## 🧩 Architecture

```mermaid
flowchart TD
    U([Developer]) --> WEB[React + TypeScript UI]
    WEB <-->|HTTP / JSON| API[FastAPI]
    API --> GH[GitHub adapter]
    GH --> INV[Bounded inventory at a fixed commit]
    INV --> AST[Python AST parser]
    AST --> GRAPH[Code knowledge graph]
    INV --> SKILLS[Deterministic skills]
    GRAPH --> DB[(SQLite or PostgreSQL)]
    SKILLS --> FINDINGS[Structured findings]
    FINDINGS --> DB
    DB --> REPORT[Markdown report export]
    DB --> RETRIEVAL[Lexical and structural evidence retrieval]
    RETRIEVAL -->|User confirms transmission| AI[Configured AI provider]
    AI --> ANSWER[Answer with validated evidence references]
    ANSWER --> WEB
```

### Evidence model

Yggdrasil distinguishes **deterministically extracted facts** from **inferred relationships**. Relationships inferred from matching names are not presented as confirmed runtime behavior. AI answers are tied to retrieved references, but their semantic conclusions still require human review.

## 🚀 Getting started

### Prerequisites

- **Python 3.11+** (the Windows helper prefers Python 3.13 when available).
- **Node.js 22.12+ and npm** for the web UI.
- **Git** to clone the repository.
- **Docker Desktop** only if you want to use Docker Compose.

> [!IMPORTANT]
> The MVP has no user authentication for network use. Run it locally and keep ports bound to localhost. Do not expose the API or UI to a shared network or the public internet without authentication, authorization, request limits, and a security review.

### Windows — one-command development start

```powershell
git clone https://github.com/GabrielJalmeida/yggdrasil.git
cd yggdrasil
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-dev.ps1"
```

The script creates `.env` from `.env.example` when needed, creates a Python virtual environment, installs API development dependencies, applies database migrations, opens the API in a separate PowerShell window, and starts Vite.

Open:

- **Web UI:** <http://localhost:5173>
- **FastAPI / OpenAPI docs:** <http://127.0.0.1:8000/docs>
- **Health check:** <http://127.0.0.1:8000/api/v1/health>

The default database is local SQLite at `services/api/data/yggdrasil.db`. AI questions remain disabled until a provider is configured.

### Docker Compose

With Docker Desktop running:

```powershell
docker compose up --build
```

Open <http://localhost:5173>. Compose starts PostgreSQL, the API, and the web UI; exposed ports are bound to `127.0.0.1`. Compose database credentials are for development only and must not be reused in real environments.

### Manual development setup

<details>
<summary><strong>Start the API and web UI in separate terminals</strong></summary>

**Terminal 1 — API (from the repository root):**

```powershell
Copy-Item .env.example .env  # only if .env does not exist
cd services/api
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — web UI:**

```powershell
cd apps/web
npm install
npm run dev
```

Linux/macOS helper scripts are available at `scripts/start-api.sh` and `scripts/start-web.sh`.

</details>

### Windows desktop package (experimental)

The build script prepares the frontend, runs local checks, packages the launcher with PyInstaller, and creates a ZIP in Downloads:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\desktop\build-windows.ps1"
```

To test an extracted package, run `desktop\test-windows-package.ps1` and pass the package directory through `-PackageDirectory`. The local smoke test checked startup, UI, local session token, health check, and SQLite persistence. **The package has not yet passed acceptance on a clean machine without Python, Node.js, and Docker; its AI flow also needs end-to-end validation.**

## 🔧 Configuration

Copy `.env.example` to `.env`. The application runs without an AI key; configure a provider only if you want to ask questions about an analyzed repository.

<details>
<summary><strong>Environment variables</strong></summary>

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/yggdrasil.db` | SQLAlchemy database URL; supports SQLite and PostgreSQL. |
| `GITHUB_TOKEN` | Empty | Optional token to increase GitHub API rate limits for public repositories. |
| `FRONTEND_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Origins allowed by API CORS. |
| `MAX_ARCHIVE_BYTES` | `20971520` | Maximum compressed archive size (20 MiB). |
| `MAX_FILES` | `1000` | Maximum inventory entries/files. |
| `MAX_TREE_DIRECTORIES` | `2000` | Maximum subdirectory queries when rebuilding a truncated Git tree. |
| `MAX_FILE_BYTES` | `262144` | Maximum size for an individual text file (256 KiB). |
| `MAX_TOTAL_TEXT_BYTES` | `8388608` | Aggregate text-content budget (8 MiB). |
| `MAX_TOTAL_UNPACKED_BYTES` | `52428800` | Maximum declared uncompressed data (50 MiB). |
| `AI_PROVIDER` | `disabled` | Set to `openai-compatible` to enable the configured AI adapter. |
| `AI_API_KEY` | Empty | Provider key. Required for hosted services; may be omitted only for recognized local endpoints. |
| `AI_BASE_URL` | `https://api.openai.com/v1` | Configured provider base URL. The Gemini API path uses `https://generativelanguage.googleapis.com`. |
| `AI_MODEL` | Empty | Model identifier available to your provider/account. |
| `AI_TIMEOUT_SECONDS` | `90` | AI request timeout; the Gemini path has a 90-second minimum. |
| `AI_REASONING_EFFORT` | `low` | Reasoning level passed to the Gemini path. |
| `AI_MAX_CONTEXT_CHARS` | `14000` | Approximate character budget for retrieved context. |
| `AI_MAX_EVIDENCE_ITEMS` | `8` | Maximum retrieved evidence items per question. |

</details>

### Enable AI questions

Add provider settings to `.env` and restart the API. This example was used in the local validation environment:

```dotenv
AI_PROVIDER=openai-compatible
AI_API_KEY=your-google-ai-studio-key
AI_BASE_URL=https://generativelanguage.googleapis.com
AI_MODEL=gemini-3.6-flash
AI_TIMEOUT_SECONDS=90
AI_REASONING_EFFORT=medium
```

Use a model ID available to your account and region. The example above was used in the local environment on 2026-10-27 and does not guarantee universal availability. Never commit `.env`, API keys, or real credentials. The browser never receives the key. Before sending a question, the UI explains that the question and selected **redacted** evidence snippets will be transmitted to the configured provider after confirmation; the full repository is not sent as a single prompt.

## 💡 Typical workflow

1. Paste a public repository URL such as `https://github.com/owner/project` into the UI and choose a Git reference (for example, `main`).
2. Start the analysis. Yggdrasil resolves the reference to a commit and displays inventory coverage, supported Python symbols, graph relations, warnings, and findings.
3. Search or filter the graph; select a node to inspect its location and available source evidence.
4. Review generated findings. Treat them as candidates until you inspect their evidence and impact.
5. When AI is configured, ask a question about the analyzed snapshot and open the cited references. Check the evidence before relying on the conclusion.
6. Export the analysis to Markdown.

## 📡 API

The API prefix is `/api/v1`. Interactive OpenAPI documentation is available at <http://127.0.0.1:8000/docs> while the local API is running.

<details>
<summary><strong>Available endpoints</strong></summary>

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Health and database readiness check. |
| `GET` | `/api/v1/skills` | Lists enabled skills and their limitations. |
| `POST` | `/api/v1/analyses` | Starts an analysis (`202 Accepted`). |
| `GET` | `/api/v1/analyses` | Lists recent analyses. |
| `GET` | `/api/v1/analyses/{analysis_id}` | Reads analysis status, commit, counts, coverage, and warnings. |
| `GET` | `/api/v1/analyses/{analysis_id}/events` | Streams and replays persisted events as SSE. |
| `GET` | `/api/v1/analyses/{analysis_id}/graph` | Queries nodes and edges with server-side search and filters. |
| `GET` | `/api/v1/analyses/{analysis_id}/nodes/{node_id}` | Loads node details and available source evidence. |
| `GET` | `/api/v1/analyses/{analysis_id}/findings` | Lists findings; supports severity, skill, and status filters. |
| `PATCH` | `/api/v1/analyses/{analysis_id}/findings/{finding_id}/status` | Stores a human review decision. |
| `POST` | `/api/v1/analyses/{analysis_id}/questions` | Asks an evidence-grounded question about a completed analysis. |
| `GET` | `/api/v1/analyses/{analysis_id}/export/markdown` | Downloads the report directly. |
| `POST` | `/api/v1/analyses/{analysis_id}/exports/markdown` | Creates a persisted Markdown export. |
| `GET` | `/api/v1/exports/{export_id}` | Downloads a persisted export. |

</details>

## 🧪 Tests and validation

**Latest local validation recorded on Windows 11:**

- Backend: **101 tests passed**; `compileall` and Ruff passed.
- Frontend: `npm ci`, ESLint, TypeScript type-check, and Vite production build passed.
- Graph layout: 420 synthetic nodes tested without overlaps; overview mode displayed 180 nodes and filtered module views displayed 20.
- Desktop configuration tests: 3 passed.
- Windows desktop package: PyInstaller build completed, ZIP generated, and SHA-256 verified.
- Package smoke test: first launch, UI, local session token, health check, SQLite creation, and persistence across a second launch passed (exit code 0).
- Offline deterministic-skills benchmark: 6/6 cases passed, score 1.0, with zero provider calls. This measures defined skill contracts, not the target repository's absolute security.
- A manual AI query about the Yggdrasil repository returned an evidence-backed answer with citations. This does not establish semantic correctness for every possible answer.
- **Open items:** clean-machine acceptance has not been completed; the desktop package's AI flow showed a local session authorization error during manual testing and remains pending end-to-end validation/correction.

These are local development checks, not a claim that CI or clean-machine release acceptance has passed.

### Run backend tests

From the repository root:

```powershell
cd services/api
python -m pip install -e ".[dev]"
python -m pytest -q
```

### Run frontend checks

```powershell
cd apps/web
npm ci
npm run lint
npm run build
npm run test:layout
```

### Offline RAG retrieval evaluation

The project includes a labelled corpus for `kinegratii/borax` and a local harness that measures retrieval of expected files. It does not by itself measure the semantic correctness of AI-generated answers or validate abstention.

```powershell
cd services/api
python scripts/evaluate_rag.py --analysis-id "ANALYSIS_ID" --cases evaluation/corpora/borax.json --output .\data\rag-evaluation-borax.json
```

Analyze the corpus repository in the UI before running the evaluator. Use the ID of a completed analysis and the same database configured for the API. Labelled paths missing from the snapshot or not read are excluded from metrics, and the report records the commit SHA. See [`docs/RAG-EVALUATION.md`](docs/RAG-EVALUATION.md) for details.

## 🛡️ Security, privacy, and boundaries

- **Read-only analysis:** target code is not imported, executed, built, installed, or tested by Yggdrasil.
- **GitHub origin restrictions:** repository URLs are validated and network requests use fixed GitHub hosts; redirects are rejected.
- **Resource limits:** archive size, file count, individual file size, aggregate content, and tree traversal have configurable bounds.
- **Secret redaction:** supported credential patterns are redacted before source text is persisted. Pattern-based redaction can miss unknown or encoded secrets and is not a guarantee of anonymization.
- **Untrusted repository content:** README text, comments, strings, and source files are treated as untrusted data; the model receives no shell, filesystem, or write-capable tools.
- **AI privacy:** when AI is enabled, the question and selected redacted snippets are sent to the configured provider after user confirmation. Do not submit code unless that transfer is authorized.
- **No network authentication:** this MVP is designed for local use; keep services on localhost.
- **Static-analysis limits:** findings require human review. The absence of a finding does not prove a repository is secure.

See [`docs/SECURITY.md`](docs/SECURITY.md) for the threat model and residual risks.

## 🗂️ Repository structure

```text
yggdrasil/
├── apps/web/                  # React + TypeScript UI and graph canvas
├── desktop/                   # Launcher, local secure storage, experimental Windows build
├── services/api/
│   ├── app/api/               # FastAPI routes
│   ├── app/application/       # Analysis, question, and evaluation orchestration
│   ├── app/domain/            # Graph, findings, reports, and skills
│   ├── app/infrastructure/    # GitHub adapter and AI provider
│   ├── evaluation/corpora/    # Versioned evaluation corpora
│   └── tests/                 # Backend unit and integration tests
├── skills/                    # Versioned skill contracts and manifests
├── docs/                      # Master plan, security, progress, and evaluations
│   └── assets/banner.svg      # README banner
├── scripts/                   # Windows/Linux development helpers
├── .env.example               # Non-secret configuration template
└── docker-compose.yml         # Optional local PostgreSQL stack
```

## 🧭 Roadmap

- [x] Public GitHub repository ingestion pinned to a commit.
- [x] Static Python parsing and persisted knowledge graph.
- [x] Initial deterministic skills and structured human-reviewed findings.
- [x] Evidence-grounded AI questions with citation validation.
- [x] Progress events and Markdown report export.
- [x] SQLite default with PostgreSQL support.
- [x] Initial offline retrieval-evaluation harness and versioned corpus.
- [x] Experimental Windows desktop package and basic local smoke test.
- [ ] Validate clean installation, build, and frontend lint in CI.
- [ ] Expand evaluation of semantic answer quality and abstention.
- [ ] Complete end-to-end AI validation in the desktop package and test on clean Windows.
- [ ] Improve graph navigation and large-result pagination based on observed use.
- [ ] Consider a second language and semantic retrieval only if evaluation demonstrates value.
- [ ] Explore snapshot comparison and incremental re-analysis.

Read the [Master Engineering Plan](docs/MASTER-PLAN.md) (pt-BR) for product direction and [`docs/PROGRESS.md`](docs/PROGRESS.md) for verified implementation state and remaining limitations.

## 🤝 Contributing

Issues and focused pull requests are welcome. Before proposing features, read the current limits and security model. Prefer small, testable changes that preserve read-only analysis of third-party repositories.

1. Fork the repository and create a branch from `main`.
2. Make a focused change and add or update tests.
3. Run the relevant backend or frontend checks.
4. Describe behavior, test evidence, and remaining limitations in the pull request.

## 📜 License

Yggdrasil is distributed under the [MIT License](LICENSE).

## 👤 Author

Created by **[GabrielJalmeida](https://github.com/GabrielJalmeida)**.

---

<div align="center">

**Map before guessing. Evidence before conclusions.**

If Yggdrasil is useful to you, consider giving the repository a ⭐.

</div>
