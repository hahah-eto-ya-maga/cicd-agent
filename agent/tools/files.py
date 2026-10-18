from pathlib import Path


def safe_path(workdir: Path, p: str) -> Path:
    path = (workdir / p).resolve()
    if not path.is_relative_to(workdir):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_read(workdir: Path, path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(workdir, path).read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"

def run_write(workdir: Path, path: str, content: str) -> str:
    try:
        file_path = safe_path(workdir, path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

def run_edit(workdir: Path, path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(workdir, path)
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: text not found in {path}"
        file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"

def run_glob(workdir: Path, pattern: str) -> str:
    import glob as g
    try:
        matches = sorted({
            match for match in g.glob(pattern, root_dir=workdir, recursive=True)
            if (workdir / match).resolve().is_relative_to(workdir)
        })
        shown = matches[:200]
        if len(matches) > 200:
            shown.append("... (more matches omitted; narrow the pattern)")
        return "\n".join(shown) if shown else "(no matches)"
    except Exception as e:
        return f"Error: {e}"

