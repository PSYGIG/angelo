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

import six

from .process import Process

class System(object):
    """
    A system consisting of processes
    """
    def __init__(self, name, services, config_version=None):
        self.name = name
        self.services = services
        self.config_version = config_version


    @classmethod
    def from_config(cls, name, config_data, default_platform=None):
        """
        Construct a Project from a config.Config object.
        """
        system = cls(name, [], config_data.version)

        for service_dict in config_data.services:
            service_dict = dict(service_dict)

            system.services.append(
                Process(
                    service_dict.pop('name'),
                    pid_mode=None,
                    platform=service_dict.pop('platform', None),
                    default_platform=default_platform,
                    **service_dict)
            )

        return system

    def get_service(self, name):
        """
        Retrieve a service by name. Raises NoSuchService
        if the named service does not exist.
        """
        for service in self.services:
            if service.name == name:
                return service

        raise NoSuchService(name)

class NoSuchService(Exception):
    def __init__(self, name):
        if isinstance(name, six.binary_type):
            name = name.decode('utf-8')
        self.name = name
        self.msg = "No such service: %s" % self.name

    def __str__(self):
        return self.msg
