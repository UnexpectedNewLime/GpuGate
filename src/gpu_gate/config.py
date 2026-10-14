"""Read immutable startup settings; configuration loading performs file I/O only."""

import math
import tomllib
from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit


class ConfigError(ValueError):
    """A configuration error whose message names a field, never its value."""


class SecretReader(Protocol):
    def __call__(self, path: Path) -> str:
        """Read a credential file without logging its contents."""
        ...


@dataclass(frozen=True)
class GpuSettings:
    hold_percent: float
    release_percent: float
    quiet_seconds: float


@dataclass(frozen=True)
class DetectorSettings:
    required_sources: tuple[str, ...]
    gpu_poll_seconds: float
    process_poll_seconds: float
    freshness_seconds: float


@dataclass(frozen=True)
class BackendSettings:
    url: str


@dataclass(frozen=True)
class ServerSettings:
    bind: str
    port: int


@dataclass(frozen=True)
class ModelSettings:
    allowlist: tuple[str, ...]


@dataclass(frozen=True)
class RetentionSettings:
    payload_hours: int
    metadata_days: int


@dataclass(frozen=True)
class CredentialSettings:
    watcher: str = field(repr=False)
    operator: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    ownership: str
    controls: str
    gpu: GpuSettings
    detectors: DetectorSettings
    backend: BackendSettings
    server: ServerSettings
    models: ModelSettings
    retention: RetentionSettings
    credentials: CredentialSettings


def _table(value: object, name: str, required: tuple[str, ...]) -> dict:
    if not isinstance(value, dict):
        raise ConfigError(f"{name or 'config'}: expected a TOML table")
    prefix = f"{name}." if name else ""
    for key in value:
        if key not in required:
            raise ConfigError(f"{prefix}{key}: unknown field")
    for key in required:
        if key not in value:
            raise ConfigError(f"{prefix}{key}: required setting is missing")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name}: expected a nonempty string")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{name}: expected a nonempty list of strings")
    result = tuple(_string(item, name) for item in value)
    if len(set(result)) != len(result):
        raise ConfigError(f"{name}: duplicate entries are not allowed")
    return result


def _number(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name}: expected a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or (positive and value <= 0):
        raise ConfigError(
            f"{name}: expected a finite{' positive' if positive else ''} number"
        )
    return value


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ConfigError(f"{name}: expected an integer in {minimum}..{maximum}")
    return value


def _policy(value: object, name: str, supported: str) -> str:
    if _string(value, name) != supported:
        raise ConfigError(f"{name}: unsupported policy")
    return supported


def _backend_url(value: object) -> str:
    name = "backend.url"
    url = _string(value, name)
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        loopback = hostname == "localhost" or (
            hostname is not None and ip_address(hostname).is_loopback
        )
        valid = (
            parsed.scheme == "http"
            and loopback
            and parsed.port == 11434
            and parsed.path in ("", "/")
            and parsed.username is None
            and parsed.password is None
            and "?" not in url
            and "#" not in url
            and not any(character.isspace() for character in url)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ConfigError(f"{name}: expected the loopback Ollama HTTP endpoint")
    return url


def _bind(value: object) -> str:
    name = "server.bind"
    bind = _string(value, name)
    try:
        address = ip_address(bind)
        # Range validation does not prove this address belongs to the host's
        # tailnet. Routing and authenticated private exposure need deployment checks.
        private = address.is_loopback or address in ip_network("100.64.0.0/10")
    except ValueError:
        private = False
    if not private:
        raise ConfigError(
            f"{name}: expected a loopback or explicit tailnet IPv4 address"
        )
    return bind


def _credential(
    value: object, name: str, directory: Path, secrets: SecretReader
) -> str:
    reference = _string(value, name)
    secret_path = Path(reference)
    if not secret_path.is_absolute():
        secret_path = directory / secret_path
    try:
        secret = secrets(secret_path)
    except Exception:
        # Readers can include credential content in their exception messages.
        # Suppress the original exception in the displayed traceback as well.
        raise ConfigError(f"{name}: could not read credential file") from None
    if not isinstance(secret, str) or not secret.strip():
        raise ConfigError(f"{name}: credential file is empty or invalid")
    return secret


def load_settings(path: Path, secrets: SecretReader) -> Settings:
    """Load once per startup. Relative secret paths are beside the TOML file.

    No configuration value establishes detector coverage, GPU safety or backend
    release. Those remain separate readiness checks in the future runtime.
    """
    try:
        with path.open("rb") as source:
            data = tomllib.load(source)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        raise ConfigError("config: could not read a valid TOML file") from None

    _table(
        data,
        "",
        (
            "ownership",
            "controls",
            "gpu",
            "detectors",
            "backend",
            "server",
            "models",
            "retention",
            "credentials",
        ),
    )
    ownership = _policy(data["ownership"], "ownership", "shared")
    controls = _policy(data["controls"], "controls", "guarded")

    gpu = _table(
        data["gpu"], "gpu", ("hold_percent", "release_percent", "quiet_seconds")
    )
    hold = _number(gpu["hold_percent"], "gpu.hold_percent")
    release = _number(gpu["release_percent"], "gpu.release_percent")
    if not 0 < hold <= 100:
        raise ConfigError("gpu.hold_percent: must be greater than zero and at most 100")
    if not 0 <= release < hold:
        raise ConfigError(
            "gpu.release_percent: must be nonnegative and below hold_percent"
        )
    gpu_settings = GpuSettings(
        hold, release, _number(gpu["quiet_seconds"], "gpu.quiet_seconds", positive=True)
    )

    detectors = _table(
        data["detectors"],
        "detectors",
        (
            "required_sources",
            "gpu_poll_seconds",
            "process_poll_seconds",
            "freshness_seconds",
        ),
    )
    required_sources = _strings(
        detectors["required_sources"], "detectors.required_sources"
    )
    if any(source not in ("gpu", "game_sessions") for source in required_sources):
        raise ConfigError("detectors.required_sources: unsupported source")
    if "gpu" not in required_sources:
        raise ConfigError("detectors.required_sources: gpu observations are required")
    detector_settings = DetectorSettings(
        required_sources,
        _number(
            detectors["gpu_poll_seconds"], "detectors.gpu_poll_seconds", positive=True
        ),
        _number(
            detectors["process_poll_seconds"],
            "detectors.process_poll_seconds",
            positive=True,
        ),
        _number(
            detectors["freshness_seconds"], "detectors.freshness_seconds", positive=True
        ),
    )

    backend = _table(data["backend"], "backend", ("url",))
    backend_settings = BackendSettings(_backend_url(backend["url"]))
    server = _table(data["server"], "server", ("bind", "port"))
    server_settings = ServerSettings(
        _bind(server["bind"]), _integer(server["port"], "server.port", 1, 65535)
    )
    backend_endpoint = urlsplit(backend_settings.url)
    backend_host = backend_endpoint.hostname
    bind_address = ip_address(server_settings.bind)
    if server_settings.port == backend_endpoint.port and (
        (backend_host == "localhost" and bind_address.is_loopback)
        or (
            backend_host is not None
            and backend_host != "localhost"
            and ip_address(backend_host) == bind_address
        )
    ):
        raise ConfigError("server.port: listener conflicts with the Ollama endpoint")
    models = _table(data["models"], "models", ("allowlist",))
    model_settings = ModelSettings(_strings(models["allowlist"], "models.allowlist"))
    retention = _table(
        data["retention"], "retention", ("payload_hours", "metadata_days")
    )
    retention_settings = RetentionSettings(
        _integer(retention["payload_hours"], "retention.payload_hours", 24, 24),
        _integer(retention["metadata_days"], "retention.metadata_days", 7, 7),
    )
    credentials = _table(
        data["credentials"], "credentials", ("watcher_file", "operator_file")
    )
    credential_settings = CredentialSettings(
        _credential(
            credentials["watcher_file"],
            "credentials.watcher_file",
            path.parent,
            secrets,
        ),
        _credential(
            credentials["operator_file"],
            "credentials.operator_file",
            path.parent,
            secrets,
        ),
    )
    if credential_settings.watcher == credential_settings.operator:
        raise ConfigError(
            "credentials.operator_file: watcher and operator credentials must differ"
        )
    return Settings(
        ownership,
        controls,
        gpu_settings,
        detector_settings,
        backend_settings,
        server_settings,
        model_settings,
        retention_settings,
        credential_settings,
    )
