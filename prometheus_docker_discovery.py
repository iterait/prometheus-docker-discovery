from typing import Iterable, cast

import prometheus_client
from docker import DockerClient
from docker.models.containers import Container
from fastapi import FastAPI, Response
from pydantic import BaseModel

DISCOVERY_LABEL_PREFIX = "prometheus."
JOB_LABEL = f"{DISCOVERY_LABEL_PREFIX}job"
TARGET_LABELS_PREFIX = f"{DISCOVERY_LABEL_PREFIX}labels."
TARGET_ADDRESS_LABEL = f"{TARGET_LABELS_PREFIX}address"


app = FastAPI()
client = DockerClient.from_env()


class PrometheusMetricsResponse(Response):
    media_type = prometheus_client.CONTENT_TYPE_LATEST


def discover() -> Iterable[Container]:
    containers = cast(list[Container], client.containers.list(all=True))

    for container in containers:
        if JOB_LABEL in container.labels:
            yield container


def target_labels(container: Container) -> dict[str, str]:
    result = dict[str, str]()

    for label_name, label_value in container.labels.items():
        if not label_name.startswith(TARGET_LABELS_PREFIX):
            continue

        label_name = label_name[len(TARGET_LABELS_PREFIX) :]
        result[label_name] = label_value

    return result


class DiscoveredTarget(BaseModel):
    targets: list[str]
    labels: dict[str, str]


@app.get("/targets", response_model=list[DiscoveredTarget])
def get_targets():
    result = list[DiscoveredTarget]()

    for container in discover():
        if not TARGET_ADDRESS_LABEL in container.labels:
            continue

        target = DiscoveredTarget(
            targets=[container.labels[TARGET_ADDRESS_LABEL]],
            labels={
                "job": container.labels[JOB_LABEL],
                "container_name": container.name or "",
                **target_labels(container),
            },
        )

        result.append(target)

    return result


container_memory_usage = prometheus_client.Gauge(
    "docker_container_memory_usage_bytes",
    "Container memory usage (without caches)",
    ["job", "container_name"],
)

container_cpu_usage = prometheus_client.Gauge(
    "docker_container_cpu_usage_percent",
    "Container CPU usage percent (not divided by number of CPU cores)",
    ["job", "container_name"],
)


@app.get("/metrics", response_class=PrometheusMetricsResponse)
def get_metrics():
    """
    Retrieve Prometheus metrics
    """

    container_cpu_usage.clear()
    container_memory_usage.clear()

    for container in discover():
        stats = container.stats(stream=False)

        container_memory_usage.labels(job=container.labels[JOB_LABEL], container_name=container.name or "").set(
            stats["memory_stats"].get("usage", 0) - stats["memory_stats"].get("stats", {}).get("cache", 0)
        )

        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_cpu_delta = stats["cpu_stats"].get("system_cpu_usage", 0) - stats["precpu_stats"].get(
            "system_cpu_usage", 0
        )

        container_cpu_usage.labels(job=container.labels[JOB_LABEL], container_name=container.name or "").set(
            (cpu_delta / system_cpu_delta) * stats["cpu_stats"]["online_cpus"] * 100.0 if system_cpu_delta > 0 else 0
        )

    return PrometheusMetricsResponse(prometheus_client.generate_latest())
