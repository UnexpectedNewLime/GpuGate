"""Authentication cases proposed for approval under AGENTS.md.

Reuse CredentialSettings. Watcher may submit/read/cancel-own; operator may use
operator controls only. Stable principal IDs are watcher/operator, independent
of credential rotation. The proposed Authorization value limit is 4096 ASCII
bytes, inclusive. Bearer schemes are case-insensitive with one or more spaces;
tokens remain case-sensitive and must match exactly.
"""

import importlib
import socket
import subprocess
import traceback
from dataclasses import FrozenInstanceError, asdict, replace
from types import ModuleType

import pytest

from gpu_gate.config import CredentialSettings

WATCHER_SECRET = "synthetic-watcher-secret"
OPERATOR_SECRET = "synthetic-operator-secret"


@pytest.fixture(autouse=True)
def forbid_external_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Authentication must not contact services or run commands")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


@pytest.fixture
def auth() -> ModuleType:
    return importlib.import_module("gpu_gate.auth")


@pytest.fixture
def contracts() -> ModuleType:
    return importlib.import_module("gpu_gate.contracts")


@pytest.fixture
def credentials() -> CredentialSettings:
    return CredentialSettings(WATCHER_SECRET, OPERATOR_SECRET)


@pytest.mark.parametrize("role", ["SUBMIT", "READ", "CANCEL_OWN"])
def test_watcher_receives_stable_identity_and_only_job_permissions(
    auth: ModuleType,
    contracts: ModuleType,
    credentials: CredentialSettings,
    role: str,
) -> None:
    principal = auth.authenticate(
        "Bearer " + WATCHER_SECRET, getattr(contracts.Role, role), credentials
    )
    assert isinstance(principal, contracts.Principal)
    assert principal.principal_id == "watcher"
    assert principal.roles == frozenset(
        (contracts.Role.SUBMIT, contracts.Role.READ, contracts.Role.CANCEL_OWN)
    )


def test_operator_receives_a_distinct_identity_and_only_control_permission(
    auth: ModuleType, contracts: ModuleType, credentials: CredentialSettings
) -> None:
    principal = auth.authenticate(
        "Bearer " + OPERATOR_SECRET, contracts.Role.OPERATOR, credentials
    )
    assert isinstance(principal, contracts.Principal)
    assert principal.principal_id == "operator"
    assert principal.roles == frozenset((contracts.Role.OPERATOR,))


def test_principal_is_immutable_and_contains_no_credential(
    auth: ModuleType, contracts: ModuleType, credentials: CredentialSettings
) -> None:
    principal = auth.authenticate(
        "Bearer " + WATCHER_SECRET, contracts.Role.SUBMIT, credentials
    )
    assert isinstance(principal.roles, frozenset)
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        principal.principal_id = "operator"
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        principal.roles = frozenset((contracts.Role.OPERATOR,))
    assert set(asdict(principal)) == {"principal_id", "roles"}
    rendered = repr(principal) + str(asdict(principal))
    for secret in (WATCHER_SECRET, OPERATOR_SECRET):
        assert secret not in rendered


@pytest.mark.parametrize(
    "caller,role",
    [("watcher", "SUBMIT"), ("operator", "OPERATOR")],
)
def test_token_rotation_keeps_identity_and_revokes_the_old_token(
    auth: ModuleType,
    contracts: ModuleType,
    credentials: CredentialSettings,
    caller: str,
    role: str,
) -> None:
    old_token = getattr(credentials, caller)
    required_role = getattr(contracts.Role, role)
    original = auth.authenticate("Bearer " + old_token, required_role, credentials)
    new_token = "rotated-synthetic-" + caller
    rotated = replace(credentials, **{caller: new_token})
    assert auth.authenticate("Bearer " + new_token, required_role, rotated) == original
    with pytest.raises(auth.Unauthenticated):
        auth.authenticate("Bearer " + old_token, required_role, rotated)


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER", "bEaReR"])
@pytest.mark.parametrize("separator", [" ", "   "])
def test_bearer_scheme_casing_and_spaces_preserve_token_identity(
    auth: ModuleType,
    contracts: ModuleType,
    credentials: CredentialSettings,
    scheme: str,
    separator: str,
) -> None:
    principal = auth.authenticate(
        scheme + separator + WATCHER_SECRET, contracts.Role.SUBMIT, credentials
    )
    assert principal.principal_id == "watcher"


def test_valid_bearer_alphabet_and_padding_match_without_rewriting(
    auth: ModuleType, contracts: ModuleType, credentials: CredentialSettings
) -> None:
    token = "AZaz09-._~+/=="
    credentials = replace(credentials, watcher=token)
    assert (
        auth.authenticate(
            "Bearer " + token, contracts.Role.SUBMIT, credentials
        ).principal_id
        == "watcher"
    )
    with pytest.raises(auth.Unauthenticated):
        auth.authenticate(
            "Bearer " + token.rstrip("="), contracts.Role.SUBMIT, credentials
        )


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "",
        "Bearer",
        "Bearer ",
        "Basic " + WATCHER_SECRET,
        WATCHER_SECRET,
        "Bearer" + WATCHER_SECRET,
        " Bearer " + WATCHER_SECRET,
        "Bearer " + WATCHER_SECRET + " ",
        "Bearer\t" + WATCHER_SECRET,
        "Bearer\n" + WATCHER_SECRET,
        "Bearer " + WATCHER_SECRET + "\r\n",
        "Bearer " + WATCHER_SECRET + "\x00",
        "Bearer " + WATCHER_SECRET + ", Bearer " + OPERATOR_SECRET,
        'Bearer "' + WATCHER_SECRET + '"',
        "Bearer synthetic-watcher secret",
        "Bearer synthetic-\u00e9",
        "Bearer synthetic-\ud800",
        "Bearer =invalid",
        "Bearer token=middle",
        "Bearer synthetic-unknown-secret",
        "Bearer " + WATCHER_SECRET.upper(),
        "Bearer " + WATCHER_SECRET + "x",
        "Bearer " + WATCHER_SECRET[:-1],
    ],
)
def test_missing_malformed_and_unknown_credentials_have_the_same_safe_error(
    auth: ModuleType,
    contracts: ModuleType,
    credentials: CredentialSettings,
    authorization: str | None,
) -> None:
    with pytest.raises(auth.Unauthenticated) as baseline:
        auth.authenticate(None, contracts.Role.SUBMIT, credentials)
    with pytest.raises(auth.Unauthenticated) as caught:
        auth.authenticate(authorization, contracts.Role.SUBMIT, credentials)
    assert caught.value.code == "UNAUTHENTICATED"
    assert str(caught.value) == str(baseline.value)
    rendered = "".join(traceback.format_exception(caught.value))
    rendered += str(caught.value) + repr(caught.value) + repr(vars(caught.value))
    for secret in (WATCHER_SECRET, OPERATOR_SECRET, "synthetic-unknown-secret"):
        assert secret not in rendered


@pytest.mark.parametrize(
    "token,role",
    [
        (WATCHER_SECRET, "OPERATOR"),
        (OPERATOR_SECRET, "SUBMIT"),
        (OPERATOR_SECRET, "READ"),
        (OPERATOR_SECRET, "CANCEL_OWN"),
    ],
)
def test_valid_credentials_cannot_cross_the_role_boundary(
    auth: ModuleType,
    contracts: ModuleType,
    credentials: CredentialSettings,
    token: str,
    role: str,
) -> None:
    with pytest.raises(auth.Forbidden) as caught:
        auth.authenticate("Bearer " + token, getattr(contracts.Role, role), credentials)
    assert caught.value.code == "FORBIDDEN"
    rendered = "".join(traceback.format_exception(caught.value))
    rendered += str(caught.value) + repr(caught.value) + repr(vars(caught.value))
    for secret in (WATCHER_SECRET, OPERATOR_SECRET):
        assert secret not in rendered


@pytest.mark.parametrize("role", ["SUBMIT", "OPERATOR"])
def test_unknown_token_is_unauthenticated_regardless_of_required_role(
    auth: ModuleType,
    contracts: ModuleType,
    credentials: CredentialSettings,
    role: str,
) -> None:
    with pytest.raises(auth.Unauthenticated):
        auth.authenticate(
            "Bearer synthetic-unknown-secret",
            getattr(contracts.Role, role),
            credentials,
        )


@pytest.mark.parametrize("size", [4096, 4097])
def test_proposed_header_limit_applies_even_to_a_matching_credential(
    auth: ModuleType,
    contracts: ModuleType,
    credentials: CredentialSettings,
    size: int,
) -> None:
    token = "x" * (size - len("Bearer "))
    credentials = replace(credentials, watcher=token)
    header = "Bearer " + token
    assert len(header.encode("ascii")) == size
    if size == 4096:
        assert (
            auth.authenticate(header, contracts.Role.SUBMIT, credentials).principal_id
            == "watcher"
        )
    else:
        with pytest.raises(auth.Unauthenticated):
            auth.authenticate(header, contracts.Role.SUBMIT, credentials)
