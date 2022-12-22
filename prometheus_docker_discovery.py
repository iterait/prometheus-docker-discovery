from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, cast

import prometheus_client
from docker import DockerClient
from docker.models.containers import Container
from fastapi import FastAPI, Response
from pydantic import BaseModel

DISCOVERY_LABEL_PREFIX = "prometheus."
JOB_LABEL = f"{DISCOVERY_LABEL_PREFIX}job"
TARGET_LABELS_PREFIX = f"{DISCOVERY_LABEL_PREFIX}labels."
TARGET_PORT_LABEL = f"{DISCOVERY_LABEL_PREFIX}metrics.port"
TARGET_HOST_LABEL = f"{DISCOVERY_LABEL_PREFIX}metrics.host"


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
        if not TARGET_PORT_LABEL in container.labels:
            continue

        port = container.labels[TARGET_PORT_LABEL]
        host = container.labels.get(TARGET_HOST_LABEL)

        if container.ports and (port_spec := container.ports.get(f"{port}/tcp")) is not None:
            port = port_spec[0]["HostPort"]

            if not host:
                host = port_spec[0]["HostIp"]

        if not host or not port:
            continue

        target = DiscoveredTarget(
            targets=[f"{host}:{port}"],
            labels={
                "job": container.labels[JOB_LABEL],
                "container_name": container.name or "",
                **target_labels(container),
            },
        )

        result.append(target)

    return result


@app.get("/metrics", response_class=PrometheusMetricsResponse)
def get_metrics():
    """
    Retrieve Prometheus metrics
    """

    registry = prometheus_client.CollectorRegistry()
    label_names = ["job", "container_name"]

    containers = list(discover())

    for container in containers:
        for label in target_labels(container).keys():
            if not label in label_names:
                label_names.append(label)

    container_memory_usage = prometheus_client.Gauge(
        "docker_container_memory_usage_bytes",
        "Container memory usage (without caches)",
        label_names,
        registry=registry,
    )

    container_cpu_usage = prometheus_client.Gauge(
        "docker_container_cpu_usage_percent",
        "Container CPU usage percent (not divided by number of CPU cores)",
        label_names,
        registry=registry,
    )

    def fetch_stats(container: Container):
        stats = container.stats(stream=False)

        labels = target_labels(container)
        metric_labels = dict[str, str]()

        for label in label_names:
            if label == "job":
                metric_labels[label] = container.labels[JOB_LABEL]
            elif label == "container_name":
                metric_labels[label] = container.name or ""
            else:
                metric_labels[label] = labels.get(label, "")

        container_memory_usage.labels(**metric_labels).set(
            stats["memory_stats"].get("usage", 0) - stats["memory_stats"].get("stats", {}).get("cache", 0)
        )

        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_cpu_delta = stats["cpu_stats"].get("system_cpu_usage", 0) - stats["precpu_stats"].get(
            "system_cpu_usage", 0
        )

        container_cpu_usage.labels(**metric_labels).set(
            (cpu_delta / system_cpu_delta) * stats["cpu_stats"]["online_cpus"] * 100.0 if system_cpu_delta > 0 else 0
        )

    with ThreadPoolExecutor(64) as pool:
        for container in containers:
            pool.submit(fetch_stats, container)

    return PrometheusMetricsResponse(prometheus_client.generate_latest(registry))
