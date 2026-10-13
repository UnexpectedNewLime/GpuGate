import subprocess
import sys
from pathlib import Path


def test_installed_package_imports_from_outside_checkout(tmp_path: Path) -> None:
    """An editable install must work without the checkout on Python's search path."""
    package_file = Path(__file__).resolve().parents[1] / "src/gpu_gate/__init__.py"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; from pathlib import Path; import gpu_gate; "
            "assert gpu_gate.__file__ is not None, 'Expected a regular package'; "
            "assert Path(gpu_gate.__file__).resolve() == Path(sys.argv[1]).resolve(), "
            "'Import did not resolve to this checkout'; "
            "assert hasattr(gpu_gate, '__path__'), 'Expected a package'",
            str(package_file),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
