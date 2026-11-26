"""Refresh the Vite demo fixture without connecting to PostgreSQL."""
import json
from pathlib import Path
import sys

backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend))
from app.services.assessment_paths import sample_assessment_graph

output = backend.parent / "frontend/src/components/assessmentGraphSample.json"
output.write_text(json.dumps(sample_assessment_graph(), indent=2) + "\n", encoding="utf-8")
print(output)
