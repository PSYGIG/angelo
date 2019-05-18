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


VERSION_EXPLANATION = (
    'You might be seeing this error because you\'re using the wrong Compose file version. '
    'Either specify a supported version (e.g "2.2" or "3.3") and place '
    'your service definitions under the `services` key, or omit the `version` key '
    'and place your service definitions at the root of the file to use '
    'version 1.\nFor more on the Compose file format versions, see '
    'https://docs.docker.com/compose/compose-file/')


class ConfigurationError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class EnvFileNotFound(ConfigurationError):
    pass


class DependencyError(ConfigurationError):
    pass


class CircularReference(ConfigurationError):
    def __init__(self, trail):
        self.trail = trail

    @property
    def msg(self):
        lines = [
            "{} in {}".format(service_name, filename)
            for (filename, service_name) in self.trail
        ]
        return "Circular reference:\n  {}".format("\n  extends ".join(lines))


class ComposeFileNotFound(ConfigurationError):
    def __init__(self, supported_filenames):
        super(ComposeFileNotFound, self).__init__("""
        Can't find a suitable configuration file in this directory or any
        parent. Are you in the right directory?

        Supported filenames: %s
        """ % ", ".join(supported_filenames))


class DuplicateOverrideFileFound(ConfigurationError):
    def __init__(self, override_filenames):
        self.override_filenames = override_filenames
        super(DuplicateOverrideFileFound, self).__init__(
            "Multiple override files found: {}. You may only use a single "
            "override file.".format(", ".join(override_filenames))
        )
