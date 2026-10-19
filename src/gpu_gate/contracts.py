"""Validate submission input and compute its stable retry identity without I/O."""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256

from gpu_gate.config import Settings

_FIELDS = (
    "incident_job_id",
    "model",
    "prompt",
    "expires_at",
    "start_not_after",
    "max_queue_wait_ms",
)
_MAX_BODY_BYTES = 65_536
_MAX_PROMPT_BYTES = 32_768


class InvalidInput(ValueError):
    """Invalid submission input; messages must never include submitted values."""

    code = "INVALID_INPUT"


class PayloadTooLarge(ValueError):
    """A submission body or decoded prompt exceeds its byte limit."""

    code = "PAYLOAD_TOO_LARGE"


@dataclass(frozen=True)
class SubmitRequest:
    incident_job_id: str
    model: str
    prompt: str = field(repr=False)
    expires_at: datetime
    start_not_after: datetime
    max_queue_wait_ms: int


@dataclass(frozen=True)
class CanonicalSubmission:
    request: SubmitRequest
    canonical_hash: str


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for name, value in pairs:
        if name in result:
            raise InvalidInput("body: duplicate fields are not allowed")
        result[name] = value
    return result


def _reject_constant(value: str) -> None:
    raise InvalidInput("body: non-standard JSON constants are not allowed")


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise InvalidInput(f"{name}: expected a string")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise InvalidInput(f"{name}: expected valid Unicode text") from None
    return value


def _timestamp(value: str, name: str) -> datetime:
    try:
        # fromisoformat normalises overflowing offset minutes instead of rejecting them.
        offset = re.search(r"[+-]\d{2}:?(\d{2})(?::?\d{2})?(?:[.,]\d+)?$", value)
        if offset is not None and int(offset[1]) >= 60:
            raise ValueError
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
        parsed = parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        raise InvalidInput(f"{name}: expected a timezone-aware timestamp") from None
    # The request and hash must describe the same millisecond-precision deadline.
    return parsed.replace(microsecond=parsed.microsecond // 1000 * 1000)


def parse_submission(body: bytes, key: str, settings: Settings) -> CanonicalSubmission:
    """Parse without checking deadline acceptance, which follows retained-key lookup.

    Canonical JSON follows protocol field order, uses compact UTF-8 encoding and
    UTC millisecond timestamps ending in Z. Prompt text is preserved exactly.
    """
    if len(body) > _MAX_BODY_BYTES:
        raise PayloadTooLarge("body: byte limit exceeded")
    try:
        data = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, RecursionError):
        raise InvalidInput("body: expected a valid UTF-8 JSON object") from None
    if not isinstance(data, dict) or set(data) != set(_FIELDS):
        raise InvalidInput("body: expected exactly the submission fields")

    for name in _FIELDS[:-1]:
        _string(data[name], name)
    if not isinstance(key, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key) is None:
        raise InvalidInput("key: invalid idempotency key syntax")
    if data["incident_job_id"] != key:
        raise InvalidInput("incident_job_id: must equal the idempotency key")
    if data["model"] not in settings.models.allowlist:
        raise InvalidInput("model: not in the configured allowlist")
    prompt = data["prompt"]
    if not prompt:
        raise InvalidInput("prompt: must not be empty")
    if len(prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
        raise PayloadTooLarge("prompt: byte limit exceeded")
    wait = data["max_queue_wait_ms"]
    if type(wait) is not int or not 0 <= wait <= 600_000:
        raise InvalidInput("max_queue_wait_ms: expected an integer in 0..600000")

    request = SubmitRequest(
        incident_job_id=key,
        model=data["model"],
        prompt=prompt,
        expires_at=_timestamp(data["expires_at"], "expires_at"),
        start_not_after=_timestamp(data["start_not_after"], "start_not_after"),
        max_queue_wait_ms=wait,
    )
    canonical = {
        "incident_job_id": request.incident_job_id,
        "model": request.model,
        "prompt": request.prompt,
        "expires_at": request.expires_at.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
        "start_not_after": request.start_not_after.isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
        "max_queue_wait_ms": request.max_queue_wait_ms,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return CanonicalSubmission(request, sha256(encoded).hexdigest())
