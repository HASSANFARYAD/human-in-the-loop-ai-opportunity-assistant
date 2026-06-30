from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from mcp_shield.config import settings
from mcp_shield.dashboard import router as dashboard_router
from mcp_shield.database import init_db
from mcp_shield.proxy import handle_proxy_request


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="MCP Shield",
    description="Security and governance proxy layer for AI agents",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def catch_all(request: Request) -> Response:
    return await handle_proxy_request(request)


if __name__ == "__main__":
    uvicorn.run(
        "mcp_shield.main:app",
        host=settings.proxy_host,
        port=settings.proxy_port,
        reload=True,
    )
