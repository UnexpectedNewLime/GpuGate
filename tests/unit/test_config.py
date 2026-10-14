import importlib
import json
import socket
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import ModuleType

import pytest

WATCHER_SECRET = "synthetic-watcher-secret"
OPERATOR_SECRET = "synthetic-operator-secret"

VALID_TOML = """\
ownership = "shared"
controls = "guarded"

[gpu]
hold_percent = 30
release_percent = 10
quiet_seconds = 60

[detectors]
required_sources = ["gpu", "game_sessions"]
gpu_poll_seconds = 1
process_poll_seconds = 2
freshness_seconds = 5

[backend]
url = "http://127.0.0.1:11434"

[server]
bind = "127.0.0.1"
port = 11435

[models]
allowlist = ["gpt-oss:20b"]

[retention]
payload_hours = 24
metadata_days = 7

[credentials]
watcher_file = "watcher.token"
operator_file = "operator.token"
"""


class FakeSecretReader:
    def __init__(self, directory: Path) -> None:
        self.values = {
            directory / "watcher.token": WATCHER_SECRET,
            directory / "operator.token": OPERATOR_SECRET,
        }
        self.calls: list[Path] = []

    def __call__(self, path: Path) -> str:
        self.calls.append(path)
        return self.values[path]


@pytest.fixture(autouse=True)
def forbid_network_and_host_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Configuration loading must only read files")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


@pytest.fixture
def config() -> ModuleType:
    # Import here so missing implementation does not prevent test collection.
    return importlib.import_module("gpu_gate.config")


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "gate.toml"
    path.write_text(VALID_TOML, encoding="utf-8")
    return path


@pytest.fixture
def secrets(config_file: Path) -> FakeSecretReader:
    return FakeSecretReader(config_file.parent)


def test_valid_settings_preserve_explicit_policies_and_read_credentials(
    config: ModuleType, config_file: Path, secrets: FakeSecretReader
) -> None:
    settings = config.load_settings(config_file, secrets)

    assert settings.ownership == "shared"
    assert settings.controls == "guarded"
    assert settings.backend.url == "http://127.0.0.1:11434"
    assert (settings.server.bind, settings.server.port) == ("127.0.0.1", 11435)
    assert settings.models.allowlist == ("gpt-oss:20b",)
    assert settings.detectors.required_sources == ("gpu", "game_sessions")
    assert settings.retention.payload_hours == 24
    assert settings.retention.metadata_days == 7
    assert secrets.calls == [
        config_file.parent / "watcher.token",
        config_file.parent / "operator.token",
    ]
    for value in (WATCHER_SECRET, OPERATOR_SECRET):
        assert value not in repr(settings)
        assert value not in str(settings)
        assert value not in repr(settings.credentials)
        assert value not in str(settings.credentials)


@pytest.mark.parametrize(
    "hold,release,quiet,gpu_poll,process_poll,freshness",
    [(30, 10, 60, 1, 2, 5), (75.5, 25.5, 12.5, 0.5, 1.5, 4.5), (100, 0, 1, 1, 1, 1)],
)
def test_tunable_values_are_preserved(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    hold: float,
    release: float,
    quiet: float,
    gpu_poll: float,
    process_poll: float,
    freshness: float,
) -> None:
    text = VALID_TOML
    for field, old, new in (
        ("hold_percent", 30, hold),
        ("release_percent", 10, release),
        ("quiet_seconds", 60, quiet),
        ("gpu_poll_seconds", 1, gpu_poll),
        ("process_poll_seconds", 2, process_poll),
        ("freshness_seconds", 5, freshness),
    ):
        text = text.replace(f"{field} = {old}\n", f"{field} = {new}\n")
    config_file.write_text(text, encoding="utf-8")

    settings = config.load_settings(config_file, secrets)

    assert settings.gpu.hold_percent == hold
    assert settings.gpu.release_percent == release
    assert settings.gpu.quiet_seconds == quiet
    assert settings.detectors.gpu_poll_seconds == gpu_poll
    assert settings.detectors.process_poll_seconds == process_poll
    assert settings.detectors.freshness_seconds == freshness


@pytest.mark.parametrize(
    "old,new,field",
    [
        ("hold_percent = 30", "hold_percent = 101", "gpu.hold_percent"),
        ("release_percent = 10", "release_percent = -1", "gpu.release_percent"),
        ("release_percent = 10", "release_percent = 30", "gpu.release_percent"),
        ("release_percent = 10", "release_percent = 31", "gpu.release_percent"),
        ("hold_percent = 30", "hold_percent = true", "gpu.hold_percent"),
        ("release_percent = 10", "release_percent = false", "gpu.release_percent"),
        ("hold_percent = 30", 'hold_percent = "30"', "gpu.hold_percent"),
    ],
)
def test_invalid_thresholds_name_the_field(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    old: str,
    new: str,
    field: str,
) -> None:
    config_file.write_text(VALID_TOML.replace(old, new), encoding="utf-8")

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert field in str(caught.value)


@pytest.mark.parametrize(
    "section,field,old",
    [
        ("gpu", "quiet_seconds", 60),
        ("detectors", "gpu_poll_seconds", 1),
        ("detectors", "process_poll_seconds", 2),
        ("detectors", "freshness_seconds", 5),
    ],
)
@pytest.mark.parametrize("invalid", ["0", "-1", "nan", "inf", "-inf", "true", '"1"'])
def test_every_duration_requires_a_finite_positive_number(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    section: str,
    field: str,
    old: int,
    invalid: str,
) -> None:
    config_file.write_text(
        VALID_TOML.replace(f"{field} = {old}\n", f"{field} = {invalid}\n"),
        encoding="utf-8",
    )

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert f"{section}.{field}" in str(caught.value)


@pytest.mark.parametrize(
    "removed,field",
    [
        ('ownership = "shared"\n', "ownership"),
        ('controls = "guarded"\n', "controls"),
        ("hold_percent = 30\n", "gpu.hold_percent"),
        ('required_sources = ["gpu", "game_sessions"]\n', "detectors.required_sources"),
        ('allowlist = ["gpt-oss:20b"]\n', "models.allowlist"),
        ("payload_hours = 24\n", "retention.payload_hours"),
        ("metadata_days = 7\n", "retention.metadata_days"),
        ('bind = "127.0.0.1"\n', "server.bind"),
        ('watcher_file = "watcher.token"\n', "credentials.watcher_file"),
    ],
)
def test_required_settings_have_no_silent_defaults(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    removed: str,
    field: str,
) -> None:
    config_file.write_text(VALID_TOML.replace(removed, ""), encoding="utf-8")

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert field in str(caught.value)


def test_gpu_observations_cannot_be_removed_from_required_sources(
    config: ModuleType, config_file: Path, secrets: FakeSecretReader
) -> None:
    config_file.write_text(
        VALID_TOML.replace(
            'required_sources = ["gpu", "game_sessions"]',
            'required_sources = ["game_sessions"]',
        ),
        encoding="utf-8",
    )

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert "detectors.required_sources" in str(caught.value)


def test_requiring_gpu_does_not_make_the_proposed_session_veto_mandatory(
    config: ModuleType, config_file: Path, secrets: FakeSecretReader
) -> None:
    config_file.write_text(
        VALID_TOML.replace(
            'required_sources = ["gpu", "game_sessions"]',
            'required_sources = ["gpu"]',
        ),
        encoding="utf-8",
    )

    assert config.load_settings(config_file, secrets).detectors.required_sources == (
        "gpu",
    )


@pytest.mark.parametrize(
    "old,new,field",
    [
        ('ownership = "shared"', 'ownership = "exclusive"', "ownership"),
        ('controls = "guarded"', 'controls = "force_idle"', "controls"),
        ("payload_hours = 24", "payload_hours = 48", "retention.payload_hours"),
        ("metadata_days = 7", "metadata_days = 0", "retention.metadata_days"),
        ("payload_hours = 24", "payload_hours = true", "retention.payload_hours"),
        ('allowlist = ["gpt-oss:20b"]', "allowlist = []", "models.allowlist"),
        ('allowlist = ["gpt-oss:20b"]', "allowlist = [12]", "models.allowlist"),
        (
            'required_sources = ["gpu", "game_sessions"]',
            "required_sources = []",
            "detectors.required_sources",
        ),
        ("port = 11435", "port = true", "server.port"),
        ("port = 11435", "port = 65536", "server.port"),
    ],
)
def test_invalid_policies_lists_and_port_are_rejected(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    old: str,
    new: str,
    field: str,
) -> None:
    config_file.write_text(VALID_TOML.replace(old, new), encoding="utf-8")

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert field in str(caught.value)


@pytest.mark.parametrize(
    "text,field",
    [
        ("unexpected = 1\n" + VALID_TOML, "unexpected"),
        (
            VALID_TOML.replace("hold_percent = 30", "hold_percent = 30\nextra = 1"),
            "gpu.extra",
        ),
        (VALID_TOML + "\n[unknown]\nvalue = 1\n", "unknown"),
    ],
    ids=["unknown-root-field", "unknown-gpu-field", "unknown-section"],
)
def test_unknown_fields_and_sections_are_rejected(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    text: str,
    field: str,
) -> None:
    config_file.write_text(text, encoding="utf-8")

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert field in str(caught.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.20:11434",
        "http://[::ffff:192.168.1.20]:11434",
        "https://example.com:11434",
        "http://127.0.0.1:11434?token=" + WATCHER_SECRET,
        "http://127.0.0.1:11434#" + WATCHER_SECRET,
        "http://user:" + WATCHER_SECRET + "@127.0.0.1:11434",
        "file:///tmp/ollama",
        "not-a-url",
    ],
)
def test_backend_urls_cannot_redirect_inference_or_expose_secrets(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    url: str,
) -> None:
    config_file.write_text(
        VALID_TOML.replace("http://127.0.0.1:11434", url), encoding="utf-8"
    )

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert "backend.url" in str(caught.value)
    assert WATCHER_SECRET not in str(caught.value)
    assert WATCHER_SECRET not in repr(caught.value)


@pytest.mark.parametrize("position", ["leading", "middle", "trailing"])
@pytest.mark.parametrize(
    "control",
    [chr(code) for code in range(32)] + [chr(127)],
    ids=[f"ascii-{code:02x}" for code in range(32)] + ["ascii-7f"],
)
def test_backend_url_rejects_ascii_control_characters_in_every_position(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    control: str,
    position: str,
) -> None:
    base_url = "http://127.0.0.1:11434"
    url = {
        "leading": control + base_url,
        "middle": "http://127.0.0." + control + "1:11434",
        "trailing": base_url + control,
    }[position]
    config_file.write_text(
        VALID_TOML.replace(json.dumps(base_url), json.dumps(url)), encoding="utf-8"
    )

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert "backend.url" in str(caught.value)
    assert secrets.calls == []


@pytest.mark.parametrize("bind", ["0.0.0.0", "::", "8.8.8.8", "192.168.1.20"])
def test_public_wildcard_and_lan_bind_addresses_are_rejected(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    bind: str,
) -> None:
    config_file.write_text(
        VALID_TOML.replace('bind = "127.0.0.1"', f'bind = "{bind}"'),
        encoding="utf-8",
    )

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert "server.bind" in str(caught.value)


def test_explicit_tailnet_bind_is_accepted_without_network_discovery(
    config: ModuleType, config_file: Path, secrets: FakeSecretReader
) -> None:
    config_file.write_text(
        VALID_TOML.replace('bind = "127.0.0.1"', 'bind = "100.100.100.100"'),
        encoding="utf-8",
    )

    assert config.load_settings(config_file, secrets).server.bind == "100.100.100.100"


@pytest.mark.parametrize(
    "backend_host,bind",
    [
        ("127.0.0.1", "127.0.0.1"),
        ("[0:0:0:0:0:0:0:1]", "::1"),
        ("[::ffff:127.0.0.1]", "127.0.0.1"),
        ("127.0.0.1", "::ffff:127.0.0.1"),
    ],
    ids=[
        "same-ipv4-endpoint",
        "equivalent-ipv6-endpoint",
        "mapped-backend-ipv4-listener",
        "ipv4-backend-mapped-listener",
    ],
)
def test_gate_listener_cannot_use_the_configured_ollama_endpoint(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    backend_host: str,
    bind: str,
) -> None:
    config_file.write_text(
        VALID_TOML.replace(
            'url = "http://127.0.0.1:11434"',
            f'url = "http://{backend_host}:11434"',
        )
        .replace('bind = "127.0.0.1"', f'bind = "{bind}"')
        .replace("port = 11435", "port = 11434"),
        encoding="utf-8",
    )

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert "server.port" in str(caught.value)


@pytest.mark.parametrize("bind", ["100.100.100.100", "127.0.0.2"])
def test_ollama_port_is_allowed_on_a_separate_explicit_address(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    bind: str,
) -> None:
    config_file.write_text(
        VALID_TOML.replace('bind = "127.0.0.1"', f'bind = "{bind}"').replace(
            "port = 11435", "port = 11434"
        ),
        encoding="utf-8",
    )

    settings = config.load_settings(config_file, secrets)

    assert settings.server.bind == bind
    assert settings.server.port == 11434


@pytest.mark.parametrize(
    "backend_host,bind,port",
    [
        ("[::ffff:127.0.0.1]", "127.0.0.1", 11435),
        ("[::ffff:127.0.0.1]", "100.100.100.100", 11434),
        ("127.0.0.1", "::ffff:127.0.0.1", 11435),
    ],
    ids=["different-port", "different-address", "mapped-listener-different-port"],
)
def test_mapped_loopback_addresses_are_allowed_without_an_endpoint_collision(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    backend_host: str,
    bind: str,
    port: int,
) -> None:
    config_file.write_text(
        VALID_TOML.replace(
            'url = "http://127.0.0.1:11434"',
            f'url = "http://{backend_host}:11434"',
        )
        .replace('bind = "127.0.0.1"', f'bind = "{bind}"')
        .replace("port = 11435", f"port = {port}"),
        encoding="utf-8",
    )

    settings = config.load_settings(config_file, secrets)

    assert settings.backend.url == f"http://{backend_host}:11434"
    assert (settings.server.bind, settings.server.port) == (bind, port)


@pytest.mark.parametrize("field", ["backend.url", "server.bind"])
@pytest.mark.parametrize("port", [11434, 11435], ids=["same-port", "different-port"])
@pytest.mark.parametrize(
    "scoped",
    ["::1%1", "::1%lo", "::1%251", "::ffff:127.0.0.1%1"],
    ids=["numeric-scope", "named-scope", "uri-encoded-scope", "mapped-scope"],
)
def test_ipv6_scopes_are_rejected_in_backend_and_listener_settings(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    field: str,
    port: int,
    scoped: str,
) -> None:
    unscoped = scoped.split("%", 1)[0]
    backend_host = scoped if field == "backend.url" else unscoped
    bind = scoped if field == "server.bind" else unscoped
    config_file.write_text(
        VALID_TOML.replace(
            'url = "http://127.0.0.1:11434"',
            f'url = "http://[{backend_host}]:11434"',
        )
        .replace('bind = "127.0.0.1"', f'bind = "{bind}"')
        .replace("port = 11435", f"port = {port}"),
        encoding="utf-8",
    )

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert field in str(caught.value)


@pytest.mark.parametrize("text", ["[gpu\n", "\xff", 'ownership = "' + WATCHER_SECRET])
def test_unreadable_toml_has_a_safe_file_error(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    text: str,
) -> None:
    config_file.write_bytes(text.encode("latin-1"))

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert "config" in str(caught.value).lower()
    assert WATCHER_SECRET not in str(caught.value)


def test_missing_configuration_file_has_a_domain_error(
    config: ModuleType, tmp_path: Path
) -> None:
    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(tmp_path / "missing.toml", FakeSecretReader(tmp_path))

    assert "config" in str(caught.value).lower()


def test_secret_reader_failures_do_not_leak_exception_content(
    config: ModuleType, config_file: Path
) -> None:
    def denied(path: Path) -> str:
        raise PermissionError(WATCHER_SECRET)

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, denied)

    assert "credentials.watcher_file" in str(caught.value)
    assert WATCHER_SECRET not in str(caught.value)


@pytest.mark.parametrize("value", ["", "   ", "\n", "\r\n", " \t\r\n"])
def test_empty_credentials_are_rejected(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    value: str,
) -> None:
    secrets.values[config_file.parent / "watcher.token"] = value

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert "credentials.watcher_file" in str(caught.value)


@pytest.mark.parametrize("padding", ["\n", "\r\n", " \t"], ids=["lf", "crlf", "spaces"])
def test_credential_file_whitespace_is_removed_before_storage(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    padding: str,
) -> None:
    secrets.values[config_file.parent / "watcher.token"] = (
        f"{padding}{WATCHER_SECRET}{padding}"
    )
    secrets.values[config_file.parent / "operator.token"] = (
        f"{padding}{OPERATOR_SECRET}{padding}"
    )

    settings = config.load_settings(config_file, secrets)

    assert settings.credentials.watcher == WATCHER_SECRET
    assert settings.credentials.operator == OPERATOR_SECRET


@pytest.mark.parametrize("role", ["watcher", "operator"])
@pytest.mark.parametrize(
    "invalid",
    ["\n", "\r", "\r\n", "\t", "\x00", " ", "é", "="],
    ids=["lf", "cr", "crlf", "tab", "nul", "space", "non-ascii", "internal-padding"],
)
def test_invalid_bearer_credential_characters_are_rejected_without_leaking_tokens(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    role: str,
    invalid: str,
) -> None:
    token = f"synthetic{invalid}extra"
    secrets.values[config_file.parent / f"{role}.token"] = token

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert f"credentials.{role}_file" in str(caught.value)
    assert token not in str(caught.value)
    assert token not in repr(caught.value)


@pytest.mark.parametrize("role", ["watcher", "operator"])
def test_valid_bearer_alphabet_and_trailing_padding_are_preserved(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    role: str,
) -> None:
    token = "AZaz09-._~+/=="
    secrets.values[config_file.parent / f"{role}.token"] = f" \t{token}\r\n"

    settings = config.load_settings(config_file, secrets)

    assert getattr(settings.credentials, role) == token


@pytest.mark.parametrize(
    "watcher_padding,operator_padding",
    [("", "\n"), ("\n", "\r\n"), (" \t", "")],
    ids=["plain-vs-lf", "lf-vs-crlf", "spaces-vs-plain"],
)
def test_credentials_that_match_after_trimming_are_rejected_without_leaking_tokens(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    watcher_padding: str,
    operator_padding: str,
) -> None:
    secrets.values[config_file.parent / "watcher.token"] = (
        f"{watcher_padding}{WATCHER_SECRET}{watcher_padding}"
    )
    secrets.values[config_file.parent / "operator.token"] = (
        f"{operator_padding}{WATCHER_SECRET}{operator_padding}"
    )

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert "credentials.operator_file" in str(caught.value)
    assert WATCHER_SECRET not in str(caught.value)
    assert WATCHER_SECRET not in repr(caught.value)


@pytest.mark.parametrize("same_file", [False, True], ids=["same-content", "same-file"])
def test_watcher_and_operator_cannot_share_a_credential(
    config: ModuleType,
    config_file: Path,
    secrets: FakeSecretReader,
    same_file: bool,
) -> None:
    if same_file:
        config_file.write_text(
            VALID_TOML.replace(
                'operator_file = "operator.token"', 'operator_file = "watcher.token"'
            ),
            encoding="utf-8",
        )
    else:
        secrets.values[config_file.parent / "operator.token"] = WATCHER_SECRET

    with pytest.raises(config.ConfigError) as caught:
        config.load_settings(config_file, secrets)

    assert "credentials.operator_file" in str(caught.value)
    for value in (WATCHER_SECRET, OPERATOR_SECRET):
        assert value not in str(caught.value)
        assert value not in repr(caught.value)


def test_settings_are_immutable_and_file_edits_require_another_load(
    config: ModuleType, config_file: Path, secrets: FakeSecretReader
) -> None:
    original = config.load_settings(config_file, secrets)

    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        original.ownership = "exclusive"
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        original.gpu.hold_percent = 80
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        original.models.allowlist += ("another-model",)

    config_file.write_text(
        VALID_TOML.replace("hold_percent = 30", "hold_percent = 80"),
        encoding="utf-8",
    )
    reloaded = config.load_settings(config_file, secrets)

    assert original.gpu.hold_percent == 30
    assert reloaded.gpu.hold_percent == 80
