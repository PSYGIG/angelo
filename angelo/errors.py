# -*- coding: utf-8 -*- 
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


class OperationFailedError(Exception):
    def __init__(self, reason):
        self.msg = reason


class StreamParseError(RuntimeError):
    def __init__(self, reason):
        self.msg = reason


class HealthCheckException(Exception):
    def __init__(self, reason):
        self.msg = reason


class HealthCheckFailed(HealthCheckException):
    def __init__(self, container_id):
        super(HealthCheckFailed, self).__init__(
            'Container "{}" is unhealthy.'.format(container_id)
        )


class NoHealthCheckConfigured(HealthCheckException):
    def __init__(self, service_name):
        super(NoHealthCheckConfigured, self).__init__(
            'Service "{}" is missing a healthcheck configuration'.format(
                service_name
            )
        )
