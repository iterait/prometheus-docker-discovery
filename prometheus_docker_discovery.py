from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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
        if TARGET_PORT_LABEL not in container.labels:
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
    label_names = ["job", "container_name", "image", "image_id", "container_id"]
    now = datetime.now(timezone.utc)

    containers = list(discover())

    info = client.df()

    containers_df = {container["Id"]: container for container in info["Containers"]}

    for container in containers:
        for label in target_labels(container).keys():
            if label not in label_names:
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

    container_uptime = prometheus_client.Gauge(
        "docker_container_uptime_seconds",
        "Container uptime",
        label_names,
        registry=registry,
    )

    container_rootfs_size = prometheus_client.Gauge(
        "docker_container_rootfs_size_bytes",
        "Container rootfs size in bytes",
        label_names,
        registry=registry,
    )

    container_size_on_disk = prometheus_client.Gauge(
        "docker_container_disk_size_bytes",
        "Container size on disk in bytes",
        label_names,
        registry=registry,
    )

    container_mount_count = prometheus_client.Gauge(
        "docker_container_mount_count",
        "Number of container mounts",
        label_names,
        registry=registry,
    )

    volume_size = prometheus_client.Gauge(
        "docker_volume_size_bytes", "Size of a volume in bytes.", ["volume_id"], registry=registry
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
            elif label == "image":
                metric_labels[label] = containers_df[container.id].get("Image", "")
            elif label == "image_id":
                metric_labels[label] = containers_df[container.id].get("ImageID", "")
            elif label == "container_id":
                metric_labels[label] = container.id or "unknown-container-id"
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

        if container.status == "running" and container.attrs:
            started_at = container.attrs.get("State", {}).get("StartedAt")
            if started_at:
                container_uptime.labels(**metric_labels).set(
                    (now - datetime.fromisoformat(started_at).astimezone(timezone.utc)).total_seconds()
                )
        else:
            container_uptime.labels(**metric_labels).set(0)

        container_rootfs_size.labels(**metric_labels).set(
            containers_df[container.id]["SizeRootFs"]
        )

        if "SizeRw" in containers_df[container.id]:
            container_size_on_disk.labels(**metric_labels).set(
                containers_df[container.id]["SizeRw"]
            )

        container_mount_count.labels(**metric_labels).set(
            len(containers_df[container.id].get("Mounts", []))
        )

    for volume in info["Volumes"]:
        volume_size.labels(volume_id=volume["Name"]).set(volume["UsageData"]["Size"])

    with ThreadPoolExecutor(64) as pool:
        for container in containers:
            pool.submit(fetch_stats, container)

    return PrometheusMetricsResponse(prometheus_client.generate_latest(registry))
