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

import signal

from ..const import IS_WINDOWS_PLATFORM


class ShutdownException(Exception):
    pass


class HangUpException(Exception):
    pass


def shutdown(signal, frame):
    raise ShutdownException()


def set_signal_handler(handler):
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def set_signal_handler_to_shutdown():
    set_signal_handler(shutdown)


def hang_up(signal, frame):
    raise HangUpException()


def set_signal_handler_to_hang_up():
    # on Windows a ValueError will be raised if trying to set signal handler for SIGHUP
    if not IS_WINDOWS_PLATFORM:
        signal.signal(signal.SIGHUP, hang_up)


def ignore_sigpipe():
    # Restore default behavior for SIGPIPE instead of raising
    # an exception when encountered.
    if not IS_WINDOWS_PLATFORM:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)