# PROJECT BRIEF

## Security Review Notes

- We must constrain user-provided Ollama base URLs to loopback-only targets unless explicit opt-in is introduced.
- Relevant implementation files:
  - `project_prompter/web.py`
  - `project_prompter/ollama_client.py`
- Sensitive local Ollama endpoints in scope:
  - `/api/tags`
  - `/api/generate`
- Threat model focus: SSRF-style misuse through analysis configuration and model endpoint routing.
