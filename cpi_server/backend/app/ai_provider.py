"""Load the shared AI provider housed in cd_cpi_server."""
import importlib.util
from pathlib import Path
import sys

_name = "credit_ai_runtime"
if _name not in sys.modules:
    _path = next(candidate for parent in Path(__file__).resolve().parents
                 for candidate in (parent / "ai_runtime.py", parent / "cd_cpi_server" / "ai_runtime.py")
                 if candidate.is_file())
    _spec = importlib.util.spec_from_file_location(_name, _path)
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
AIClient = sys.modules[_name].AIClient
