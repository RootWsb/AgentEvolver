"""Read-only guard — verify that the production skill directory is not writable."""

import os
from pathlib import Path

from agent_evolver.config import get_config

_config = get_config()


def check_production_writable() -> tuple[bool, str]:
    """Return (is_writable, reason).

    In strict mode (evolver_strict_readonly=true), the caller should
    refuse to start if is_writable is True.
    """
    prod = _config.evolver_production_dir

    if not prod.exists():
        return True, f"Production directory does not exist: {prod}"

    # Check write permission at OS level
    try:
        # Try to create and immediately delete a temp file
        test_file = prod / ".evolver_write_test"
        test_file.write_text("")
        test_file.unlink()
        return True, f"Production directory {prod} is WRITABLE — evolution engine must NOT have write access"
    except PermissionError:
        return False, f"Production directory {prod} is read-only — OK"
    except OSError as e:
        return True, f"Could not determine write status for {prod}: {e}"


def assert_production_readonly(strict: bool = False) -> None:
    is_writable, reason = check_production_writable()
    if is_writable:
        msg = f"[EVOLVER SECURITY] {reason}"
        if strict or _config.evolver_strict_readonly:
            raise RuntimeError(f"{msg} Refusing to start in strict mode.")
        # In non-strict mode, just warn
        print(f"WARNING: {msg}")
