# /*
#  * Copyright (C) 2019 PSYGIG株式会社
#  * Copyright (C) 2019 Docker Inc.
#  *
#  * Licensed under the Apache License, Version 2.0 (the "License");
#  * you may not use this file except in compliance with the License.
#  * You may obtain a copy of the License at
#  *
#  * http://www.apache.org/licenses/LICENSE-2.0
#  *
#  * Unless required by applicable law or agreed to in writing, software
#  * distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.
#  */

from __future__ import absolute_import
from __future__ import unicode_literals

import logging
import os
import re

import six

from . import errors
from . import verbose_proxy
from .. import config
from .. import parallel
from ..system import System
from ..config.environment import Environment
from ..const import API_VERSIONS
from .utils import get_version_info

log = logging.getLogger(__name__)

SILENT_COMMANDS = set((
    'events',
    'exec',
    'kill',
    'logs',
    'pause',
    'ps',
    'restart',
    'rm',
    'start',
    'stop',
    'top',
    'unpause',
))


def system_from_options(project_dir, options, additional_options={}):
    override_dir = options.get('--project-directory')
    environment_file = options.get('--env-file')
    environment = Environment.from_env_file(override_dir or project_dir, environment_file)
    environment.silent = options.get('COMMAND', None) in SILENT_COMMANDS
    set_parallel_limit(environment)

    host = options.get('--host')
    if host is not None:
        host = host.lstrip('=')
    return get_project(
        project_dir,
        get_config_path_from_options(project_dir, options, environment),
        project_name=options.get('--project-name'),
        verbose=options.get('--verbose'),
        host=host,
        environment=environment,
        override_dir=override_dir,
        compatibility=options.get('--compatibility'),
        interpolate=(not additional_options.get('--no-interpolate'))
    )


def set_parallel_limit(environment):
    parallel_limit = environment.get('COMPOSE_PARALLEL_LIMIT')
    if parallel_limit:
        try:
            parallel_limit = int(parallel_limit)
        except ValueError:
            raise errors.UserError(
                'COMPOSE_PARALLEL_LIMIT must be an integer (found: "{}")'.format(
                    environment.get('COMPOSE_PARALLEL_LIMIT')
                )
            )
        if parallel_limit <= 1:
            raise errors.UserError('COMPOSE_PARALLEL_LIMIT can not be less than 2')
        parallel.GlobalLimit.set_global_limit(parallel_limit)


def get_config_from_options(base_dir, options, additional_options={}):
    override_dir = options.get('--project-directory')
    environment_file = options.get('--env-file')
    environment = Environment.from_env_file(override_dir or base_dir, environment_file)
    config_path = get_config_path_from_options(
        base_dir, options, environment
    )
    return config.load(
        config.find(base_dir, config_path, environment, override_dir),
        options.get('--compatibility'),
        not additional_options.get('--no-interpolate')
    )


def get_config_path_from_options(base_dir, options, environment):
    def unicode_paths(paths):
        return [p.decode('utf-8') if isinstance(p, six.binary_type) else p for p in paths]

    file_option = options.get('--file')
    if file_option:
        return unicode_paths(file_option)

    config_files = environment.get('COMPOSE_FILE')
    if config_files:
        pathsep = environment.get('COMPOSE_PATH_SEPARATOR', os.pathsep)
        return unicode_paths(config_files.split(pathsep))
    return None


def get_project(project_dir, config_path=None, project_name=None, verbose=False,
                host=None, tls_config=None, environment=None, override_dir=None,
                compatibility=False, interpolate=True):
    if not environment:
        environment = Environment.from_env_file(project_dir)
    config_details = config.find(project_dir, config_path, environment, override_dir)
    project_name = get_project_name(
        config_details.working_dir, project_name, environment
    )
    config_data = config.load(config_details, compatibility, interpolate)

    api_version = environment.get(
        'COMPOSE_API_VERSION',
        API_VERSIONS[config_data.version])



    return System.from_config(
        project_name, config_data, environment.get('DOCKER_DEFAULT_PLATFORM')
    )


def get_project_name(working_dir, project_name=None, environment=None):
    def normalize_name(name):
        return re.sub(r'[^-_a-z0-9]', '', name.lower())

    if not environment:
        environment = Environment.from_env_file(working_dir)
    project_name = project_name or environment.get('COMPOSE_PROJECT_NAME')
    if project_name:
        return normalize_name(project_name)

    project = os.path.basename(os.path.abspath(working_dir))
    if project:
        return normalize_name(project)

    return 'default'
