# Parallel

The main goal of this project is to experiment with a solution for encoding large amounts of multimedia data in parallel across multiple servers.

## Requirements

### Software requirements

| Software | Minimum | Recommended |
| -------- | ------- | ----------- |
| Linux    | Any     | Any         |
| Docker   | 19.x    | 20.x        |
| Make     | 4.x     | 4.x         |

### Hardware requirements

|       Hardware        |  Minimum  |   Recommended    |
| :-------------------: | :-------: | :--------------: |
|        Server         |     1     | 1 (only for now) |
|          CPU          |   2c/2t   |      6c/12t      |
| Instruction set (x86) | x86-64-v2 |    x86-64-v3     |
| Instruction set (ARM) |   armv8   |      armv8       |
|          RAM          |   8 GB    |      32 GB       |
|          GPU          |     -     | Hardware enc/dec |
|      Disk space       |   4 GB    |      16 GB       |
|       Internet        |  10 Mbps  |     100 Mbps     |


## Architecture

This is a Docker Compose POC (single host, 2-4 services/workers) meant to later scale to
many hosts, so the code is deliberately split so growth doesn't mean rewriting it:

- `parallel/services/common/` -- shared config (`Settings`, one env var per field,
  required fields have no insecure default) and S3 client, used by both `api` and `tasks`.
- `parallel/services/tasks/` -- the Celery app and its tasks. Each media type is its own
  module (`video.py`, `image.py`); adding a new conversion (e.g. another image format)
  means adding one task module plus one entry in `api/media_handlers.py`, not touching
  the existing ones.
- `parallel/services/api/` -- FastAPI app, split into `routers/` (`media`, `health`,
  `admin`) plus `security.py` (API key auth), `schemas.py` (response models) and
  `media_handlers.py` (extension -> Celery task registry).
- `parallel/services/worker/` -- the Celery worker entrypoint. `worker-high`/`worker-low`
  in `docker-compose.yml` are two replica groups consuming different priority queues.

Infrastructure (RabbitMQ, Valkey, SeaweedFS, Flower) each live under their own
`parallel/services/<name>/` with their own `docker-compose.yml` and `env/` folder,
included by `parallel/docker-compose.yml`.

## Installation

Secrets are never committed: each service's `env/*.env` is generated locally from a
committed `env/*.env.example` template (placeholders look like `GENERATE:<name>`; the
same name always gets the same random value across files, e.g. the RabbitMQ password
used by both the `rabbitmq` and `api`/`worker` services).

```bash
make env-init   # generates parallel/services/*/env/*.env if missing -- also runs
                 # automatically as part of `make start`/`make build`
```

Then bring up the stack (builds the images and starts every service declared in
`DOCKER_PROFILES` in the `Makefile`):

```bash
make start
```

Your generated API key is in `parallel/services/api/env/variables.api.env`
(`API_KEY=...`). The `scripts/*.sh` helpers and the Robot Framework tests both need it;
the tests read it automatically, the scripts expect it exported:

```bash
export API_KEY=$(grep -oP 'API_KEY=\K.+' parallel/services/api/env/variables.api.env)
./scripts/push.sh
```

To run the integration test suite (it drives `make start`/`make stop` itself and needs
a Python environment with Robot Framework, separate from the services' own
dependencies):

```bash
python3 -m venv myenv
source myenv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
robot --randomize all tests.robot
```

## Source

- [FFMPEG](https://ffmpeg.org/)
- [RabbitMQ](https://www.rabbitmq.com/)
- [Celery](https://docs.celeryproject.org/en/stable/)

## License

[MIT](LICENSE)
