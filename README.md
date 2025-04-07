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


## Installation

```bash
python3 -m venv myenv
```

```bash
source myenv/bin/activate
```

```bash
pip install --upgrade pip
```

```bash
pip install -r requirements.txt
```

Now all dependencies are installed, you can run the tests:

```bash
robot --randomize all tests.robot
```




## Source

- [FFMPEG](https://ffmpeg.org/)
- [RabbitMQ](https://www.rabbitmq.com/)
- [Celery](https://docs.celeryproject.org/en/stable/)
- [Flask](https://flask.palletsprojects.com/)
