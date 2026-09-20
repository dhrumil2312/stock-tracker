"""POST /api/chat — SSE stream; the model may fetch moves and news via tools."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..config import CHAT_MODELS, resolve_chat_model
from ..models import ChatModelOption, ChatRequest
from ..services import chat as chat_service
from ..services.pipeline import build_ticker_response
from ..services.stocks import StockDataError

router = APIRouter(prefix="/api/chat", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("/models", response_model=list[ChatModelOption])
def get_chat_models() -> list[ChatModelOption]:
    """The curated allow-list the frontend selector renders."""
    return [ChatModelOption(**m) for m in CHAT_MODELS]


@router.post("")
def post_chat(req: ChatRequest) -> StreamingResponse:
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")
    try:
        model = resolve_chat_model(req.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        data = build_ticker_response(req.ticker, include_news=False, threshold=req.threshold)
    except StockDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    def events():
        for event, payload in chat_service.iter_chat_sse(
            ticker=data.ticker,
            company_name=data.company_name,
            industry=data.industry or data.sector,
            movements=data.movements,
            message=req.message,
            history=req.history,
            model=model,
        ):
            yield f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
