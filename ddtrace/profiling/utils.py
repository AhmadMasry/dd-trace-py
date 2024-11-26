import logging
import os

from ddtrace.internal import agent


LOG = logging.getLogger(__name__)


def _get_endpoint(tracer, agentless=False) -> str:
    if agentless:
        LOG.warning(
            "Agentless uploading is currently for internal usage only and not officially supported. "
            "You should not enable it unless somebody at Datadog instructed you to do so."
        )
        endpoint = "https://intake.profile.{}".format(os.environ.get("DD_SITE", "datadoghq.com"))
    else:
        tracer_agent_url = tracer.agent_trace_url
        endpoint = tracer_agent_url if tracer_agent_url else agent.get_trace_url()
    return endpoint


def _get_endpoint_path(agentless=False) -> str:
    if agentless:
        endpoint_path = "/api/v2/profile"
    else:
        # path is relative because it is appended to the agent base path
        endpoint_path = "profiling/v1/input"
    return endpoint_path