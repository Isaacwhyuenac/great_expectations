"""
PyInvoke developer task file
https://www.pyinvoke.org/

These tasks can be run using `invoke <NAME>` or `inv <NAME>` from the project root.

To show all available tasks `invoke --list`

To show task help page `invoke <NAME> --help`
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
from typing import TYPE_CHECKING, Union

import invoke
from typing_extensions import Final

from docs.sphinx_api_docs_source import check_public_api_docstrings, public_api_report
from docs.sphinx_api_docs_source.build_sphinx_api_docs import SphinxInvokeDocsBuilder

try:
    from tests.integration.usage_statistics import usage_stats_utils

    is_ge_installed: bool = True
except ModuleNotFoundError:
    is_ge_installed = False

if TYPE_CHECKING:
    from invoke.context import Context


GX_ROOT_DIR: Final = pathlib.Path(__file__).parent / "great_expectations"

_CHECK_HELP_DESC = "Only checks for needed changes without writing back. Exit with error code if changes needed."
_EXCLUDE_HELP_DESC = "Exclude files or directories"
_PATH_HELP_DESC = "Target path. (Default: .)"
# https://www.pyinvoke.org/faq.html?highlight=pty#why-is-my-command-behaving-differently-under-invoke-versus-being-run-by-hand
_PTY_HELP_DESC = "Whether or not to use a pseudo terminal"


@invoke.task(
    help={
        "check": _CHECK_HELP_DESC,
        "exclude": _EXCLUDE_HELP_DESC,
        "path": _PATH_HELP_DESC,
        "isort": "Use `isort` to sort packages. Default behavior.",
        "ruff": (
            "Use `ruff` instead of `isort` to sort imports."
            " This will eventually become the default."
        ),
        "pty": _PTY_HELP_DESC,
    }
)
def sort(
    ctx: Context,
    path: str = ".",
    check: bool = False,
    exclude: str | None = None,
    ruff: bool = False,  # isort is the current default
    isort: bool = False,
    pty: bool = True,
):
    """Sort module imports."""
    if ruff and isort:
        raise invoke.Exit("cannot use both `--ruff` and `--isort`", code=1)
    if not isort:
        cmds = [
            "ruff",
            path,
            "--select I",
            "--diff" if check else "--fix",
        ]
        if exclude:
            cmds.extend(["--extend-exclude", exclude])
    else:
        cmds = ["isort", path]
        if check:
            cmds.append("--check-only")
        if exclude:
            cmds.extend(["--skip", exclude])
    ctx.run(" ".join(cmds), echo=True, pty=pty)


@invoke.task(
    help={
        "check": _CHECK_HELP_DESC,
        "exclude": _EXCLUDE_HELP_DESC,
        "path": _PATH_HELP_DESC,
        "sort": "Disable import sorting. Runs by default.",
        "pty": _PTY_HELP_DESC,
    }
)
def fmt(
    ctx: Context,
    path: str = ".",
    sort_: bool = True,
    check: bool = False,
    exclude: str | None = None,
    pty: bool = True,
):
    """
    Run code formatter.
    """
    if sort_:
        sort(ctx, path, check=check, exclude=exclude, pty=pty)

    cmds = ["black", path]
    if check:
        cmds.append("--check")
    if exclude:
        cmds.extend(["--exclude", exclude])
    ctx.run(" ".join(cmds), echo=True, pty=pty)


@invoke.task(
    help={
        "path": _PATH_HELP_DESC,
        "fix": "Attempt to automatically fix lint violations.",
        "watch": "Run in watch mode by re-running whenever files change.",
        "pty": _PTY_HELP_DESC,
    }
)
def lint(
    ctx: Context,
    path: str = ".",
    fix: bool = False,
    watch: bool = False,
    pty: bool = True,
):
    """Run formatter (black) and linter (ruff)"""
    fmt(ctx, path, check=not fix, pty=pty)

    # Run code linter (ruff)
    cmds = ["ruff", path]
    if fix:
        cmds.append("--fix")
    if watch:
        cmds.append("--watch")
    ctx.run(" ".join(cmds), echo=True, pty=pty)


@invoke.task(help={"path": _PATH_HELP_DESC})
def fix(ctx: Context, path: str = "."):
    """Automatically fix all possible code issues."""
    lint(ctx, path=path, fix=True)
    fmt(ctx, path=path, sort_=True)


@invoke.task(help={"path": _PATH_HELP_DESC})
def upgrade(ctx: Context, path: str = "."):
    """Run code syntax upgrades."""
    cmds = ["ruff", path, "--select", "UP", "--fix"]
    ctx.run(" ".join(cmds), echo=True, pty=True)


@invoke.task(
    help={
        "all_files": "Run hooks against all files, not just the current changes.",
        "diff": "Show the diff of changes on hook failure.",
        "sync": "Re-install the latest git hooks.",
    }
)
def hooks(
    ctx: Context, all_files: bool = False, diff: bool = False, sync: bool = False
):
    """Run and manage pre-commit hooks."""
    cmds = ["pre-commit", "run"]
    if diff:
        cmds.append("--show-diff-on-failure")
    if all_files:
        cmds.extend(["--all-files"])
    else:
        # used in CI - runs faster and only checks files that have changed
        cmds.extend(["--from-ref", "origin/HEAD", "--to-ref", "HEAD"])

    ctx.run(" ".join(cmds))

    if sync:
        print("  Re-installing hooks ...")
        ctx.run(" ".join(["pre-commit", "uninstall"]), echo=True)
        ctx.run(" ".join(["pre-commit", "install"]), echo=True)


@invoke.task(aliases=("docstring",), iterable=("paths",))
def docstrings(ctx: Context, paths: list[str] | None = None):
    """
    Check public API docstrings.

    Optionally pass a directory or file.
    To pass multiple items:
        invoke docstrings -p=great_expectations/core -p=great_expectations/util.py
    """

    select_paths = [pathlib.Path(p) for p in paths] if paths else None
    try:
        check_public_api_docstrings.main(select_paths=select_paths)
    except AssertionError as err:
        raise invoke.Exit(
            message=f"{err}\n\nGenerated with {check_public_api_docstrings.__file__}",
            code=1,
        )


@invoke.task(
    aliases=["types"],
    iterable=["packages"],
    help={
        "packages": "One or more `great_expectatations` sub-packages to type-check with mypy.",
        "install-types": "Automatically install any needed types from `typeshed`.",
        "daemon": "Run mypy in daemon mode with faster analysis."
        " The daemon will be started and re-used for subsequent calls."
        " For detailed usage see `dmypy --help`.",
        "clear-cache": "Clear the local mypy cache directory.",
        "check-stub-sources": "Check the implementation `.py` files for any `.pyi`"
        " stub files in `great_expectations`."
        " By default `mypy` will not check implementation files if a `.pyi` stub file exists."
        " This should be run in CI in addition to the normal type-checking step.",
        "python-version": "Type check as if running a specific python version. Default 3.8",
    },
)
def type_check(
    ctx: Context,
    packages: list[str],
    install_types: bool = False,
    pretty: bool = False,
    warn_unused_ignores: bool = False,
    daemon: bool = False,
    clear_cache: bool = False,
    report: bool = False,
    check_stub_sources: bool = False,
    ci: bool = False,
    python_version: str = "3.8",
):
    """Run mypy static type-checking on select packages."""
    mypy_cache = pathlib.Path(".mypy_cache")

    if ci:
        mypy_cache.mkdir(exist_ok=True)
        print(f"  mypy cache {mypy_cache.absolute()}")

        type_check(
            ctx,
            packages,
            install_types=True,
            pretty=pretty,
            warn_unused_ignores=True,
            daemon=daemon,
            clear_cache=clear_cache,
            report=report,
            check_stub_sources=check_stub_sources,
            ci=False,
            python_version=python_version,
        )
        return  # don't run twice

    if clear_cache:
        print(f"  Clearing {mypy_cache} ... ", end="")
        try:
            shutil.rmtree(mypy_cache)
            print("✅"),
        except FileNotFoundError as exc:
            print(f"❌\n  {exc}")

    bin = "dmypy run --" if daemon else "mypy"
    ge_pkgs = [f"great_expectations.{p}" for p in packages]

    if check_stub_sources:
        # see --help docs for explanation of this flag
        for stub_file in GX_ROOT_DIR.glob("**/*.pyi"):
            source_file = stub_file.with_name(  # TODO:py3.9 .with_stem()
                f"{stub_file.name[:-1]}"
            )
            relative_path = source_file.relative_to(GX_ROOT_DIR.parent)
            ge_pkgs.append(str(relative_path))

    cmds = [
        bin,
        *ge_pkgs,
    ]
    if install_types:
        cmds.extend(["--install-types", "--non-interactive"])
    if daemon:
        # see related issue https://github.com/python/mypy/issues/9475
        cmds.extend(["--follow-imports=normal"])
    if report:
        cmds.extend(["--txt-report", "type_cov", "--html-report", "type_cov"])
    if pretty:
        cmds.extend(["--pretty"])
    if warn_unused_ignores:
        cmds.extend(["--warn-unused-ignores"])
    if python_version:
        cmds.extend(["--python-version", python_version])
    # use pseudo-terminal for colorized output
    ctx.run(" ".join(cmds), echo=True, pty=True)


@invoke.task(aliases=["get-stats"])
def get_usage_stats_json(ctx: Context):
    """
    Dump usage stats event examples to json file
    """
    if not is_ge_installed:
        raise invoke.Exit(
            message="This invoke task requires Great Expecations to be installed in the environment. Please try again.",
            code=1,
        )

    events = usage_stats_utils.get_usage_stats_example_events()
    version = usage_stats_utils.get_gx_version()

    outfile = f"v{version}_example_events.json"
    with open(outfile, "w") as f:
        json.dump(events, f)

    print(f"File written to '{outfile}'.")


@invoke.task(pre=[get_usage_stats_json], aliases=["move-stats"])
def mv_usage_stats_json(ctx: Context):
    """
    Use databricks-cli lib to move usage stats event examples to dbfs:/
    """
    version = usage_stats_utils.get_gx_version()
    outfile = f"v{version}_example_events.json"
    cmd = "databricks fs cp --overwrite {0} dbfs:/schemas/{0}"
    cmd = cmd.format(outfile)
    ctx.run(cmd)
    print(f"'{outfile}' copied to dbfs.")


UNIT_TEST_DEFAULT_TIMEOUT: float = 2.0


@invoke.task(
    aliases=["test"],
    help={
        "unit": "Runs tests marked with the 'unit' marker. Default behavior.",
        "integration": "Runs integration tests and exclude unit-tests. By default only unit tests are run.",
        "ignore-markers": "Don't exclude any test by not passing any markers to pytest.",
        "slowest": "Report on the slowest n number of tests",
        "ci": "execute tests assuming a CI environment. Publish XML reports for coverage reporting etc.",
        "timeout": f"Fails unit-tests if calls take longer than this value. Default {UNIT_TEST_DEFAULT_TIMEOUT} seconds",
        "html": "Create html coverage report",
        "package": "Run tests on a specific package. Assumes there is a `tests/<PACKAGE>` directory of the same name.",
        "full-cov": "Show coverage report on the entire `great_expectations` package regardless of `--package` param.",
    },
)
def tests(
    ctx: Context,
    unit: bool = True,
    integration: bool = False,
    ignore_markers: bool = False,
    ci: bool = False,
    html: bool = False,
    cloud: bool = True,
    slowest: int = 5,
    timeout: float = UNIT_TEST_DEFAULT_TIMEOUT,
    package: str | None = None,
    full_cov: bool = False,
):
    """
    Run tests. Runs unit tests by default.

    Use `invoke tests -p=<TARGET_PACKAGE>` to run tests on a particular package and measure coverage (or lack thereof).
    """
    markers = []
    if integration:
        markers += ["integration"]
        unit = False
    markers += ["unit" if unit else "not unit"]

    cov_param = "--cov=great_expectations"
    if package and not full_cov:
        cov_param += f"/{package.replace('.', '/')}"

    cmds = [
        "pytest",
        f"--durations={slowest}",
        cov_param,
        "--cov-report term",
        "-vv",
    ]
    if not ignore_markers:
        marker_text = " and ".join(markers)

        cmds += ["-m", f"'{marker_text}'"]
    if unit and not ignore_markers:
        try:
            import pytest_timeout  # noqa: F401

            cmds += [f"--timeout={timeout}"]
        except ImportError:
            print("`pytest-timeout` is not installed, cannot use --timeout")

    if cloud:
        cmds += ["--cloud"]
    if ci:
        cmds += ["--cov-report", "xml"]
    if html:
        cmds += ["--cov-report", "html"]
    if package:
        cmds += [f"tests/{package.replace('.', '/')}"]  # allow `foo.bar`` format
    ctx.run(" ".join(cmds), echo=True, pty=True)


PYTHON_VERSION_DEFAULT: float = 3.8


@invoke.task(
    help={
        "name": "Docker image name.",
        "tag": "Docker image tag.",
        "build": "If True build the image, otherwise run it. Defaults to False.",
        "detach": "Run container in background and print container ID. Defaults to False.",
        "py": f"version of python to use. Default is {PYTHON_VERSION_DEFAULT}",
        "cmd": "Command for docker image. Default is bash.",
        "target": "Set the target build stage to build.",
    }
)
def docker(
    ctx: Context,
    name: str = "gx38local",
    tag: str = "latest",
    build: bool = False,
    detach: bool = False,
    cmd: str = "bash",
    py: float = PYTHON_VERSION_DEFAULT,
    target: str | None = None,
):
    """
    Build or run gx docker image.
    """

    _exit_with_error_if_not_in_repo_root(task_name="docker")

    filedir = os.path.realpath(
        os.path.dirname(os.path.realpath(__file__))  # noqa: PTH120
    )

    cmds = ["docker"]

    if build:
        cmds.extend(
            [
                "buildx",
                "build",
                "-f",
                "docker/Dockerfile.tests",
                f"--tag {name}:{tag}",
                *[
                    f"--build-arg {arg}"
                    for arg in ["SOURCE=local", f"PYTHON_VERSION={py}"]
                ],
                ".",
            ]
        )
        if target:
            cmds.extend(["--target", target])

    else:
        cmds.append("run")
        if detach:
            cmds.append("--detach")
        cmds.extend(
            [
                "-it",
                "--rm",
                "--mount",
                f"type=bind,source={filedir},target=/great_expectations",
                "-w",
                "/great_expectations",
                f"{name}:{tag}",
                f"{cmd}",
            ]
        )

    ctx.run(" ".join(cmds), echo=True, pty=True)


@invoke.task(
    aliases=("schema", "schemas"),
    help={
        "sync": "Update the json schemas at `great_expectations/datasource/fluent/schemas`",
        "indent": "Indent size for nested json objects. Default: 4",
        "clean": "Delete all schema files and sub directories."
        " Can be combined with `--sync` to reset the /schemas dir and remove stale schemas",
    },
)
def type_schema(
    ctx: Context,
    sync: bool = False,
    clean: bool = False,
    indent: int = 4,
):
    """
    Show all the json schemas for Fluent Datasources & DataAssets

    Generate json schema for each Datasource & DataAsset with `--sync`.
    """
    import pandas

    from great_expectations.datasource.fluent import (
        _PANDAS_SCHEMA_VERSION,
        BatchRequest,
        Datasource,
    )
    from great_expectations.datasource.fluent.sources import (
        _iter_all_registered_types,
    )

    schema_dir_root: Final[pathlib.Path] = (
        GX_ROOT_DIR / "datasource" / "fluent" / "schemas"
    )
    if clean:
        file_count = len(list(schema_dir_root.glob("**/*.json")))
        print(f"🗑️ removing schema directory and contents - {file_count} .json files")
        shutil.rmtree(schema_dir_root)

    schema_dir_root.mkdir(exist_ok=True)

    datasource_dir: pathlib.Path = schema_dir_root

    if not sync:
        print("--------------------\nRegistered Fluent types\n--------------------\n")

    name_model = [
        ("BatchRequest", BatchRequest),
        (Datasource.__name__, Datasource),
        *_iter_all_registered_types(),
    ]

    for name, model in name_model:
        if issubclass(model, Datasource):
            datasource_dir = schema_dir_root.joinpath(model.__name__)
            datasource_dir.mkdir(exist_ok=True)
            schema_dir = schema_dir_root
            print("-" * shutil.get_terminal_size()[0])
        else:
            schema_dir = datasource_dir
            print("  ", end="")

        if not sync:
            print(f"{name} - {model.__name__}.json")
            continue

        if (
            datasource_dir.name.startswith("Pandas")
            and _PANDAS_SCHEMA_VERSION != pandas.__version__
        ):
            print(
                f"🙈  {name} - was generated with pandas"
                f" {_PANDAS_SCHEMA_VERSION} but you have {pandas.__version__}; skipping"
            )
            continue

        try:
            schema_path = schema_dir.joinpath(f"{model.__name__}.json")
            json_str: str = model.schema_json(indent=indent) + "\n"

            if schema_path.exists():
                if json_str == schema_path.read_text():
                    print(f"✅  {name} - {schema_path.name} unchanged")
                    continue

            schema_path.write_text(json_str)
            print(f"🔃  {name} - {schema_path.name} schema updated")
        except TypeError as err:
            print(f"❌  {name} - Could not sync schema - {type(err).__name__}:{err}")
    raise invoke.Exit(code=0)


def _exit_with_error_if_not_in_repo_root(task_name: str):
    """Exit if the command was not run from the repository root."""
    filedir = os.path.realpath(
        os.path.dirname(os.path.realpath(__file__))  # noqa: PTH120
    )
    curdir = os.path.realpath(os.getcwd())  # noqa: PTH109
    if filedir != curdir:
        exit_message = f"The {task_name} task must be invoked from the same directory as the tasks.py file at the top of the repo."
        raise invoke.Exit(
            exit_message,
            code=1,
        )


@invoke.task
def api_docs(ctx: Context):
    """Build api documentation."""

    repo_root = pathlib.Path(__file__).parent

    _exit_with_error_if_not_run_from_correct_dir(
        task_name="docs", correct_dir=repo_root
    )
    sphinx_api_docs_source_dir = repo_root / "docs" / "sphinx_api_docs_source"

    doc_builder = SphinxInvokeDocsBuilder(
        ctx=ctx, api_docs_source_path=sphinx_api_docs_source_dir, repo_root=repo_root
    )

    doc_builder.build_docs()


@invoke.task(
    name="docs",
    help={
        "build": "Build docs via yarn build instead of serve via yarn start. Default False.",
        "clean": "Remove directories and files from versioned docs and code. Default False.",
        "start": "Only run yarn start, do not process versions. For example if you have already run invoke docs and just want to serve docs locally for editing.",
        "lint": "Run the linter",
    },
)
def docs(
    ctx: Context,
    build: bool = False,
    clean: bool = False,
    start: bool = False,
    lint: bool = False,
):
    """Build documentation site, including api documentation and earlier doc versions. Note: Internet access required to download earlier versions."""

    repo_root = pathlib.Path(__file__).parent

    _exit_with_error_if_not_run_from_correct_dir(
        task_name="docs", correct_dir=repo_root
    )

    print("Running invoke docs from:", repo_root)
    old_pwd = pathlib.Path.cwd()
    docusaurus_dir = repo_root / "docs/docusaurus"
    os.chdir(docusaurus_dir)
    if clean:
        rm_cmds = ["rm", "-f", "oss_docs_versions.zip", "versions.json"]
        ctx.run(" ".join(rm_cmds), echo=True)
        rm_rf_cmds = [
            "rm",
            "-rf",
            "versioned_code",
            "versioned_docs",
            "versioned_sidebars",
        ]
        ctx.run(" ".join(rm_rf_cmds), echo=True)
    elif lint:
        ctx.run(" ".join(["yarn lint"]), echo=True)
    elif start:
        ctx.run(" ".join(["yarn start"]), echo=True)
    else:
        print("Making sure docusaurus dependencies are installed.")
        ctx.run(" ".join(["yarn install"]), echo=True)

        build_docs_cmd = "../build_docs" if build else "../build_docs_locally.sh"
        print(f"Running {build_docs_cmd} from:", docusaurus_dir)
        ctx.run(build_docs_cmd, echo=True)

    os.chdir(old_pwd)


@invoke.task(
    name="public-api",
    help={
        "write_to_file": "Write items to be addressed to public_api_report.txt, default False",
    },
)
def public_api_task(
    ctx: Context,
    write_to_file: bool = False,
):
    """Generate a report to determine the state of our Public API. Lists classes, methods and functions that are used in examples in our documentation, and any manual includes or excludes (see public_api_report.py). Items listed when generating this report need the @public_api decorator (and a good docstring) or to be excluded from consideration if they are not applicable to our Public API."""

    repo_root = pathlib.Path(__file__).parent

    _exit_with_error_if_not_run_from_correct_dir(
        task_name="public-api", correct_dir=repo_root
    )

    # Docs folder is not reachable from install of Great Expectations
    api_docs_dir = repo_root / "docs" / "sphinx_api_docs_source"
    sys.path.append(str(api_docs_dir.resolve()))

    public_api_report.generate_public_api_report(write_to_file=write_to_file)


def _exit_with_error_if_not_run_from_correct_dir(
    task_name: str, correct_dir: Union[pathlib.Path, None] = None
) -> None:
    """Exit if the command was not run from the correct directory."""
    if not correct_dir:
        correct_dir = pathlib.Path(__file__).parent
    curdir = pathlib.Path.cwd()
    if correct_dir != curdir:
        exit_message = f"The {task_name} task must be invoked from the same directory as the tasks.py file."
        raise invoke.Exit(
            exit_message,
            code=1,
        )


@invoke.task(
    aliases=("links",),
    help={"skip_external": "Skip external link checks (is slow), default is True"},
)
def link_checker(ctx: Context, skip_external: bool = True):
    """Checks the Docusaurus docs for broken links"""
    import docs.checks.docs_link_checker as checker

    path: str = "docs/docusaurus/docs"
    docs_root: str = "docs/docusaurus/docs"
    site_prefix: str = "docs"

    code, message = checker.scan_docs(
        path=path,
        docs_root=docs_root,
        site_prefix=site_prefix,
        skip_external=skip_external,
    )
    raise invoke.Exit(message, code)
