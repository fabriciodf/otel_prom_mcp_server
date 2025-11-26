#!/usr/bin/env python

import os
import json
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import time
from datetime import datetime, timedelta
from enum import Enum

import dotenv
import requests
from fastmcp import FastMCP, Context
from prometheus_mcp_server.logging_config import get_logger

dotenv.load_dotenv()
mcp = FastMCP("Prometheus MCP")

# Cache for metrics list to improve completion performance
_metrics_cache = {"data": None, "timestamp": 0}
_CACHE_TTL = 300  # 5 minutes

# Get logger instance
logger = get_logger()

# Health check tool for Docker containers and monitoring
@mcp.tool(
    description="Verifica saúde do servidor MCP e conectividade com o Prometheus",
    annotations={
        "title": "Verificar Saúde",
        "icon": "❤️",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def health_check() -> Dict[str, Any]:
    """Retorna o estado de saúde do servidor MCP e da conexão com o Prometheus.

    Returns:
        Health status including service information, configuration, and connectivity
    """
    try:
        health_status = {
            "status": "healthy",
            "service": "prometheus-mcp-server",
            "version": "1.5.0",
            "timestamp": datetime.utcnow().isoformat(),
            "transport": config.mcp_server_config.mcp_server_transport if config.mcp_server_config else "stdio",
            "configuration": {
                "prometheus_url_configured": bool(config.url),
                "authentication_configured": bool(config.username or config.token),
                "org_id_configured": bool(config.org_id)
            }
        }
        
        # Test Prometheus connectivity if configured
        if config.url:
            try:
                # Quick connectivity test
                make_prometheus_request("query", params={"query": "up", "time": str(int(time.time()))})
                health_status["prometheus_connectivity"] = "healthy"
                health_status["prometheus_url"] = config.url
            except Exception as e:
                health_status["prometheus_connectivity"] = "unhealthy"
                health_status["prometheus_error"] = str(e)
                health_status["status"] = "degraded"
        else:
            health_status["status"] = "unhealthy"
            health_status["error"] = "PROMETHEUS_URL not configured"
        
        logger.info("Health check completed", status=health_status["status"])
        return health_status
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "prometheus-mcp-server",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


class TransportType(str, Enum):
    """Supported MCP server transport types."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid transport values."""
        return [transport.value for transport in cls]

@dataclass
class MCPServerConfig:
    """Global Configuration for MCP."""
    mcp_server_transport: TransportType = None
    mcp_bind_host: str = None
    mcp_bind_port: int = None

    def __post_init__(self):
        """Validate mcp configuration."""
        if not self.mcp_server_transport:
            raise ValueError("MCP SERVER TRANSPORT is required")
        if not self.mcp_bind_host:
            raise ValueError(f"MCP BIND HOST is required")
        if not self.mcp_bind_port:
            raise ValueError(f"MCP BIND PORT is required")

@dataclass
class PrometheusConfig:
    url: str
    url_ssl_verify: bool = True
    disable_prometheus_links: bool = False
    # Optional credentials
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    # Optional Org ID for multi-tenant setups
    org_id: Optional[str] = None
    # Optional Custom MCP Server Configuration
    mcp_server_config: Optional[MCPServerConfig] = None
    # Optional custom headers for Prometheus requests
    custom_headers: Optional[Dict[str, str]] = None

config = PrometheusConfig(
    url=os.environ.get("PROMETHEUS_URL", ""),
    url_ssl_verify=os.environ.get("PROMETHEUS_URL_SSL_VERIFY", "True").lower() in ("true", "1", "yes"),
    disable_prometheus_links=os.environ.get("PROMETHEUS_DISABLE_LINKS", "False").lower() in ("true", "1", "yes"),
    username=os.environ.get("PROMETHEUS_USERNAME", ""),
    password=os.environ.get("PROMETHEUS_PASSWORD", ""),
    token=os.environ.get("PROMETHEUS_TOKEN", ""),
    org_id=os.environ.get("ORG_ID", ""),
    mcp_server_config=MCPServerConfig(
        mcp_server_transport=os.environ.get("PROMETHEUS_MCP_SERVER_TRANSPORT", "stdio").lower(),
        mcp_bind_host=os.environ.get("PROMETHEUS_MCP_BIND_HOST", "127.0.0.1"),
        mcp_bind_port=int(os.environ.get("PROMETHEUS_MCP_BIND_PORT", "8080"))
    ),
    custom_headers=json.loads(os.environ.get("PROMETHEUS_CUSTOM_HEADERS")) if os.environ.get("PROMETHEUS_CUSTOM_HEADERS") else None,
)

def get_prometheus_auth():
    """Get authentication for Prometheus based on provided credentials."""
    if config.token:
        return {"Authorization": f"Bearer {config.token}"}
    elif config.username and config.password:
        return requests.auth.HTTPBasicAuth(config.username, config.password)
    return None

def make_prometheus_request(endpoint, params=None):
    """Make a request to the Prometheus API with proper authentication and headers."""
    if not config.url:
        logger.error("Prometheus configuration missing", error="PROMETHEUS_URL not set")
        raise ValueError("Prometheus configuration is missing. Please set PROMETHEUS_URL environment variable.")
    if not config.url_ssl_verify:
        logger.warning("SSL certificate verification is disabled. This is insecure and should not be used in production environments.", endpoint=endpoint)

    url = f"{config.url.rstrip('/')}/api/v1/{endpoint}"
    url_ssl_verify = config.url_ssl_verify
    auth = get_prometheus_auth()
    headers = {}

    if isinstance(auth, dict):  # Token auth is passed via headers
        headers.update(auth)
        auth = None  # Clear auth for requests.get if it's already in headers
    
    # Add OrgID header if specified
    if config.org_id:
        headers["X-Scope-OrgID"] = config.org_id

    if config.custom_headers:
        headers.update(config.custom_headers)

    try:
        logger.debug("Making Prometheus API request", endpoint=endpoint, url=url, params=params, headers=headers)

        # Make the request with appropriate headers and auth
        response = requests.get(url, params=params, auth=auth, headers=headers, verify=url_ssl_verify)
        
        response.raise_for_status()
        result = response.json()
        
        if result["status"] != "success":
            error_msg = result.get('error', 'Unknown error')
            logger.error("Prometheus API returned error", endpoint=endpoint, error=error_msg, status=result["status"])
            raise ValueError(f"Prometheus API error: {error_msg}")
        
        data_field = result.get("data", {})
        if isinstance(data_field, dict):
            result_type = data_field.get("resultType")
        else:
            result_type = "list"
        logger.debug("Prometheus API request successful", endpoint=endpoint, result_type=result_type)
        return result["data"]
    
    except requests.exceptions.RequestException as e:
        logger.error("HTTP request to Prometheus failed", endpoint=endpoint, url=url, error=str(e), error_type=type(e).__name__)
        raise
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Prometheus response as JSON", endpoint=endpoint, url=url, error=str(e))
        raise ValueError(f"Invalid JSON response from Prometheus: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error during Prometheus request", endpoint=endpoint, url=url, error=str(e), error_type=type(e).__name__)
        raise

def get_cached_metrics() -> List[str]:
    """Get metrics list with caching to improve completion performance.

    This helper function is available for future completion support when
    FastMCP implements the completion capability. For now, it can be used
    internally to optimize repeated metric list requests.
    """
    current_time = time.time()

    # Check if cache is valid
    if _metrics_cache["data"] is not None and (current_time - _metrics_cache["timestamp"]) < _CACHE_TTL:
        logger.debug("Using cached metrics list", cache_age=current_time - _metrics_cache["timestamp"])
        return _metrics_cache["data"]

    # Fetch fresh metrics
    try:
        data = make_prometheus_request("label/__name__/values")
        _metrics_cache["data"] = data
        _metrics_cache["timestamp"] = current_time
        logger.debug("Refreshed metrics cache", metric_count=len(data))
        return data
    except Exception as e:
        logger.error("Failed to fetch metrics for cache", error=str(e))
        # Return cached data if available, even if expired
        return _metrics_cache["data"] if _metrics_cache["data"] is not None else []

# Note: Argument completions will be added when FastMCP supports the completion
# capability. The get_cached_metrics() function above is ready for that integration.

@mcp.tool(
    description="Executa uma consulta PromQL instantânea no Prometheus",
    annotations={
        "title": "Executar PromQL (instantânea)",
        "icon": "📊",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def execute_query(query: str, time: Optional[str] = None) -> Dict[str, Any]:
    """Executa uma consulta instantânea no Prometheus.

    Args:
        query: PromQL query string
        time: Optional RFC3339 or Unix timestamp (default: current time)

    Returns:
        Query result with type (vector, matrix, scalar, string) and values
    """
    params = {"query": query}
    if time:
        params["time"] = time
    
    logger.info("Executing instant query", query=query, time=time)
    data = make_prometheus_request("query", params=params)

    result = {
        "resultType": data["resultType"],
        "result": data["result"]
    }

    if not config.disable_prometheus_links:
        from urllib.parse import urlencode
        ui_params = {"g0.expr": query, "g0.tab": "0"}
        if time:
            ui_params["g0.moment_input"] = time
        prometheus_ui_link = f"{config.url.rstrip('/')}/graph?{urlencode(ui_params)}"
        result["links"] = [{
            "href": prometheus_ui_link,
            "rel": "prometheus-ui",
            "title": "Ver no Prometheus UI"
        }]

    logger.info("Instant query completed",
                query=query,
                result_type=data["resultType"],
                result_count=len(data["result"]) if isinstance(data["result"], list) else 1)

    return result

@mcp.tool(
    description="Executa uma consulta PromQL de período (range) com início, fim e passo",
    annotations={
        "title": "Executar PromQL (range)",
        "icon": "📈",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def execute_range_query(query: str, start: str, end: str, step: str, ctx: Context | None = None) -> Dict[str, Any]:
    """Executa uma consulta de período (range) no Prometheus.

    Args:
        query: PromQL query string
        start: Start time as RFC3339 or Unix timestamp
        end: End time as RFC3339 or Unix timestamp
        step: Query resolution step width (e.g., '15s', '1m', '1h')

    Returns:
        Range query result with type (usually matrix) and values over time
    """
    params = {
        "query": query,
        "start": start,
        "end": end,
        "step": step
    }

    logger.info("Executando consulta de período", query=query, start=start, end=end, step=step)

    # Report progress if context available
    if ctx:
        await ctx.report_progress(progress=0, total=100, message="Iniciando consulta de período...")

    data = make_prometheus_request("query_range", params=params)

    # Report progress
    if ctx:
        await ctx.report_progress(progress=50, total=100, message="Processando resultados da consulta...")

    result = {
        "resultType": data["resultType"],
        "result": data["result"]
    }

    if not config.disable_prometheus_links:
        from urllib.parse import urlencode
        ui_params = {
            "g0.expr": query,
            "g0.tab": "0",
            "g0.range_input": f"{start} to {end}",
            "g0.step_input": step
        }
        prometheus_ui_link = f"{config.url.rstrip('/')}/graph?{urlencode(ui_params)}"
        result["links"] = [{
            "href": prometheus_ui_link,
            "rel": "prometheus-ui",
            "title": "Ver no Prometheus UI"
        }]

    # Report completion
    if ctx:
        await ctx.report_progress(progress=100, total=100, message="Consulta de período concluída")

    logger.info("Consulta de período concluída",
                query=query,
                result_type=data["resultType"],
                result_count=len(data["result"]) if isinstance(data["result"], list) else 1)

    return result

@mcp.tool(
    description="Lista métricas disponíveis no Prometheus (suporta paginação e filtro)",
    annotations={
        "title": "Listar métricas",
        "icon": "📋",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def list_metrics(
    limit: Optional[int] = None,
    offset: int = 0,
    filter_pattern: Optional[str] = None,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """Obtém a lista de nomes de métricas disponíveis no Prometheus.

    Args:
        limit: Maximum number of metrics to return (default: all metrics)
        offset: Number of metrics to skip for pagination (default: 0)
        filter_pattern: Optional substring to filter metric names (case-insensitive)

    Returns:
        Dictionary containing:
        - metrics: List of metric names
        - total_count: Total number of metrics (before pagination)
        - returned_count: Number of metrics returned
        - offset: Current offset
        - has_more: Whether more metrics are available
    """
    logger.info("Listando métricas disponíveis", limit=limit, offset=offset, filter_pattern=filter_pattern)

    # Report progress if context available
    if ctx:
        await ctx.report_progress(progress=0, total=100, message="Buscando lista de métricas...")

    data = make_prometheus_request("label/__name__/values")

    if ctx:
        await ctx.report_progress(progress=50, total=100, message=f"Processando {len(data)} métricas...")

    # Apply filter if provided
    if filter_pattern:
        filtered_data = [m for m in data if filter_pattern.lower() in m.lower()]
        logger.debug("Applied filter", original_count=len(data), filtered_count=len(filtered_data), pattern=filter_pattern)
        data = filtered_data

    total_count = len(data)

    # Apply pagination
    start_idx = offset
    end_idx = offset + limit if limit is not None else len(data)
    paginated_data = data[start_idx:end_idx]

    result = {
        "metrics": paginated_data,
        "total_count": total_count,
        "returned_count": len(paginated_data),
        "offset": offset,
        "has_more": end_idx < total_count
    }

    if ctx:
        await ctx.report_progress(progress=100, total=100, message=f"Obtidas {len(paginated_data)} de {total_count} métricas")

    logger.info("Lista de métricas obtida",
                total_count=total_count,
                returned_count=len(paginated_data),
                offset=offset,
                has_more=result["has_more"])

    return result

@mcp.tool(
    description="Busca métricas por prefixo ou trecho do nome (útil para padrões OpenTelemetry/semconv)",
    annotations={
        "title": "Buscar métricas (prefixo)",
        "icon": "🔎",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def search_metrics(
    prefix: str,
    limit: int = 50,
    offset: int = 0,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """Busca métricas que contenham o prefixo/termo informado (case-insensitive)."""
    logger.info("Buscando métricas por prefixo", prefix=prefix, limit=limit, offset=offset)

    if ctx:
        await ctx.report_progress(progress=0, total=100, message="Buscando métricas...")

    data = get_cached_metrics()
    term = prefix.lower()
    filtered = [m for m in data if term in m.lower()]

    total_count = len(filtered)
    start_idx = offset
    end_idx = offset + limit if limit is not None else len(filtered)
    paginated = filtered[start_idx:end_idx]

    result = {
        "metrics": paginated,
        "total_count": total_count,
        "returned_count": len(paginated),
        "offset": offset,
        "has_more": end_idx < total_count
    }

    if ctx:
        await ctx.report_progress(progress=100, total=100, message=f"Encontradas {len(paginated)} de {total_count} métricas")

    logger.info("Busca de métricas concluída",
                prefix=prefix,
                total_count=total_count,
                returned_count=len(paginated),
                offset=offset,
                has_more=result["has_more"])

    return result

@mcp.tool(
    description="Sugere métricas comuns do OpenTelemetry (semconv) por domínio: http, rpc, db, messaging, process, system, container, k8s",
    annotations={
        "title": "Sugestões semconv",
        "icon": "🧭",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def suggest_semconv(domain: str = "http") -> Dict[str, Any]:
    """Retorna exemplos de métricas semânticas típicas (semconv) para facilitar navegação."""
    domain = domain.lower()
    catalog: Dict[str, list[str]] = {
        "http": [
            "http_server_duration_milliseconds_sum",
            "http_server_duration_milliseconds_count",
            "http_server_active_requests",
            "http_server_request_size",
            "http_server_response_size",
        ],
        "http_client": [
            "http_client_duration_milliseconds_sum",
            "http_client_duration_milliseconds_count",
            "http_client_active_requests",
        ],
        "rpc": [
            "rpc_server_duration_milliseconds_sum",
            "rpc_server_duration_milliseconds_count",
            "rpc_server_active_requests",
        ],
        "db": [
            "db_client_operation_duration_milliseconds_sum",
            "db_client_operation_duration_milliseconds_count",
            "db_client_connections_usage",
        ],
        "messaging": [
            "messaging_operation_duration_milliseconds_sum",
            "messaging_operation_duration_milliseconds_count",
            "messaging_clients_active",
        ],
        "process": [
            "process_runtime_jvm_cpu_utilization" ,
            "process_cpu_seconds_total",
            "process_resident_memory_bytes",
            "process_runtime_go_gc_duration_seconds_sum",
        ],
        "system": [
            "system_cpu_utilization",
            "system_cpu_usage",
            "system_memory_usage",
            "system_memory_utilization",
            "system_filesystem_usage",
            "system_network_io_bytes",
            "system_load_average_1m",
        ],
        "container": [
            "container_cpu_usage_seconds_total",
            "container_memory_usage_bytes",
            "container_memory_working_set_bytes",
            "container_network_receive_bytes_total",
            "container_network_transmit_bytes_total",
        ],
        "k8s": [
            "k8s_pod_cpu_usage",
            "k8s_pod_memory_usage",
            "k8s_node_cpu_utilization",
            "k8s_node_memory_utilization",
            "k8s_container_restarts_total",
        ],
    }
    suggestions = catalog.get(domain, [])
    return {
        "domain": domain,
        "examples": suggestions,
        "known_domains": list(catalog.keys()),
    }

@mcp.tool(
    description="Obtém metadata para uma métrica específica",
    annotations={
        "title": "Metadata da métrica",
        "icon": "ℹ️",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_metric_metadata(metric: str) -> List[Dict[str, Any]]:
    """Obtém metadata sobre uma métrica específica.

    Args:
        metric: The name of the metric to retrieve metadata for

    Returns:
        List of metadata entries for the metric
    """
    logger.info("Retrieving metric metadata", metric=metric)
    endpoint = f"metadata?metric={metric}"
    data = make_prometheus_request(endpoint, params=None)
    if "metadata" in data:
        metadata = data["metadata"]
    elif "data" in data:
        metadata = data["data"]
    else:
        metadata = data
    if isinstance(metadata, dict):
        metadata = [metadata]
    logger.info("Metric metadata retrieved", metric=metric, metadata_count=len(metadata))
    return metadata

@mcp.tool(
    description="Obtém informações sobre todos os targets de scrape",
    annotations={
        "title": "Targets de scrape",
        "icon": "🎯",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_targets() -> Dict[str, List[Dict[str, Any]]]:
    """Obtém informações sobre todos os targets de scrape do Prometheus.

    Returns:
        Dictionary with active and dropped targets information
    """
    logger.info("Recuperando targets de scrape")
    data = make_prometheus_request("targets")
    
    result = {
        "activeTargets": data["activeTargets"],
        "droppedTargets": data["droppedTargets"]
    }
    
    logger.info("Targets de scrape obtidos", 
                active_targets=len(data["activeTargets"]), 
                dropped_targets=len(data["droppedTargets"]))
    
    return result

if __name__ == "__main__":
    logger.info("Starting Prometheus MCP Server", mode="direct")
    mcp.run()
