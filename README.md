# Prometheus Docker Discovery

This service exports [prometheus](https://prometheus.io/) metrics of various docker containers and volumes.

## Metrics
Currently supported metrics:
- `docker_container_memory_usage_bytes` - Container memory usage (without caches)
- `docker_container_cpu_usage_percent` - Container CPU usage percent (not divided by number of CPU cores)
- `docker_container_uptime_seconds` - Container uptime
- `docker_container_rootfs_size_bytes` - Container rootfs size in bytes
- `docker_container_disk_size_bytes` - Container size on disk in bytes
- `docker_container_mount_count` - Number of container mounts
- `docker_volume_size_bytes` - Size of a volume in bytes

## Container Metrics Registration via Labels
- Add `prometheus.job=<job-name>` label to the container to-be exported.
- Optionally add other labels to be exported via `prometheus.labels.<label-name>=<label-value>`

## Run Prometheus Docker Discovery
```bash
docker run -p 8000:8000 -v /var/run/docker.sock:/var/run/docker.sock iterait/prometheus-docker-discovery:master
```

Access http://localhost:8080/metrics This might take a while

## Example docker-compose.yaml
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
