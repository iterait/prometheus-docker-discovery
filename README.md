# Prometheus Docker Discovery

Prometheus Docker Discovery is a service tailored to seamlessly export the [Prometheus](https://prometheus.io/) metrics for [Docker](https://www.docker.com/) containers and volumes.
This enhances the monitoring and observability of your Dockerized applications, providing insights into resource utilization, container health, and other critical metrics.

## Supported Metrics
This service currently supports a set of monitoring metrics:
- `docker_container_memory_usage_bytes` - Container memory usage, excluding caches
- `docker_container_cpu_usage_percent` - Container CPU usage percent, not divided by number of CPU cores
- `docker_container_uptime_seconds` - Container uptime
- `docker_container_rootfs_size_bytes` - Container `rootfs` size in bytes
- `docker_container_disk_size_bytes` - Container size on disk in bytes
- `docker_container_mount_count` - Number of container mounts
- `docker_volume_size_bytes` - Volume size

## Container Metrics Registration via Labels
Effortlessly register container metrics by adding specific labels to the container. The following labels are essential:
- `prometheus.job=<job-name>`: Assign a job name for Prometheus to identify, collect and export metrics.
- Optionally, enhance metric granularity by incorporating additional labels through `prometheus.labels.<label-name>=<label-value>`.

## Run Prometheus Docker Discovery
Supposing there are already some correctly labeled containers, you can initiate Prometheus Docker Discovery with the following command:

```bash
docker run -p 8000:8000 -v /var/run/docker.sock:/var/run/docker.sock iterait/prometheus-docker-discovery:master
```

Access the metrics endpoint at http://localhost:8000/metrics.
Be patient, as the metrics might take a while to become available.

## Example docker-compose.yaml
Integrate Prometheus Docker Discovery seamlessly into your Docker-compose environment with this example configuration:

```yaml
services:
  db_prod:
    image: postgres
    labels:
      - prometheus.job=db
      - prometheus.labels.env=production

  db_dev:
    image: postgres
    labels:
      - prometheus.job=db
      - prometheus.labels.env=dev

  prometheus_docker_discovery:
    image: iterait/prometheus-docker-discovery:master
    ports:
      - 8000:8000
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

## License
Prometheus Docker Discovery is released under the [MIT License](./LICENSE).

## Collaboration
We welcome and encourage collaboration from the community.
If you find Prometheus Docker Discovery useful or have ideas for improvement, please feel free to contribute to the project.

To get started, fork the repository, make your changes, and submit a pull request.
