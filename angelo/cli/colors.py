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

from ..const import IS_WINDOWS_PLATFORM

NAMES = [
    'grey',
    'red',
    'green',
    'yellow',
    'blue',
    'magenta',
    'cyan',
    'white'
]


def get_pairs():
    for i, name in enumerate(NAMES):
        yield(name, str(30 + i))
        yield('intense_' + name, str(30 + i) + ';1')


def ansi(code):
    return '\033[{0}m'.format(code)


def ansi_color(code, s):
    return '{0}{1}{2}'.format(ansi(code), s, ansi(0))


def make_color_fn(code):
    return lambda s: ansi_color(code, s)


if IS_WINDOWS_PLATFORM:
    import colorama
    colorama.init(strip=False)
for (name, code) in get_pairs():
    globals()[name] = make_color_fn(code)


def rainbow():
    cs = ['cyan', 'yellow', 'green', 'magenta', 'red', 'blue',
          'intense_cyan', 'intense_yellow', 'intense_green',
          'intense_magenta', 'intense_red', 'intense_blue']

    for c in cs:
        yield globals()[c]
