"""The packaging contract in `pyproject.toml` and `uv.lock` (spec 0001:
Language, Packaging, Parser isolation, torch builds; verify.md steps 2, 7 to 9).

These read the files directly, so they stay fast and need no network. They
catch an edit that quietly breaks a rule the spec depends on, for example
torch slipping into the core dependencies.
"""

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEAVY = {"torch", "torchvision", "docling", "marker-pdf"}


@pytest.fixture(scope="module")
def pyproject():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def lock():
    return tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))


def _dep_name(spec: str) -> str:
    for sep in "<>=!~;[ ":
        spec = spec.split(sep, 1)[0]
    return spec.strip().lower()


def _lock_packages(lock, name):
    return [p for p in lock["package"] if p["name"] == name]


def test_python_is_pinned_to_3_12_line(pyproject):
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.14"
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12"


def test_console_scripts_point_at_the_cli_and_mcp_entry_points(pyproject):
    assert pyproject["project"]["scripts"] == {
        "parsebench": "parsebench.cli:app",
        "parsebench-mcp": "parsebench.mcp_server:main",
    }


def test_core_dependencies_never_include_a_heavy_parser(pyproject):
    # covers: verify.md step 2 (the core never installs torch)
    core = {_dep_name(d) for d in pyproject["project"]["dependencies"]}

    assert core.isdisjoint(HEAVY)


def test_locked_core_dependencies_never_include_a_heavy_parser(lock):
    # covers: verify.md step 2, checked against the resolved lock too
    (pkg,) = _lock_packages(lock, "parsebench")
    core = {d["name"] for d in pkg["dependencies"]}

    assert core.isdisjoint(HEAVY)


def test_every_parser_extra_is_declared(pyproject):
    # covers: verify.md step 7
    extras = pyproject["project"]["optional-dependencies"]

    assert {"pymupdf", "docling", "marker"} <= set(extras)


def test_every_parser_extra_is_in_the_lock(lock):
    # covers: verify.md step 7
    (pkg,) = _lock_packages(lock, "parsebench")

    assert {"pymupdf", "docling", "marker"} <= set(pkg["optional-dependencies"])


def test_docling_and_marker_are_declared_conflicting(pyproject):
    # covers: verify.md step 8
    conflicts = pyproject["tool"]["uv"]["conflicts"]
    as_sets = [{item["extra"] for item in group} for group in conflicts]

    assert {"docling", "marker"} in as_sets


@pytest.mark.parametrize("pkg", ["torch", "torchvision"])
def test_cpu_wheel_index_applies_only_on_linux(pyproject, pkg):
    # covers: verify.md step 9 (spec torch builds)
    (source,) = pyproject["tool"]["uv"]["sources"][pkg]

    assert source["index"] == "pytorch-cpu"
    assert source["marker"] == "sys_platform == 'linux'"


def test_cpu_wheel_index_is_explicit_so_nothing_else_resolves_from_it(pyproject):
    (index,) = [i for i in pyproject["tool"]["uv"]["index"] if i["name"] == "pytorch-cpu"]

    assert index["url"] == "https://download.pytorch.org/whl/cpu"
    assert index["explicit"] is True


def test_lock_has_pypi_torch_and_linux_only_cpu_torch(lock):
    # covers: verify.md step 9
    torches = _lock_packages(lock, "torch")
    by_source = {t["source"]["registry"]: t for t in torches}

    assert set(by_source) == {
        "https://pypi.org/simple",
        "https://download.pytorch.org/whl/cpu",
    }
    cpu = by_source["https://download.pytorch.org/whl/cpu"]
    assert cpu["version"].endswith("+cpu")
    assert all("sys_platform == 'linux'" in m for m in cpu["resolution-markers"])


def test_build_backend_is_uv_build(pyproject):
    assert pyproject["build-system"]["build-backend"] == "uv_build"


def test_package_ships_a_py_typed_marker():
    assert (ROOT / "src" / "parsebench" / "py.typed").is_file()


@pytest.mark.parametrize(
    "subpackage",
    [
        "schemas",
        "generators",
        "tasks",
        "adapters",
        "workers",
        "answering",
        "harness",
        "scoring",
        "stats",
        "storage",
        "publish",
        "mcp_server",
    ],
)
def test_spec_layout_subpackage_exists(subpackage):
    assert (ROOT / "src" / "parsebench" / subpackage / "__init__.py").is_file()


def test_env_file_is_git_ignored_and_example_is_committed():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in [line.strip() for line in ignored]
    assert (ROOT / ".env.example").is_file()
