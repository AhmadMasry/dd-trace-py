"""
This custom pytest plugin implements tracing for pytest by using pytest hooks. The plugin registers tracing code
to be run at specific points during pytest execution. The most important hooks used are:

    * pytest_sessionstart: during pytest session startup, a custom trace filter is configured to the global tracer to
        only send test spans, which are generated by the plugin.
    * pytest_runtest_protocol: this wraps around the execution of a pytest test function, which we trace. Most span
        tags are generated and added in this function. We also store the span on the underlying pytest test item to
        retrieve later when we need to report test status/result.
    * pytest_runtest_makereport: this hook is used to set the test status/result tag, including skipped tests and
        expected failures.

"""
import os
from typing import Dict  # noqa:F401

import pytest

from ddtrace import config
from ddtrace.appsec._iast._pytest_plugin import ddtrace_iast  # noqa:F401
from ddtrace.appsec._iast._utils import _is_iast_enabled
from ddtrace.contrib.internal.pytest._utils import _USE_PLUGIN_V2
from ddtrace.contrib.internal.pytest._utils import _extract_span
from ddtrace.contrib.internal.pytest._utils import _pytest_version_supports_itr


# pytest default settings
config._add(
    "pytest",
    dict(
        _default_service="pytest",
        operation_name=os.getenv("DD_PYTEST_OPERATION_NAME", default="pytest.test"),
    ),
)


DDTRACE_HELP_MSG = "Enable tracing of pytest functions."
NO_DDTRACE_HELP_MSG = "Disable tracing of pytest functions."
DDTRACE_INCLUDE_CLASS_HELP_MSG = "Prepend 'ClassName.' to names of class-based tests."
PATCH_ALL_HELP_MSG = "Call ddtrace.patch_all before running tests."


def is_enabled(config):
    """Check if the ddtrace plugin is enabled."""
    return (config.getoption("ddtrace") or config.getini("ddtrace")) and not config.getoption("no-ddtrace")


def pytest_addoption(parser):
    """Add ddtrace options."""
    group = parser.getgroup("ddtrace")

    group._addoption(
        "--ddtrace",
        action="store_true",
        dest="ddtrace",
        default=False,
        help=DDTRACE_HELP_MSG,
    )

    group._addoption(
        "--no-ddtrace",
        action="store_true",
        dest="no-ddtrace",
        default=False,
        help=NO_DDTRACE_HELP_MSG,
    )

    group._addoption(
        "--ddtrace-patch-all",
        action="store_true",
        dest="ddtrace-patch-all",
        default=False,
        help=PATCH_ALL_HELP_MSG,
    )

    group._addoption(
        "--ddtrace-include-class-name",
        action="store_true",
        dest="ddtrace-include-class-name",
        default=False,
        help=DDTRACE_INCLUDE_CLASS_HELP_MSG,
    )

    group._addoption(
        "--ddtrace-iast-fail-tests",
        action="store_true",
        dest="ddtrace-iast-fail-tests",
        default=False,
        help=DDTRACE_INCLUDE_CLASS_HELP_MSG,
    )

    parser.addini("ddtrace", DDTRACE_HELP_MSG, type="bool")
    parser.addini("no-ddtrace", DDTRACE_HELP_MSG, type="bool")
    parser.addini("ddtrace-patch-all", PATCH_ALL_HELP_MSG, type="bool")
    parser.addini("ddtrace-include-class-name", DDTRACE_INCLUDE_CLASS_HELP_MSG, type="bool")
    if _is_iast_enabled():
        from ddtrace.appsec._iast import _iast_pytest_activation

        _iast_pytest_activation()


# Version-specific pytest hooks
if _USE_PLUGIN_V2:
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_collection_finish  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_configure as _versioned_pytest_configure
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_ddtrace_get_item_module_name  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_ddtrace_get_item_suite_name  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_ddtrace_get_item_test_name  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_load_initial_conftests  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_report_teststatus  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_runtest_makereport  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_runtest_protocol  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_sessionfinish  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_sessionstart  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v2 import pytest_terminal_summary  # noqa: F401
else:
    from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_collection_modifyitems  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_configure as _versioned_pytest_configure
    from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_ddtrace_get_item_module_name  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_ddtrace_get_item_suite_name  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_ddtrace_get_item_test_name  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_load_initial_conftests  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_runtest_makereport  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_runtest_protocol  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_sessionfinish  # noqa: F401
    from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_sessionstart  # noqa: F401

    # Internal coverage is only used for ITR at the moment, so the hook is only added if the pytest version supports it
    if _pytest_version_supports_itr():
        from ddtrace.contrib.internal.pytest._plugin_v1 import pytest_terminal_summary  # noqa: F401


def pytest_configure(config):
    config.addinivalue_line("markers", "dd_tags(**kwargs): add tags to current span")
    if is_enabled(config):
        _versioned_pytest_configure(config)


@pytest.hookimpl
def pytest_addhooks(pluginmanager):
    from ddtrace.contrib.internal.pytest import newhooks

    pluginmanager.add_hookspecs(newhooks)


@pytest.fixture(scope="function")
def ddspan(request):
    """Return the :class:`ddtrace._trace.span.Span` instance associated with the
    current test when Datadog CI Visibility is enabled.
    """
    from ddtrace.internal.ci_visibility import CIVisibility as _CIVisibility

    if _CIVisibility.enabled:
        return _extract_span(request.node)


@pytest.fixture(scope="session")
def ddtracer():
    """Return the :class:`ddtrace.tracer.Tracer` instance for Datadog CI
    visibility if it is enabled, otherwise return the default Datadog tracer.
    """
    import ddtrace
    from ddtrace.internal.ci_visibility import CIVisibility as _CIVisibility

    if _CIVisibility.enabled:
        return _CIVisibility._instance.tracer
    return ddtrace.tracer


@pytest.fixture(scope="session", autouse=True)
def patch_all(request):
    """Patch all available modules for Datadog tracing when ddtrace-patch-all
    is specified in command or .ini.
    """
    import ddtrace

    if request.config.getoption("ddtrace-patch-all") or request.config.getini("ddtrace-patch-all"):
        ddtrace.patch_all()
