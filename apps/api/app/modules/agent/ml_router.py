from __future__ import annotations

import json
import logging
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from agent_core.contracts import RouteDecision
from agent_core.registry import TOOL_NAMES
from agent_core.router import RuleRouter
from app.core.config import settings

_LOGGER = logging.getLogger(__name__)
from tokenizers import Tokenizer


class OnnxIntentClassifier:
    def __init__(
        self,
        *,
        model_path: str,
        tokenizer_path: str,
        label_map_path: str,
    ) -> None:
        self.model_path = Path(model_path)
        self.tokenizer_path = Path(tokenizer_path)
        self.label_map_path = Path(label_map_path)
        self._tokenizer: Tokenizer | None = None
        self._session: ort.InferenceSession | None = None
        self._labels: list[str] = []
        self._lock = threading.Lock()

    def _load(self) -> None:
        if self._session is not None:
            return
        with self._lock:
            if self._session is not None:
                return
            label_map = json.loads(self.label_map_path.read_text(encoding="utf-8"))
            self._labels = [
                label_map["id_to_label"][str(index)]
                for index in range(len(label_map["label_to_id"]))
            ]
            self._tokenizer = Tokenizer.from_file(str(self.tokenizer_path))
            self._session = ort.InferenceSession(
                str(self.model_path),
                providers=["CPUExecutionProvider"],
            )

    def predict(self, text: str) -> tuple[str, float] | None:
        self._load()
        if self._tokenizer is None or self._session is None or not text.strip():
            return None
        encoding = self._tokenizer.encode(text)
        input_ids = np.asarray([encoding.ids], dtype="int64")
        token_type_ids = np.asarray([encoding.type_ids], dtype="int64")
        output_name = self._session.get_outputs()[0].name
        logits = self._session.run(
            [output_name],
            {"input_ids": input_ids, "token_type_ids": token_type_ids},
        )[0][0]
        shifted = np.exp(logits - np.max(logits))
        probabilities = shifted / shifted.sum()
        index = int(np.argmax(probabilities))
        return self._labels[index], float(probabilities[index])


class MlAssistedRouter:
    def __init__(self, rule_router: RuleRouter, classifier: OnnxIntentClassifier | None) -> None:
        self.rule_router = rule_router
        self.classifier = classifier

    def route(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        known_provinces: list[str] | tuple[str, ...] = (),
        known_majors: list[str] | tuple[str, ...] = (),
        latest_year: int | None = None,
        current_year: int = 2026,
    ) -> RouteDecision:
        decision = self.rule_router.route(
            message,
            context=context,
            known_provinces=known_provinces,
            known_majors=known_majors,
            latest_year=latest_year,
            current_year=current_year,
        )
        if self.classifier is None or decision.intent != "admissions_overview":
            return decision
        if any(
            keyword in decision.normalized_message
            for keyword in ("招生计划", "计划招生", "招生多少人", "招生人数", "录取多少人")
        ):
            return decision
        try:
            prediction = self.classifier.predict(decision.normalized_message)
        except Exception:
            _LOGGER.warning("ONNX intent router unavailable; falling back to rule routing", exc_info=True)
            return decision
        if prediction is None:
            return decision
        intent, confidence = prediction
        if intent not in TOOL_NAMES or intent == "admissions_overview":
            return decision
        if confidence < settings.router_ml_confidence_threshold:
            return decision
        decision.intent = intent
        decision.confidence = "high" if confidence >= 0.65 else "normal"
        decision.reasons.append(f"ml_intent={intent};confidence={confidence:.4f}")
        decision.clarification = self.rule_router._clarification(
            decision.intent,
            decision.params,
            decision.normalized_message,
        )
        return decision

@lru_cache(maxsize=1)
def build_ml_router() -> MlAssistedRouter:
    classifier = None
    if settings.router_ml_enabled:
        classifier = OnnxIntentClassifier(
            model_path=settings.router_ml_model_path,
            tokenizer_path=settings.router_ml_tokenizer_path,
            label_map_path=settings.router_ml_label_map_path,
        )
    return MlAssistedRouter(RuleRouter(), classifier)


def clear_ml_router_cache() -> None:
    build_ml_router.cache_clear()
