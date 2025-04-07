#//////////////////////////////////////////////////////////////
#//                                                          //
#//  docker-multimedia, 2024                                 //
#//  Created: 30, May, 2021                                  //
#//  Modified: 14 November, 2024                             //
#//  file: -                                                 //
#//  -                                                       //
#//  Source:                                                 //
#//  OS: ALL                                                 //
#//  CPU: ALL                                                //
#//                                                          //
#//////////////////////////////////////////////////////////////

PROJECT_DIRECTORY ?= parallel

DOCKER_EXEC ?= docker

DOCKER_PROFILES ?= main_infrastructure

PROFILE_CMD ?= $(addprefix --profile ,$(DOCKER_PROFILES))

COMPOSE_FILES ?=  $(shell find ./$(PROJECT_DIRECTORY) -maxdepth 1 -name 'docker-compose*.yml' -type f | sed -e 's/^/--file /')
COMPOSE_FILES_DEPLOY ?=  $(shell find ./$(PROJECT_DIRECTORY)/services -maxdepth 2 -name 'docker-deploy*.yml' -type f | sed -e 's/^/--compose-file /')

COMPOSE_DIR ?= --project-directory ./$(PROJECT_DIRECTORY)

UID ?= 1000
GID ?= 1000

#PUID=$(UID) PGID=$(GID)
ENV_ARG_VAR ?=

DOCKER_COMPOSE_COMMAND ?= $(ENV_ARG_VAR) $(DOCKER_EXEC) compose $(COMPOSE_DIR) $(COMPOSE_FILES) $(PROFILE_CMD)

.PHONY: build all
all: start

.PHONY: build
build:
	$(DOCKER_COMPOSE_COMMAND) build

.PHONY: start
start: build
	$(DOCKER_COMPOSE_COMMAND) up --detach --remove-orphans

.PHONY: start-at
start-at: build
	$(DOCKER_COMPOSE_COMMAND) up --remove-orphans

.PHONY: check
check:
	$(DOCKER_COMPOSE_COMMAND) config

.PHONY: stop
stop: down

.PHONY: down
down:
	$(DOCKER_COMPOSE_COMMAND) down

.PHONY: restart
restart: stop start

# deploy for docker swarm
.PHONY: deploy
deploy:
	$(DOCKER_EXEC) stack deploy $(COMPOSE_FILES_DEPLOY) mystack

.PHONY: logs
logs:
	$(DOCKER_COMPOSE_COMMAND) logs

.PHONY: state
state:
	$(DOCKER_COMPOSE_COMMAND) ps
	$(DOCKER_COMPOSE_COMMAND) top

.PHONY: image-update
image-update:
	$(DOCKER_COMPOSE_COMMAND) pull

.PHONY: git-update
git-update: 
#	git submodule update --init --recursive --remote
	git pull --recurse-submodules --all --progress

.PHONY: update
update: image-update git-update

.PHONY: clean
clean:
	docker system prune -f

.PHONY: purge
purge:
	$(ENV_ARG_VAR) $(DOCKER_EXEC) compose $(COMPOSE_DIR) $(COMPOSE_FILES) down -v --rmi all
