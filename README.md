# Patina

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
[![Framework: Flask](https://img.shields.io/badge/Framework-Flask-000000.svg)](https://flask.palletsprojects.com/)
![OS: macOS | Linux | Windows](https://img.shields.io/badge/OS-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)
[![FOSS Pluralism Manifesto](https://img.shields.io/badge/Manifesto-FOSS%20Pluralism-8A2BE2.svg)](FOSS_PLURALISM_MANIFESTO.md)
[![Contributions welcome](https://img.shields.io/badge/Contributions-welcome-brightgreen.svg)](https://github.com/soyrochus/patina/issues)


# Parlanchina

![Parlanchina logo](images/parlanchina-logo-small.png)

Parlanchina is a production-ready AI chat application built on Flask. It streams assistant replies, renders rich content, persists sessions locally, and is polished enough for real demos and everyday use.

## Feature highlights

- **Model selection**: Pick from your configured OpenAI/Azure models per session.
- **Live streaming**: Incremental text rendering that mirrors the final saved output.
- **Markdown-first**: GitHub-flavored markdown with sanitized HTML on both client and server.
- **Mermaid diagrams**: ```mermaid blocks render with flicker-masking overlays plus zoom controls.
- **Image generation**: OpenAI Responses image tool support with generation overlays, zoom, and persisted files under `data/images/`.
- **Zoom anywhere**: Shared modal zoom for diagrams and generated images.
- **Copy helpers**: One-click copy of raw assistant text from any message bubble.
- **Keyboard flow**: Ctrl/Cmd+Enter to send; other Enter behavior remains unchanged.
- **Local persistence**: JSON session storage in `data/sessions/`; images in `data/images/`.
- **Theming**: Light/dark/system toggle; Mermaid re-renders to match the theme.
- **Session management**: Sidebar list, rename/delete, and automatic title suggestions on the first user message.
- **Safety surfacing**: Image-generation errors are shown in Markdown with a short LLM explanation.

![Parlanchine UI](images/parlanchina-ui.png)

## Installation

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) - Fast Python package installer and resolver

To install uv:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Get Parlanchina

Clone the repository:

```bash
git clone https://github.com/soyrochus/parlanchina.git
cd parlanchina
```

### Install dependencies

Use uv to create a virtual environment and install all dependencies:

```bash
uv sync
```

This will automatically create a `.venv` directory and install all required packages defined in `pyproject.toml`.

### Configure environment

Copy the example environment file and edit it with your API credentials:

```bash
cp .env.example .env
# Edit .env with your OPENAI_API_KEY and other settings
```

## Quickstart

If you've already completed the installation steps above, start the app with:

**macOS/Linux:**

```bash
./parlanchina.sh
```

**Windows (PowerShell):**

```powershell
.\parlanchina.ps1
```

**Or manually:**

```bash
uv run hypercorn parlanchina:app --bind 127.0.0.1:5000 --reload
```

Then open your browser to `http://127.0.0.1:5000`

## Configuration

Set these in `.env` (loaded via `python-dotenv`):

- `OPENAI_API_KEY` — required
- `OPENAI_PROVIDER` — `openai` (default) or `azure`
- `OPENAI_API_BASE` — custom/azure endpoint
- `OPENAI_API_VERSION` — required for Azure
- `PARLANCHINA_MODELS` — comma list of allowed models (e.g. `gpt-4o-mini,gpt-4o`)
- `PARLANCHINA_DEFAULT_MODEL` — picked if user does not select one

## How to use (functional guide)

1. **Start a chat**  
   Launch the app, pick or accept the default model. Sessions auto-save locally as you go.

2. **Send messages**  
   - Type in the input box.  
   - `Ctrl/Cmd+Enter` to send.  
   - Enter behavior otherwise stays as-is.

3. **View streamed replies**  
   - Text streams live, then auto-saves to the session.  
   - One-click copy grabs the raw assistant text for any message.

4. **Render Markdown and Mermaid**  
   - Paste or request fenced ```mermaid blocks.  
   - A rendering overlay hides flicker/errors while diagrams finalize.  
   - Click the zoom icon on diagrams to open them in the modal.

5. **Generate images**  
   - Ask for an image; the app invokes the OpenAI image tool.  
   - While generating, an overlay and “Generating image…” label appear.  
   - Images are stored under `data/images/`, referenced as Markdown, and reload with the session.  
   - Use the zoom icon on images to view them in the modal.

6. **Switch themes**  
   - Toggle light/dark/system; Mermaid diagrams re-render to match the theme.

7. **Manage sessions**  
   - Sidebar lists conversations.  
   - Rename or delete from the menu; first user message triggers an automatic title suggestion.  
   - All chat history is kept in `data/sessions/` as JSON.


## Principles of Participation

Everyone is invited and welcome to contribute: open issues, propose pull requests, share ideas, or help improve documentation. Participation is open to all, regardless of background or viewpoint.

This project follows the [FOSS Pluralism Manifesto](./FOSS_PLURALISM_MANIFESTO.md), which affirms respect for people, freedom to critique ideas, and space for diverse perspectives.


## License and Copyright

Copyright (c) 2025, Iwan van der Kleijn

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
