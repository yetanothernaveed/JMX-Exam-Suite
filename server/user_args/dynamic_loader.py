import importlib.util
import sys
from pathlib import Path
from typing import Any

def load_module_from_path(file_path: str | Path) -> Any:
    """
    Dynamically loads and executes a Python module from an absolute or relative file path.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Checker script not found at: {path}")

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
    spec.loader.exec_module(module)

    return module
