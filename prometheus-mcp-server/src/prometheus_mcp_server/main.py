#!/usr/bin/env python
import sys
import dotenv
from prometheus_mcp_server.server import mcp, config, TransportType
from prometheus_mcp_server.logging_config import setup_logging

# Initialize structured logging
logger = setup_logging()

def setup_environment():
    if dotenv.load_dotenv():
        logger.info("Configuração de ambiente carregada", source="arquivo .env")
    else:
        logger.info("Configuração de ambiente carregada", source="variáveis de ambiente", note="Nenhum .env encontrado")

    if not config.url:
        logger.error(
            "Configuração obrigatória ausente",
            error="Variável PROMETHEUS_URL não definida",
            suggestion="Defina com a URL do seu servidor Prometheus",
            example="http://seu-prometheus:9090"
        )
        return False
    
    # MCP Server configuration validation
    mcp_config = config.mcp_server_config
    if mcp_config:
        if str(mcp_config.mcp_server_transport).lower() not in TransportType.values():
            logger.error(
                "Transporte MCP inválido",
                error="Variável PROMETHEUS_MCP_SERVER_TRANSPORT inválida",
                suggestion="Defina um dos transportes válidos (http/sse/stdio)",
                example="http"
            )
            return False

        try:
            if mcp_config.mcp_bind_port:
                int(mcp_config.mcp_bind_port)
        except (TypeError, ValueError):
            logger.error(
                "Porta MCP inválida",
                error="Variável PROMETHEUS_MCP_BIND_PORT inválida",
                suggestion="Defina um número inteiro",
                example="8080"
            )
            return False
    
    # Determine authentication method
    auth_method = "none"
    if config.username and config.password:
        auth_method = "basic_auth"
    elif config.token:
        auth_method = "bearer_token"
    
    logger.info(
        "Configuração do Prometheus validada",
        server_url=config.url,
        authentication=auth_method,
        org_id=config.org_id if config.org_id else None
    )
    
    return True

def run_server():
    """Main entry point for the Prometheus MCP Server"""
    # Setup environment
    if not setup_environment():
        logger.error("Falha ao configurar ambiente, saindo")
        sys.exit(1)
    
    mcp_config = config.mcp_server_config
    transport = mcp_config.mcp_server_transport

    http_transports = [TransportType.HTTP.value, TransportType.SSE.value]
    if transport in http_transports:
        mcp.run(transport=transport, host=mcp_config.mcp_bind_host, port=mcp_config.mcp_bind_port)
        logger.info("Starting Prometheus MCP Server", 
                transport=transport, 
                host=mcp_config.mcp_bind_host,
                port=mcp_config.mcp_bind_port)
    else:
        mcp.run(transport=transport)
        logger.info("Iniciando Prometheus MCP Server", transport=transport)

if __name__ == "__main__":
    run_server()
