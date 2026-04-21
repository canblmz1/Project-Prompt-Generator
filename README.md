# Local Project Prompt Generator

## What is this?

Local Project Prompt Generator is a local-first developer tool that scans a project, redacts secrets, creates structural summaries, and generates model-specific prompts for ChatGPT, Claude, Gemini, MiniMax, and generic AI assistants. Ollama is optional.

## Why use it?

When you want to ask a cloud AI to review your project, you face several problems:
- **Context limits:** You can't paste an entire codebase.
- **Security risks:** You might accidentally paste secrets, API keys, or private code.
- **Prompt quality:** Generic pastes produce generic answers.

This tool solves all of these by intelligent filtering, fast static analysis, secret redaction, and optional local AI summarization to compress your codebase before you ever share it.

## Key Features

- **Fast & Local:** The default mode uses entirely static local processes that complete in seconds without hitting the network.
- **Robust Redaction:** Excludes sensitive files (`.env`, `.pem`, etc.) and automatically redacts recognizable secrets from source code.
- **Deep Compatibility:** Tailors output automatically for ChatGPT, Claude, Gemini, and MiniMax via meticulously constructed prompts formats.
- **Structural Analysis:** Parses and detects standard architectures out of Python, Javascript, generic backend routing and data configuration.
- **Dynamic Risk & Domain Classification:** Flags large unmanageable files, and applies bespoke contextual prompts for specific domains (like e-commerce, content CMS, or audio).

## Security Model

- **Local first:** The application executes locally. Your code is not automatically sent to the cloud. You inspect and copy the prompt to share.
- **Redaction is built-in:** We look for typical structures matching credentials, passwords, APIs, and obfuscate them. 

> **Best Effort Redaction:** Secret redaction is best-effort and pattern-based. Always review generated prompts before sharing them with any external AI system.
> **Prompt Preparation:** This tool prepares prompts locally. It does not automatically upload your code to cloud AI services.

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/project-prompter.git
cd project-prompter

# Create a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# Install dependencies and the tool
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

## Quick Start

```bash
# Check the help page
project-prompter --help

# Basic generation with Fast Mode
project-prompter "C:/dev/my-project" --mode fast --target-model all

# Access the Web UI
project-prompter --ui
```

Then visit `http://127.0.0.1:8787` in your browser.

## CLI Usage

Run tests over your workspace:
```bash
project-prompter ./my-project --target-model chatgpt
project-prompter ./my-project --mode balanced --use-ollama --model qwen2.5-coder:1.5b
```

## Modes

Fast mode does not use Ollama. Ollama support is optional.

### Fast Mode
Default mode. Does not use Ollama. Uses static and structural analysis only.

Best for:
- quick prompt generation
- large projects
- privacy-focused review preparation

### Balanced Mode
Uses structural analysis and can optionally use Ollama on selected critical files.

Example:
```bash
project-prompter "./my-project" --mode balanced --use-ollama --model qwen2.5-coder:1.5b
```

### Deep Mode
More detailed but slower. Uses Ollama only if explicitly enabled.

Example:
```bash
project-prompter "./my-project" --mode deep --use-ollama --model qwen2.5-coder:3b
```

## Optional Ollama Support

If you wish to augment summaries using a local language model, you can install Ollama.
We default to not using this to maintain high performance. Start Ollama and pass `--use-ollama` in `--mode balanced` or `deep`.

## Web UI

For a better visual experience, run:
```bash
project-prompter --ui
```
Navigate to http://127.0.0.1:8787.

## Output Files

Output is constructed nicely in the `output/` directory:
```
output/
├── project_summary.md
├── file_tree.md
├── tech_stack.md
├── risk_notes.md
├── scan_report.json
└── prompts/
    └── chatgpt_prompt.md
```

## Example Generated Prompt

```bash
project-prompter "./example-project" --mode fast --target-model chatgpt
```

Generated files:
```
output/
├── project_summary.md
├── file_tree.md
├── tech_stack.md
├── risk_notes.md
├── scan_report.json
└── prompts/
    └── chatgpt_prompt.md
```

## Development

Set up following the installation sections and push via PR.

## Testing

Ensure tests pass:
```bash
pytest
```

## Limitations

- Secret redaction is best-effort and pattern-based.
- Structural analysis is heuristically derived.
- Very large projects may bypass file-preview limits (these are adjusted per mode).

## Roadmap

- Enhanced language structural parsers
- Full tree-sitter integration for better logic scoping
- Additional prompt target frameworks

## License

MIT
