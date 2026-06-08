# ambrio/router/tools/file_tool.py
"""
File System Tool for Ambrio.
Allows reading, writing, listing, and searching files anywhere on the system.

Tools registered:
  file_read(path)                    - Read any file
  file_write(path, content)          - Write/create a file
  file_list(directory)               - List directory contents
  file_search(pattern, directory?)   - Search for files by name pattern
  file_move(src, dst)                - Move/rename a file
  file_delete(path)                  - Delete a file (with confirmation flag)
"""
import os, shutil, glob, logging
from pathlib import Path
from ambrio.router.tool_registry import tool

log = logging.getLogger(__name__)

# Safety: block access to sensitive system paths
_BLOCKED = [
    'C:\\Windows\\System32',
    'C:\\Windows\\SysWOW64',
    '/etc/shadow',
    '/etc/passwd',
    '.ssh',
    '.git/config',
]

def _safe_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    for blocked in _BLOCKED:
        if blocked.lower() in str(p).lower() and blocked != '.git/config':
            raise PermissionError(f"Access to {blocked} is blocked for safety")
    return p


@tool(name='file_read', description='Read the contents of any file on the system.')
async def file_read(path: str, max_chars: int = 8000) -> dict:
    """
    Read file contents.
    Args:
        path: Absolute or relative file path
        max_chars: Maximum characters to read (default 8000)
    """
    try:
        p = _safe_path(path)
        if not p.exists():
            return {'error': f'File not found: {path}', 'path': str(p)}
        if not p.is_file():
            return {'error': f'Not a file: {path}', 'path': str(p)}

        size = p.stat().st_size
        try:
            content = p.read_text(encoding='utf-8', errors='replace')
        except Exception:
            content = p.read_text(encoding='latin-1', errors='replace')

        truncated = len(content) > max_chars
        return {
            'path':      str(p),
            'content':   content[:max_chars],
            'size_bytes': size,
            'truncated': truncated,
            'lines':     content[:max_chars].count('\n'),
        }
    except PermissionError as e:
        return {'error': str(e), 'path': path}
    except Exception as e:
        log.error(f'file_read error: {e}')
        return {'error': str(e), 'path': path}


@tool(name='file_write', description='Write content to a file. Creates the file and parent directories if needed.')
async def file_write(path: str, content: str, mode: str = 'overwrite') -> dict:
    """
    Write content to a file.
    Args:
        path: File path to write to
        content: Text content to write
        mode: 'overwrite' (default) or 'append'
    """
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        if mode == 'append':
            with open(p, 'a', encoding='utf-8') as f:
                f.write(content)
        else:
            p.write_text(content, encoding='utf-8')

        return {
            'path':    str(p),
            'written': len(content),
            'mode':    mode,
            'success': True,
        }
    except Exception as e:
        log.error(f'file_write error: {e}')
        return {'error': str(e), 'path': path, 'success': False}


@tool(name='file_list', description='List the contents of a directory.')
async def file_list(directory: str = '.', pattern: str = '*') -> dict:
    """
    List files and subdirectories.
    Args:
        directory: Directory path to list
        pattern: Glob pattern filter (default '*')
    """
    try:
        p = _safe_path(directory)
        if not p.exists():
            return {'error': f'Directory not found: {directory}'}

        entries = []
        for item in sorted(p.glob(pattern)):
            entries.append({
                'name':     item.name,
                'type':     'dir' if item.is_dir() else 'file',
                'size':     item.stat().st_size if item.is_file() else None,
                'path':     str(item),
            })

        return {
            'directory': str(p),
            'entries':   entries[:100],  # cap at 100
            'total':     len(entries),
        }
    except Exception as e:
        return {'error': str(e), 'directory': directory}


@tool(name='file_search', description='Search for files matching a name pattern across directories.')
async def file_search(pattern: str, directory: str = 'C:\\Users', max_results: int = 20) -> dict:
    """
    Find files by name pattern.
    Args:
        pattern: File name pattern (e.g. '*.pdf', 'invoice*.xlsx')
        directory: Root directory to search from
        max_results: Max files to return
    """
    try:
        p = _safe_path(directory)
        found = []
        for match in p.rglob(pattern):
            found.append({
                'name': match.name,
                'path': str(match),
                'size': match.stat().st_size if match.is_file() else None,
            })
            if len(found) >= max_results:
                break

        return {
            'pattern':   pattern,
            'directory': str(p),
            'files':     found,
            'total':     len(found),
        }
    except Exception as e:
        return {'error': str(e), 'pattern': pattern}


@tool(
    name='file_open',
    description=(
        'Open a file or folder with the default Windows application. '
        'Examples: open a PDF in Acrobat, a Word doc in Word, a folder in Explorer, '
        'an image in Photos, a video in Media Player. '
        'Args: path (str) — absolute path to file or folder to open.'
    )
)
async def file_open(path: str) -> dict:
    """
    Open a file or folder with the OS default application (like double-clicking).
    Args:
        path: Absolute path to the file or folder to open.
    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            # Try searching for it nearby
            return {
                'error': f'File not found: {path}',
                'tip':   'Use file_search("filename") to locate the file first.',
                'success': False
            }
        os.startfile(str(p))
        kind = 'folder' if p.is_dir() else 'file'
        return {
            'success':  True,
            'opened':   str(p),
            'type':     kind,
            'answer':   f'✅ Opened {kind}: {p.name}',
        }
    except Exception as e:
        return {'error': str(e), 'path': path, 'success': False}


@tool(
    name='file_show',
    description=(
        'Reveal / show a file in Windows Explorer (highlights the file in its folder). '
        'Useful when the user says "show me the file", "where is it", "open the folder". '
        'Args: path (str) — absolute path to the file.'
    )
)
async def file_show(path: str) -> dict:
    """
    Reveal a file in Windows Explorer.
    Args:
        path: Absolute path to the file to reveal.
    """
    try:
        import subprocess
        p = Path(path).expanduser().resolve()
        if p.is_file():
            # Select the specific file in Explorer
            subprocess.Popen(['explorer', '/select,', str(p)])
            return {
                'success': True,
                'answer':  f'📂 Showing {p.name} in Explorer',
            }
        elif p.is_dir():
            subprocess.Popen(['explorer', str(p)])
            return {
                'success': True,
                'answer':  f'📂 Opened folder: {p.name}',
            }
        else:
            return {'error': f'Path not found: {path}', 'success': False}
    except Exception as e:
        return {'error': str(e), 'path': path, 'success': False}
