"""
Diagnostic script — checks WHY traces are not reaching Mistral's dashboard.
Enables OpenTelemetry debug logging to expose export errors.
"""
import os
import sys
import time
import logging
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# Enable detailed OTEL logging — this will show export attempts/failures
logging.basicConfig(level=logging.DEBUG, format="%(name)s | %(levelname)s | %(message)s")
logging.getLogger("opentelemetry").setLevel(logging.DEBUG)
logging.getLogger("opentelemetry.exporter").setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.DEBUG)

print("=" * 60)
print(" DIAGNOSTIC: Checking Mistral Telemetry Export")
print("=" * 60)
print()

# Check env vars
api_key = os.getenv("MISTRAL_API_KEY", "")
sdk_telem = os.getenv("MISTRAL_SDK_TELEMETRY", "NOT SET")
svc_name = os.getenv("OTEL_SERVICE_NAME", "NOT SET")
print(f"  MISTRAL_API_KEY: {api_key[:8]}...{api_key[-4:]}")
print(f"  MISTRAL_SDK_TELEMETRY: {sdk_telem}")
print(f"  OTEL_SERVICE_NAME: {svc_name}")
print()

# Create client and configure telemetry
from mistralai.client import Mistral
from mistralai.extra.observability import configure_telemetry, get_telemetry_tracer

client = Mistral(api_key=api_key)
result = configure_telemetry(client, provider="dedicated", redaction=True)
print(f"  configure_telemetry() returned: {result}")

tracer = get_telemetry_tracer(client, "diagnostic-test")
print(f"  Tracer: {tracer}")
print()

# Make a traced API call
print("Making traced API call...")
with tracer.start_as_current_span("diagnostic_test_span") as span:
    span.set_attribute("credit_dossier.operation", "diagnostic")
    span.set_attribute("gen_ai.system", "mistral")
    
    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[{"role": "user", "content": "Say OK"}]
    )
    print(f"  Response: {response.choices[0].message.content}")

print()
print("Waiting 10 seconds for batch export flush...")
print("(Watch for OTEL export logs above — any errors will show here)")
time.sleep(10)

# Try to force flush the tracer provider
try:
    from opentelemetry import trace as otel_trace
    provider = otel_trace.get_tracer_provider()
    print(f"\n  Global TracerProvider: {type(provider).__name__}")
    if hasattr(provider, 'force_flush'):
        provider.force_flush()
        print("  force_flush() called on global provider")
    
    # Also check if the client has a private provider
    hooks = getattr(client.sdk_configuration, "_hooks", None)
    if hooks:
        print(f"  SDK hooks: {hooks}")
except Exception as e:
    print(f"  Force flush failed: {e}")

print()
print("=" * 60)
print(" DIAGNOSTIC COMPLETE")
print(" Check the logs above for OTLP export errors.")
print(" If no errors, traces should appear on dashboard shortly.")
print("=" * 60)
