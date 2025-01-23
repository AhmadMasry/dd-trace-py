import itertools
from typing import Any
from typing import Sequence
from typing import Tuple

from ddtrace.appsec._constants import IAST
from ddtrace.appsec._constants import IAST_SPAN_TAGS
from ddtrace.appsec._iast._iast_request_context import is_iast_request_enabled
from ddtrace.appsec._iast._metrics import _set_metric_iast_executed_source
from ddtrace.appsec._iast._metrics import increment_iast_span_metric
from ddtrace.appsec._iast._taint_tracking import OriginType
from ddtrace.appsec._iast._taint_tracking import TaintRange
from ddtrace.appsec._iast._taint_tracking import get_ranges
from ddtrace.appsec._iast._taint_tracking import is_tainted
from ddtrace.appsec._iast._taint_tracking import origin_to_str
from ddtrace.appsec._iast._taint_tracking import set_ranges
from ddtrace.appsec._iast._taint_tracking import set_ranges_from_values
from ddtrace.appsec._iast._taint_tracking._errors import iast_taint_log_error
from ddtrace.internal.logger import get_logger


log = get_logger(__name__)


def is_pyobject_tainted(pyobject: Any) -> bool:
    if not is_iast_request_enabled():
        return False
    if not isinstance(pyobject, IAST.TAINTEABLE_TYPES):  # type: ignore[misc]
        return False

    try:
        return is_tainted(pyobject)
    except ValueError as e:
        iast_taint_log_error("Checking tainted object error: %s" % e)
    return False


def _taint_pyobject_base(pyobject: Any, source_name: Any, source_value: Any, source_origin=None) -> Any:
    if not is_iast_request_enabled():
        return pyobject

    if not isinstance(pyobject, IAST.TAINTEABLE_TYPES):  # type: ignore[misc]
        return pyobject
    # We need this validation in different condition if pyobject is not a text type and creates a side-effect such as
    # __len__ magic method call.
    pyobject_len = 0
    if isinstance(pyobject, IAST.TEXT_TYPES):
        pyobject_len = len(pyobject)
        if pyobject_len == 0:
            return pyobject

    if isinstance(source_name, (bytes, bytearray)):
        source_name = str(source_name, encoding="utf8", errors="ignore")
    if isinstance(source_name, OriginType):
        source_name = origin_to_str(source_name)

    if isinstance(source_value, (bytes, bytearray)):
        source_value = str(source_value, encoding="utf8", errors="ignore")
    if source_origin is None:
        source_origin = OriginType.PARAMETER

    try:
        pyobject_newid = set_ranges_from_values(pyobject, pyobject_len, source_name, source_value, source_origin)
        return pyobject_newid
    except ValueError as e:
        log.debug("Tainting object error (pyobject type %s): %s", type(pyobject), e, exc_info=True)
    return pyobject


def taint_pyobject_with_ranges(pyobject: Any, ranges: Tuple) -> bool:
    if not is_iast_request_enabled():
        return False
    if not isinstance(pyobject, IAST.TAINTEABLE_TYPES):  # type: ignore[misc]
        return False
    try:
        set_ranges(pyobject, ranges)
        return True
    except ValueError as e:
        iast_taint_log_error("Tainting object with ranges error (pyobject type %s): %s" % (type(pyobject), e))
    return False


def get_tainted_ranges(pyobject: Any) -> Tuple:
    if not is_iast_request_enabled():
        return tuple()
    if not isinstance(pyobject, IAST.TAINTEABLE_TYPES):  # type: ignore[misc]
        return tuple()
    try:
        return get_ranges(pyobject)
    except ValueError as e:
        iast_taint_log_error("Get ranges error (pyobject type %s): %s" % (type(pyobject), e))
    return tuple()


def taint_pyobject(pyobject: Any, source_name: Any, source_value: Any, source_origin=None) -> Any:
    try:
        if source_origin is None:
            source_origin = OriginType.PARAMETER

        res = _taint_pyobject_base(pyobject, source_name, source_value, source_origin)
        _set_metric_iast_executed_source(source_origin)
        increment_iast_span_metric(IAST_SPAN_TAGS.TELEMETRY_EXECUTED_SOURCE, source_origin)
        return res
    except ValueError as e:
        log.debug("Tainting object error (pyobject type %s): %s", type(pyobject), e)
    return pyobject


def copy_ranges_to_string(pyobject: str, ranges: Sequence[TaintRange]) -> str:
    # NB this function uses comment-based type annotation because TaintRange is conditionally imported
    if not isinstance(pyobject, IAST.TAINTEABLE_TYPES):  # type: ignore[misc]
        return pyobject

    for r in ranges:
        _is_string_in_source_value = False
        if r.source.value:
            if isinstance(pyobject, (bytes, bytearray)):
                pyobject_str = str(pyobject, encoding="utf8", errors="ignore")
            else:
                pyobject_str = pyobject
            _is_string_in_source_value = pyobject_str in r.source.value

        if _is_string_in_source_value:
            pyobject = _taint_pyobject_base(
                pyobject=pyobject,
                source_name=r.source.name,
                source_value=r.source.value,
                source_origin=r.source.origin,
            )
            break
    else:
        # no total match found, maybe partial match, just take the first one
        pyobject = _taint_pyobject_base(
            pyobject=pyobject,
            source_name=ranges[0].source.name,
            source_value=ranges[0].source.value,
            source_origin=ranges[0].source.origin,
        )
    return pyobject


def copy_ranges_to_iterable_with_strings(iterable, ranges):
    # type: (Sequence[str], Sequence[TaintRange]) -> Sequence[str]
    # NB this function uses comment-based type annotation because TaintRange is conditionally imported
    iterable_type = type(iterable)

    new_result = []
    # do this so it doesn't consume a potential generator
    items, items_backup = itertools.tee(iterable)
    for i in items_backup:
        i = copy_ranges_to_string(i, ranges)
        new_result.append(i)

    return iterable_type(new_result)  # type: ignore[call-arg]