#//////////////////////////////////////////////////////////////
#//                                                          //
#//  Script, 2022                                            //
#//  Created: 14, April, 2022                                //
#//  Modified: 30, November, 2024                            //
#//  file: -                                                 //
#//  -                                                       //
#//  Source:                                                 //
#//  OS: ALL                                                 //
#//  CPU: ALL                                                //
#//                                                          //
#//////////////////////////////////////////////////////////////

PROJECT_DIRECTORY := parallel

DOCKER_PROFILES := rabbitmq seaweedfs valkey api flower worker-low worker-high

.PHONY: env-init
env-init:
	python3 scripts/init_env.py

# DockerCompose.mk's own `build`/`start` rules carry the actual recipe; this just adds
# env-init as an extra prerequisite so a fresh clone gets its secrets generated before
# the first build (Make allows several rules for the same target as long as only one
# of them has a recipe).
build: env-init
start: env-init

include DockerCompose.mk
