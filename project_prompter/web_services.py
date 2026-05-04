from __future__ import annotations

from pathlib import Path


def build_file_previews(outputs: dict[str, str], per_file_limit: int, total_limit: int) -> tuple[dict[str, str], bool]:
    file_contents: dict[str, str] = {}
    total_preview_chars = 0
    previews_truncated = False

    for rel_path, abs_path in outputs.items():
        try:
            content = Path(abs_path).read_text(encoding="utf-8")
            remaining_budget = total_limit - total_preview_chars
            if remaining_budget <= 0:
                previews_truncated = True
                file_contents[rel_path] = "(preview omitted: size budget reached)"
                continue

            max_chars = min(per_file_limit, remaining_budget)
            if len(content) > max_chars:
                previews_truncated = True
                file_contents[rel_path] = f"{content[:max_chars]}\n\n...(preview truncated after {max_chars} characters)"
                total_preview_chars += max_chars
            else:
                file_contents[rel_path] = content
                total_preview_chars += len(content)
        except Exception:
            file_contents[rel_path] = "(could not read file)"

    return file_contents, previews_truncated
