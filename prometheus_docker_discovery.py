from typing import cast

from docker import DockerClient
from docker.models.containers import Container
from fastapi import FastAPI
from pydantic import BaseModel

DISCOVERY_LABEL_PREFIX = "prometheus."
TARGET_LABELS_PREFIX = f"{DISCOVERY_LABEL_PREFIX}labels."
TARGET_ADDRESS_LABEL = f"{DISCOVERY_LABEL_PREFIX}address"


app = FastAPI()
client = DockerClient.from_env()


class DiscoveredTarget(BaseModel):
    targets: list[str]
    labels: dict[str, str]


@app.get("/targets", response_model=list[DiscoveredTarget])
def get_targets():
    containers = cast(list[Container], client.containers.list(all=True))
    result = list[DiscoveredTarget]()

    for container in containers:
        job_name = container.labels.get(f"{DISCOVERY_LABEL_PREFIX}job")
        if job_name is None:
            continue

        if not TARGET_ADDRESS_LABEL in container.labels:
            continue

        target = DiscoveredTarget(
            targets=[container.labels[TARGET_ADDRESS_LABEL]],
            labels={"job": job_name, "container_name": container.name or ""},
        )

        result.append(target)

        for label_name, label_value in container.labels.items():
            if not label_name.startswith(TARGET_LABELS_PREFIX):
                continue

            label_name = label_name[len(TARGET_LABELS_PREFIX) :]
            target.labels[label_name] = label_value

    return result
