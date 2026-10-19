"""Submission expectations proposed for approval under AGENTS.md.

Selected LLD proposals: ASCII keys of 1..128 characters, prompts of 1..32,768
UTF-8 bytes, bodies up to 65,536 bytes, and queue waits of 0..600,000 ms.
Canonical JSON uses the six protocol fields in their documented order, compact
separators, unescaped Unicode and UTC timestamps with three decimals and Z.
Sub-millisecond timestamps are truncated in both the request and hash. Duplicate
JSON members and non-standard JSON constants are invalid. Deadline acceptance,
including relative ordering and the current-time horizon, belongs to accept_job.
"""

import importlib
import json
import socket
import subprocess
import traceback
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import ModuleType

import pytest

from gpu_gate.config import ModelSettings, Settings, load_settings

ATTEMPT = "12345678-1234-4234-8234-123456789abc"
PRIVATE_PROMPT = "synthetic-private-prompt-🙂"
WATCHER_SECRET = "synthetic-watcher-credential"
OPERATOR_SECRET = "synthetic-operator-credential"
FIELDS = (
    "incident_job_id",
    "model",
    "prompt",
    "expires_at",
    "start_not_after",
    "max_queue_wait_ms",
)


@pytest.fixture(autouse=True)
def forbid_external_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Submission parsing must not contact services or run commands")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


@pytest.fixture
def contracts() -> ModuleType:
    # Keep collection working before the implementation exists.
    return importlib.import_module("gpu_gate.contracts")


@pytest.fixture
def settings() -> Settings:
    example = Path(__file__).resolve().parents[2] / "config.example.toml"
    secrets = {
        "REPLACE_WITH_WATCHER_CREDENTIAL_FILE": WATCHER_SECRET,
        "REPLACE_WITH_OPERATOR_CREDENTIAL_FILE": OPERATOR_SECRET,
    }
    return load_settings(example, lambda path: secrets[path.name])


@pytest.fixture
def payload() -> dict[str, object]:
    return {
        "incident_job_id": ATTEMPT,
        "model": "gpt-oss:20b",
        "prompt": PRIVATE_PROMPT,
        "expires_at": "2026-10-15T02:10:00Z",
        "start_not_after": "2026-10-15T02:05:00Z",
        "max_queue_wait_ms": 30_000,
    }


def encode(payload: object, *, ensure_ascii: bool = False) -> bytes:
    return json.dumps(payload, ensure_ascii=ensure_ascii).encode("utf-8")


def test_valid_submission_returns_immutable_request_and_known_hash(
    contracts: ModuleType, settings: Settings, payload: dict[str, object]
) -> None:
    result = contracts.parse_submission(encode(payload), ATTEMPT, settings)

    assert isinstance(result, contracts.CanonicalSubmission)
    assert isinstance(result.request, contracts.SubmitRequest)
    request = result.request
    assert request.incident_job_id == ATTEMPT
    assert request.model == "gpt-oss:20b"
    assert request.prompt == PRIVATE_PROMPT
    assert request.max_queue_wait_ms == 30_000
    assert type(request.max_queue_wait_ms) is int
    assert request.expires_at == datetime(2026, 10, 15, 2, 10, tzinfo=UTC)
    assert request.start_not_after == datetime(2026, 10, 15, 2, 5, tzinfo=UTC)
    assert request.expires_at.tzinfo is UTC
    assert request.start_not_after.tzinfo is UTC
    expected_json = (
        '{"incident_job_id":"12345678-1234-4234-8234-123456789abc",'
        '"model":"gpt-oss:20b","prompt":"synthetic-private-prompt-🙂",'
        '"expires_at":"2026-10-15T02:10:00.000Z",'
        '"start_not_after":"2026-10-15T02:05:00.000Z",'
        '"max_queue_wait_ms":30000}'
    )
    assert result.canonical_hash == sha256(expected_json.encode("utf-8")).hexdigest()
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        request.prompt = "changed"
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        result.canonical_hash = "changed"
    assert PRIVATE_PROMPT not in repr(result)
    assert PRIVATE_PROMPT not in repr(request)


@pytest.mark.parametrize("missing", FIELDS)
def test_every_field_is_required(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], missing: str
) -> None:
    del payload[missing]
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)


@pytest.mark.parametrize("extra", ["backend_url", "tools", "priority", "format"])
def test_unknown_fields_are_rejected(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], extra: str
) -> None:
    payload[extra] = "untrusted value"
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)


@pytest.mark.parametrize("field", FIELDS[:-1])
@pytest.mark.parametrize("invalid", [None, True, 123, 1.5, [], {}])
def test_string_fields_are_not_coerced(
    contracts: ModuleType,
    settings: Settings,
    payload: dict[str, object],
    field: str,
    invalid: object,
) -> None:
    payload[field] = invalid
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)


@pytest.mark.parametrize("invalid", [True, False, 0.0, 30_000.0, "0", None, [], {}])
def test_queue_wait_requires_an_actual_integer(
    contracts: ModuleType,
    settings: Settings,
    payload: dict[str, object],
    invalid: object,
) -> None:
    payload["max_queue_wait_ms"] = invalid
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)


@pytest.mark.parametrize("wait", [-1, 600_001, 10**100])
def test_proposed_queue_wait_bounds_reject_outside_values(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], wait: int
) -> None:
    payload["max_queue_wait_ms"] = wait
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)


@pytest.mark.parametrize("wait", [0, 1, 600_000])
def test_proposed_queue_wait_boundaries_are_inclusive(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], wait: int
) -> None:
    payload["max_queue_wait_ms"] = wait
    result = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    assert result.request.max_queue_wait_ms == wait


@pytest.mark.parametrize("key", ["a", "AZaz09_-", ATTEMPT, "a" * 128])
def test_proposed_key_syntax_accepts_uuid_and_boundary_lengths(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], key: str
) -> None:
    payload["incident_job_id"] = key
    assert (
        contracts.parse_submission(
            encode(payload), key, settings
        ).request.incident_job_id
        == key
    )


@pytest.mark.parametrize(
    "key", ["", "a" * 129, "\u00e9", "a b", "a.b", "a/b", "a\n", " a"]
)
def test_invalid_keys_are_rejected_even_when_body_matches(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], key: str
) -> None:
    payload["incident_job_id"] = key
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), key, settings)


def test_key_and_attempt_must_match_exactly(
    contracts: ModuleType, settings: Settings, payload: dict[str, object]
) -> None:
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT.upper(), settings)


@pytest.mark.parametrize("model", ["", "GPT-OSS:20B", "gpt-oss:20b ", "qwen3.5:9b"])
def test_model_must_match_configured_allowlist_exactly(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], model: str
) -> None:
    payload["model"] = model
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)


def test_allowlist_is_taken_from_settings_not_fixed_to_initial_model(
    contracts: ModuleType, settings: Settings, payload: dict[str, object]
) -> None:
    settings = replace(settings, models=ModelSettings(("synthetic-model",)))
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)
    payload["model"] = "synthetic-model"
    assert (
        contracts.parse_submission(encode(payload), ATTEMPT, settings).request.model
        == "synthetic-model"
    )


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"{",
        b"{} {}",
        b"null",
        b"[]",
        b"true",
        b'"text"',
        b'{"prompt":"\xff"}',
        '{"prompt":"x"}'.encode("utf-16"),
        b'{"prompt":NaN}',
        b'{"prompt":Infinity}',
        b'{"prompt":-Infinity}',
        b'{"prompt":"\\ud800"}',
        b'{"prompt":"\\udfff"}',
        b'{"prompt":"line\nbreak"}',
        b"[" * 1500 + b"]" * 1500,
    ],
)
def test_invalid_utf8_json_and_non_object_bodies_have_domain_errors(
    contracts: ModuleType, settings: Settings, body: bytes
) -> None:
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(body, ATTEMPT, settings)


@pytest.mark.parametrize("encoding", ["invalid-utf8", "utf16"])
def test_non_utf8_encoding_is_rejected_in_an_otherwise_valid_request(
    contracts: ModuleType,
    settings: Settings,
    payload: dict[str, object],
    encoding: str,
) -> None:
    payload["prompt"] = "synthetic-encoding-marker"
    valid_body = encode(payload)
    contracts.parse_submission(valid_body, ATTEMPT, settings)
    if encoding == "invalid-utf8":
        body = valid_body.replace(b"synthetic-encoding-marker", b"synthetic-\xff")
    else:
        body = valid_body.decode("utf-8").encode("utf-16")
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(body, ATTEMPT, settings)


@pytest.mark.parametrize("field", FIELDS)
def test_duplicate_members_are_rejected_instead_of_silently_overwritten(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], field: str
) -> None:
    body = (
        encode(payload)[:-1]
        + b","
        + encode(field)
        + b":"
        + encode(payload[field])
        + b"}"
    )
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(body, ATTEMPT, settings)


@pytest.mark.parametrize(
    "prompt",
    ["a", " ", "a" * 32_768, "\u00e9" * 16_384, "🙂" * 8192],
    ids=["one-byte", "space", "ascii-limit", "two-byte-limit", "four-byte-limit"],
)
def test_proposed_prompt_limits_count_decoded_utf8_bytes(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], prompt: str
) -> None:
    payload["prompt"] = prompt
    assert (
        contracts.parse_submission(encode(payload), ATTEMPT, settings).request.prompt
        == prompt
    )


def test_empty_prompt_is_invalid_input(
    contracts: ModuleType, settings: Settings, payload: dict[str, object]
) -> None:
    payload["prompt"] = ""
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)


@pytest.mark.parametrize(
    "prompt",
    ["a" * 32_769, "\u00e9" * 16_384 + "a", "🙂" * 8192 + "a"],
    ids=["ascii-over", "two-byte-over", "four-byte-over"],
)
def test_proposed_prompt_limit_rejects_one_extra_utf8_byte(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], prompt: str
) -> None:
    payload["prompt"] = prompt
    with pytest.raises(contracts.PayloadTooLarge):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)


@pytest.mark.parametrize("extra", [0, 1])
def test_proposed_body_limit_counts_wire_bytes_including_multibyte_text(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], extra: int
) -> None:
    body = encode(payload)
    body += b" " * (65_536 + extra - len(body))
    assert len(body) == 65_536 + extra
    if extra:
        with pytest.raises(contracts.PayloadTooLarge):
            contracts.parse_submission(body, ATTEMPT, settings)
    else:
        assert (
            contracts.parse_submission(body, ATTEMPT, settings).request.prompt
            == PRIVATE_PROMPT
        )


def test_escaped_unicode_uses_decoded_prompt_limit_but_wire_body_limit(
    contracts: ModuleType, settings: Settings, payload: dict[str, object]
) -> None:
    payload["prompt"] = "\u00e9" * 16_384
    raw = encode(payload)
    escaped = encode(payload, ensure_ascii=True)
    assert len(raw) < 65_536 < len(escaped)
    assert (
        contracts.parse_submission(raw, ATTEMPT, settings).request.prompt
        == payload["prompt"]
    )
    with pytest.raises(contracts.PayloadTooLarge):
        contracts.parse_submission(escaped, ATTEMPT, settings)


@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"])
def test_unpaired_surrogates_in_an_otherwise_valid_prompt_are_invalid(
    contracts: ModuleType,
    settings: Settings,
    payload: dict[str, object],
    surrogate: str,
) -> None:
    payload["prompt"] = surrogate
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(
            encode(payload, ensure_ascii=True), ATTEMPT, settings
        )


@pytest.mark.parametrize("field", ["expires_at", "start_not_after"])
@pytest.mark.parametrize(
    "timestamp",
    [
        "",
        "2026-10-15",
        "2026-10-15T02:10:00",
        "not-a-date",
        "2026-02-30T02:10:00Z",
        "2026-10-15T02:10:00+25:00",
        "0001-01-01T00:00:00+01:00",
        "9999-12-31T23:59:59-01:00",
    ],
)
def test_timestamps_require_valid_timezone_aware_dates_representable_in_utc(
    contracts: ModuleType,
    settings: Settings,
    payload: dict[str, object],
    field: str,
    timestamp: str,
) -> None:
    payload[field] = timestamp
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)


@pytest.mark.parametrize("field", ["expires_at", "start_not_after"])
@pytest.mark.parametrize(
    "offset", ["+00:60", "-00:60", "+01:99", "-01:99", "+23:60", "-23:60"]
)
def test_invalid_offset_minutes_are_rejected_without_normalisation(
    contracts: ModuleType,
    settings: Settings,
    payload: dict[str, object],
    field: str,
    offset: str,
) -> None:
    payload[field] = "2026-10-15T02:10:00" + offset
    with pytest.raises(contracts.InvalidInput):
        contracts.parse_submission(encode(payload), ATTEMPT, settings)


@pytest.mark.parametrize("field", ["expires_at", "start_not_after"])
@pytest.mark.parametrize(
    "offset,minutes",
    [
        ("+00:00", 0),
        ("-00:00", 0),
        ("+00:59", 59),
        ("-00:59", -59),
        ("+23:59", 1439),
        ("-23:59", -1439),
    ],
)
def test_valid_offset_boundaries_preserve_the_utc_instant_and_hash(
    contracts: ModuleType,
    settings: Settings,
    payload: dict[str, object],
    field: str,
    offset: str,
    minutes: int,
) -> None:
    payload[field] = "2026-10-15T02:10:00" + offset
    result = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    expected = datetime(2026, 10, 15, 2, 10, tzinfo=UTC) - timedelta(minutes=minutes)
    assert getattr(result.request, field) == expected
    payload[field] = expected.isoformat().replace("+00:00", "Z")
    equivalent = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    assert result.request == equivalent.request
    assert result.canonical_hash == equivalent.canonical_hash


@pytest.mark.parametrize(
    "expires,start",
    [
        ("2000-01-01T00:00:00Z", "2000-01-01T00:00:00Z"),
        ("2100-01-01T00:00:00Z", "2099-12-31T23:59:00Z"),
        ("2000-01-01T00:00:00Z", "2100-01-01T00:00:00Z"),
    ],
)
def test_parser_leaves_deadline_acceptance_to_future_idempotency_lookup(
    contracts: ModuleType,
    settings: Settings,
    payload: dict[str, object],
    expires: str,
    start: str,
) -> None:
    payload.update(expires_at=expires, start_not_after=start)
    result = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    assert result.request.expires_at == datetime.fromisoformat(expires)
    assert result.request.start_not_after == datetime.fromisoformat(start)


def test_equivalent_wire_encodings_and_offsets_share_identity(
    contracts: ModuleType, settings: Settings, payload: dict[str, object]
) -> None:
    original = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    payload.update(
        expires_at="2026-10-15T13:10:00.000+11:00",
        start_not_after="2026-10-14T21:05:00.000-05:00",
    )
    reversed_payload = dict(reversed(list(payload.items())))
    body = json.dumps(reversed_payload, ensure_ascii=True, indent=2).encode("utf-8")
    replay = contracts.parse_submission(body, ATTEMPT, settings)
    assert replay.request == original.request
    assert replay.canonical_hash == original.canonical_hash


def test_sub_millisecond_precision_is_truncated_consistently(
    contracts: ModuleType, settings: Settings, payload: dict[str, object]
) -> None:
    payload.update(
        expires_at="2026-10-15T02:10:00.123999Z",
        start_not_after="2026-10-15T02:05:00.456789Z",
    )
    precise = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    assert precise.request.expires_at.microsecond == 123_000
    assert precise.request.start_not_after.microsecond == 456_000
    payload.update(
        expires_at="2026-10-15T02:10:00.123Z",
        start_not_after="2026-10-15T02:05:00.456Z",
    )
    rounded = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    assert precise.request == rounded.request
    assert precise.canonical_hash == rounded.canonical_hash


@pytest.mark.parametrize(
    "field,value",
    [
        ("incident_job_id", "another-attempt"),
        ("model", "synthetic-model"),
        ("prompt", PRIVATE_PROMPT + " "),
        ("expires_at", "2026-10-15T02:10:00.001Z"),
        ("start_not_after", "2026-10-15T02:05:00.001Z"),
        ("max_queue_wait_ms", 30_001),
    ],
)
def test_every_validated_field_contributes_to_identity(
    contracts: ModuleType,
    settings: Settings,
    payload: dict[str, object],
    field: str,
    value: object,
) -> None:
    settings = replace(
        settings, models=ModelSettings(("gpt-oss:20b", "synthetic-model"))
    )
    original = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    payload[field] = value
    changed = contracts.parse_submission(
        encode(payload), payload["incident_job_id"], settings
    )
    assert changed.canonical_hash != original.canonical_hash


@pytest.mark.parametrize(
    "prompt", ["  text\r\n\t", "\u00e9", "e\u0301", "\x00", '{"tools":[]}']
)
def test_prompt_text_is_preserved_without_whitespace_unicode_or_plan_processing(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], prompt: str
) -> None:
    payload["prompt"] = prompt
    original = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    assert original.request.prompt == prompt
    payload["prompt"] = prompt + "\n"
    assert (
        contracts.parse_submission(encode(payload), ATTEMPT, settings).canonical_hash
        != original.canonical_hash
    )


def test_unicode_normalisation_does_not_merge_distinct_prompts(
    contracts: ModuleType, settings: Settings, payload: dict[str, object]
) -> None:
    payload["prompt"] = "\u00e9"
    composed = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    payload["prompt"] = "e\u0301"
    decomposed = contracts.parse_submission(encode(payload), ATTEMPT, settings)
    assert composed.canonical_hash != decomposed.canonical_hash


@pytest.mark.parametrize(
    "case", ["malformed", "unknown", "key", "model", "timestamp", "size"]
)
def test_errors_have_stable_domain_codes_without_sensitive_content(
    contracts: ModuleType, settings: Settings, payload: dict[str, object], case: str
) -> None:
    key = ATTEMPT
    error_type = contracts.InvalidInput
    code = "INVALID_INPUT"
    if case == "unknown":
        payload[WATCHER_SECRET] = OPERATOR_SECRET
    elif case == "key":
        key = WATCHER_SECRET + "/"
    elif case == "model":
        payload["model"] = OPERATOR_SECRET
    elif case == "timestamp":
        payload["expires_at"] = WATCHER_SECRET
    elif case == "size":
        payload["prompt"] = PRIVATE_PROMPT + "a" * 32_768
        error_type = contracts.PayloadTooLarge
        code = "PAYLOAD_TOO_LARGE"
    body = encode(payload)
    if case == "malformed":
        body = body[:-1]
    with pytest.raises(error_type) as caught:
        contracts.parse_submission(body, key, settings)
    assert caught.value.code == code
    rendered = "".join(traceback.format_exception(caught.value))
    rendered += str(caught.value) + repr(caught.value) + repr(vars(caught.value))
    for private in (PRIVATE_PROMPT, WATCHER_SECRET, OPERATOR_SECRET):
        assert private not in rendered
