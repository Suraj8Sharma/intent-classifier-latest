from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from server.api.chat import router as chat_router

app = FastAPI()
app.include_router(chat_router)


@app.exception_handler(TimeoutError)
async def timeout_error_handler(request: Request, exc: TimeoutError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Inference request exceeded latency budget"},
    )


@app.exception_handler(ConnectionError)
async def connection_error_handler(request: Request, exc: ConnectionError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "System temporarily busy"},
    )
