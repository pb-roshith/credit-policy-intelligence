"""Load the deployment package shared by the Dossier backend and MCP service."""
import importlib.util
from pathlib import Path
import sys

_name = 'credit_dossier_deployment_package'
if _name not in sys.modules:
    _path = Path(__file__).resolve().parents[2] / 'dossier_package.py'
    _spec = importlib.util.spec_from_file_location(_name, _path)
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
package = sys.modules[_name]
