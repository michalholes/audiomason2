"""Shadow runner package (planning-only).

This repository already contains the authoritative runner implementation under
"scripts/am_patch/".

Issue #800 introduces a new repo-root package directory named "am_patch/".
Python import resolution would normally cause this directory to shadow the
existing package and break imports such as "am_patch.gates".

To preserve backward compatibility, this repo-root package extends its package
search path to also include "scripts/am_patch". Submodules that do not exist
in this repo-root package will resolve to the existing implementation.

The planning-only runner entrypoint is provided by "python -m am_patch" via
am_patch.__main__.
"""

from __future__ import annotations

from pathlib import Path
import pkgutil

__all__ = ["__version__"]

__version__ = "0.1.0"

# Make this package a multi-location package: repo_root/am_patch + repo_root/scripts/am_patch
_repo_root = Path(__file__).resolve().parents[1]
_scripts_pkg = _repo_root / "scripts" / "am_patch"
if _scripts_pkg.is_dir():
    __path__ = pkgutil.extend_path(__path__, __name__)  # type: ignore[name-defined]
    # mypy: __path__ is a pkgutil.ExtendPath result at runtime.
    __path__.append(str(_scripts_pkg))  # type: ignore[attr-defined]
