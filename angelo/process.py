# -*- coding: utf-8 -*- 
# /*
#  * Copyright (C) 2019 PSYGIG株式会社
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

class Process(object):
    def __init__(
        self,
        name,
        system='default',
        pid_mode=None,
        default_platform=None,
        **options
    ):
        self.name = name
        self.system = system
        self.pid_mode = pid_mode or PidMode(None)
        self.default_platform = default_platform
        self.options = options

    def __repr__(self):
        return '<Service: {}>'.format(self.name)


class PidMode(object):
    def __init__(self, mode):
        self._mode = mode

    @property
    def mode(self):
        return self._mode

    @property
    def service_name(self):
        return None