"""Small, fail-closed client for Jev's typed judgments (not a news/research API)."""
import json
import math
import os
import time

import requests

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"


class JevError(RuntimeError):
    """Messages deliberately exclude credentials, response bodies and request state."""


def number(value, low=0, high=1):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def validate_answers(payload, questions):
    if not isinstance(payload, dict) or payload.get("model") != MODEL:
        raise JevError("Unexpected model version")
    answers = payload.get("answers", {})
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise JevError("Missing or unexpected judgment")
    for key, q in questions.items():
        a = answers[key]
        if not isinstance(a, dict) or a.get("type") != q["type"]:
            raise JevError("Invalid judgment type")
        if q["type"] != "choice":
            raise JevError("Unsupported judgment type")
        p = a.get("probabilities", {})
        if (a.get("choice") not in q["criteria"] or not number(a.get("confidence"))
                or not isinstance(p, dict) or set(p) != set(q["criteria"])
                or not all(number(v) for v in p.values()) or abs(sum(p.values()) - 1) > .02):
            raise JevError("Invalid choice distribution")
    usage = payload.get("usage", {})
    if not all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens", "output_tokens")):
        raise JevError("Invalid usage accounting")
    return answers


class Client:
    def __init__(self, key=None):
        self._key = key or os.environ.get("TYPESAFE_API_KEY", "")
        if not self._key:
            raise JevError("TYPESAFE_API_KEY is not configured")
        self.input_tokens = self.output_tokens = self.calls = 0

    def ask(self, state, questions):
        body = {"model": MODEL, "state": state, "questions": questions}
        if len(json.dumps(body, ensure_ascii=False).encode()) > 65000:
            raise JevError("Evidence exceeds request budget")
        if self.calls >= 80:
            raise JevError("Briefing request budget reached")
        for attempt in range(3):
            if self.calls >= 80:
                raise JevError("Briefing request budget reached")
            self.calls += 1
            try:
                response = requests.post(API_URL, json=body,
                    headers={"Authorization": "Bearer " + self._key},
                    timeout=(10, 60), allow_redirects=False)
            except requests.RequestException:
                if attempt == 2:
                    raise JevError("Jev network request failed") from None
                time.sleep(2 ** attempt)
                continue
            if response.status_code == 200:
                try:
                    result = response.json()
                except ValueError:
                    raise JevError("Jev returned invalid JSON") from None
                answers = validate_answers(result, questions)
                self.input_tokens += result["usage"]["input_tokens"]
                self.output_tokens += result["usage"]["output_tokens"]
                return answers
            if response.status_code not in (429, 500, 502, 503, 504, 529) or attempt == 2:
                raise JevError("Jev HTTP " + str(response.status_code))
            time.sleep(2 ** attempt)
        raise JevError("Jev request failed")
