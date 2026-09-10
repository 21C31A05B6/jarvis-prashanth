"""File Analyzer: Analyze files and generate code metrics.

This plugin demonstrates:
- Using the local_read and local_write permissions
- Interacting with the local filesystem
- Generating structured reports
"""

from pathlib import Path


def analyze_file(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Analyze a file and return statistics."""
    params = parameters or {}
    path = str(params.get("path") or "").strip()
    if not path:
        return "A file path is required."
    
    filepath = Path(path).expanduser()
    if not filepath.is_file():
        return f"File not found: {path}"
    
    try:
        size = filepath.stat().st_size
        # Determine file type by extension
        suffix = filepath.suffix.lower()
        # Try to detect encoding
        encoding = "unknown"
        lines = 0
        try:
            content = filepath.read_text(encoding="utf-8")
            encoding = "utf-8"
            lines = len(content.splitlines())
        except UnicodeDecodeError:
            try:
                content = filepath.read_text(encoding="latin-1")
                encoding = "latin-1"
                lines = len(content.splitlines())
            except Exception:
                pass
        
        if player:
            player.write_log(f"[FileAnalyzer] Analyzed {filepath.name}")
        
        return (
            f"File Analysis: {filepath.name}\n"
            f"- Path: {filepath}\n"
            f"- Size: {size} bytes\n"
            f"- Type: {suffix or 'unknown'}\n"
            f"- Encoding: {encoding}\n"
            f"- Lines: {lines}"
        )
    except Exception as exc:
        return f"Could not analyze file: {exc}"


def count_lines(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Count lines of code in a directory."""
    params = parameters or {}
    directory = str(params.get("directory") or "").strip()
    extensions = str(params.get("extensions") or "py").strip().split(",")
    extensions = [e.strip().lstrip(".") for e in extensions if e.strip()]
    
    if not directory:
        return "A directory path is required."
    
    dirpath = Path(directory).expanduser()
    if not dirpath.is_dir():
        return f"Directory not found: {directory}"
    
    try:
        total_lines = 0
        file_count = 0
        for ext in extensions:
            pattern = f"*.{ext}"
            for filepath in dirpath.rglob(pattern):
                try:
                    content = filepath.read_text(encoding="utf-8", errors="ignore")
                    lines = len(content.splitlines())
                    total_lines += lines
                    file_count += 1
                except Exception:
                    pass
        
        if player:
            player.write_log(f"[FileAnalyzer] Counted lines in {directory}")
        
        return (
            f"Code metrics for {dirpath}:\n"
            f"- Files: {file_count}\n"
            f"- Total lines: {total_lines}\n"
            f"- Extensions: {', '.join(extensions)}"
        )
    except Exception as exc:
        return f"Could not count lines: {exc}"


def generate_report(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Generate a detailed file analysis report.
    
    Note: This is a stub. A real implementation would:
    1. Recursively scan the directory
    2. Gather statistics for each file type
    3. Create a structured JSON/CSV report
    4. Save it to the specified output path
    """
    params = parameters or {}
    directory = str(params.get("directory") or "").strip()
    output_path = str(params.get("output_path") or "").strip()
    
    if not directory or not output_path:
        return "Both directory and output_path are required."
    
    dirpath = Path(directory).expanduser()
    if not dirpath.is_dir():
        return f"Directory not found: {directory}"
    
    if player:
        player.write_log(f"[FileAnalyzer] Generating report for {directory}")
    
    # Stub implementation
    return f"Report generation requested for {directory} -> {output_path}. [DEMO - Feature in development]"
