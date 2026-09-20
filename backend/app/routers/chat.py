"""POST /api/chat — ask questions; the model may fetch moves and news via tools."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from ..config import CHAT_MODELS, resolve_chat_model
from ..models import ChatModelOption, ChatRequest, ChatResponse
from ..services import chat as chat_service
from ..services.pipeline import build_ticker_response
from ..services.stocks import StockDataError

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/models", response_model=list[ChatModelOption])
def get_chat_models() -> list[ChatModelOption]:
    """The curated allow-list the frontend selector renders."""
    return [ChatModelOption(**m) for m in CHAT_MODELS]


@router.post("", response_model=ChatResponse)
def post_chat(req: ChatRequest, response: Response) -> ChatResponse:
    response.headers["Cache-Control"] = "no-store"
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

    reply, grounded = chat_service.answer(
        ticker=data.ticker,
        company_name=data.company_name,
        industry=data.industry or data.sector,
        movements=data.movements,
        prices=data.prices,
        message=req.message,
        history=req.history,
        model=model,
    )
    return ChatResponse(reply=reply, grounded=grounded, model=model)
