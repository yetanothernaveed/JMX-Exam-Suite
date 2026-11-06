import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any

_module_cache: dict[str, Any] = {}
_module_cache_lock = threading.Lock()


def load_module_from_path(file_path: str | Path) -> Any:
    """
    Dynamically loads and executes a Python module from an absolute or relative file path.

    Modules are cached by resolved path and loaded under a lock. This prevents
    concurrent submissions for the same question from racing while registering
    the module in ``sys.modules`` or re-executing its top-level code.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Checker script not found at: {path}")

    cache_key = str(path)
    with _module_cache_lock:
        cached_module = _module_cache.get(cache_key)
        if cached_module is not None:
            return cached_module

        # Use the file stem (filename without .py) as the internal module name
        module_name = path.stem

        # 1. Create a spec from the file location
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec for file: {path}")

        # 2. Create a new module based on the spec
        module = importlib.util.module_from_spec(spec)

        # 3. Register it in sys.modules so standard imports inside the script work properly
        sys.modules[module_name] = module

        # 4. Execute the module to populate its namespace (functions, variables, classes)
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise

        _module_cache[cache_key] = module
        return module
