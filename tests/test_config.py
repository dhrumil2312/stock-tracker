"""Chat-model allow-list resolution and CORS origin parsing."""
from __future__ import annotations

import pytest

from app.config import CHAT_MODEL_IDS, CHAT_MODELS, Settings, resolve_chat_model, settings


def test_resolve_defaults_to_server_model_when_none() -> None:
    assert resolve_chat_model(None) == settings.chat_model


def test_resolve_accepts_allow_listed_model() -> None:
    picked = CHAT_MODELS[0]["id"]
    assert resolve_chat_model(picked) == picked


def test_resolve_rejects_unknown_model() -> None:
    with pytest.raises(ValueError):
        resolve_chat_model("evil/gpt-please-charge-my-card")


def test_default_model_is_in_allow_list() -> None:
    # The client can only pick from the allow-list, so the server default must be in it too.
    assert settings.chat_model in CHAT_MODEL_IDS


def test_allow_list_ids_match_model_entries() -> None:
    assert CHAT_MODEL_IDS == frozenset(m["id"] for m in CHAT_MODELS)


def test_cors_origin_list_splits_and_strips() -> None:
    cfg = Settings(cors_origins="http://a.com, http://b.com ,, ")
    assert cfg.cors_origin_list == ["http://a.com", "http://b.com"]
