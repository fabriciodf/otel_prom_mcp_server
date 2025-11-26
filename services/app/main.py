import os
import time
from typing import Dict, List

import dotenv
from fastapi import FastAPI, HTTPException, Request
from opentelemetry import metrics
from opentelemetry.metrics import Observation
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from pydantic import BaseModel

dotenv.load_dotenv()

app = FastAPI(title="Demo Metrics API", version="0.1.0")

def parse_resource_attributes(raw: str | None) -> Dict[str, str]:
    """Parse OTEL_RESOURCE_ATTRIBUTES=key=value,... into a dict, ignoring malformed pieces."""
    if not raw:
        return {}
    attributes: Dict[str, str] = {}
    for part in raw.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key, value = key.strip(), value.strip()
        if key:
            attributes[key] = value
    return attributes


# OpenTelemetry configuration for metrics export
resource_attributes: Dict[str, str] = {
    ResourceAttributes.SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "demo-metrics-api"),
    ResourceAttributes.SERVICE_NAMESPACE: os.getenv("OTEL_SERVICE_NAMESPACE", "prometheus-ai"),
    "service.version": "0.1.0",
}
resource_attributes.update(parse_resource_attributes(os.getenv("OTEL_RESOURCE_ATTRIBUTES")))
resource = Resource.create(resource_attributes)

metric_exporter = OTLPMetricExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
    insecure=True,
)
metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=5000)
provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
metrics.set_meter_provider(provider)
meter = metrics.get_meter(resource_attributes[ResourceAttributes.SERVICE_NAME])

# Instrument framework and HTTP clients once at import time so middleware is attached before startup
FastAPIInstrumentor.instrument_app(app, meter_provider=provider)
RequestsInstrumentor().instrument()

# Metric instruments
request_counter = meter.create_counter(
    name="demo_requests_total",
    description="Total HTTP requests received by the demo API",
)
latency_histogram = meter.create_histogram(
    name="demo_request_latency_ms",
    description="Request latency captured at the FastAPI edge",
    unit="ms",
)

# In-memory store to expose a simple gauge-like signal
orders: List[dict] = []


class Order(BaseModel):
    item_id: int
    quantity: int


@app.on_event("startup")
async def setup_telemetry() -> None:
    # Observable gauge to track current pending orders without manual updates
    def observe_pending_orders(_options) -> list[Observation]:
        return [Observation(value=len(orders))]

    meter.create_observable_gauge(
        name="demo_pending_orders",
        callbacks=[observe_pending_orders],
        description="Current number of pending in-memory orders",
    )


@app.middleware("http")
async def record_request_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000

    attributes = {
        "http.method": request.method,
        "http.route": request.url.path,
        "http.status_code": response.status_code,
    }
    request_counter.add(1, attributes=attributes)
    latency_histogram.record(elapsed_ms, attributes=attributes)

    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/items/{item_id}")
async def get_item(item_id: int, slow: bool = False) -> dict:
    if item_id < 0:
        raise HTTPException(status_code=400, detail="item_id must be positive")

    # Optional latency injection to make the histogram interesting
    if slow:
        time.sleep(0.4)

    return {"item_id": item_id, "detail": "Sample item", "slow_path": slow}


@app.post("/orders")
async def create_order(order: Order) -> dict:
    payload = order.dict()
    orders.append(payload)
    return {"status": "created", "order": payload, "pending_orders": len(orders)}


@app.delete("/orders/{item_id}")
async def clear_order(item_id: int) -> dict:
    global orders
    before = len(orders)
    orders = [o for o in orders if o["item_id"] != item_id]
    return {"status": "deleted", "removed": before - len(orders), "pending_orders": len(orders)}
