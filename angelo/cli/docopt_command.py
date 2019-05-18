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

from inspect import getdoc

from docopt import docopt
from docopt import DocoptExit


def docopt_full_help(docstring, *args, **kwargs):
    try:
        return docopt(docstring, *args, **kwargs)
    except DocoptExit:
        raise SystemExit(docstring)


class DocoptDispatcher(object):

    def __init__(self, command_class, options):
        self.command_class = command_class
        self.options = options

    def parse(self, argv):
        command_help = getdoc(self.command_class)
        options = docopt_full_help(command_help, argv, **self.options)
        command = options['COMMAND']

        if command is None:
            raise SystemExit(command_help)

        handler = get_handler(self.command_class, command)
        docstring = getdoc(handler)

        if docstring is None:
            raise NoSuchCommand(command, self)

        command_options = docopt_full_help(docstring, options['ARGS'], options_first=True)
        return options, handler, command_options


def get_handler(command_class, command):
    command = command.replace('-', '_')
    # we certainly want to have "exec" command, since that's what docker client has
    # but in python exec is a keyword
    if command == "exec":
        command = "exec_command"

    if not hasattr(command_class, command):
        raise NoSuchCommand(command, command_class)

    return getattr(command_class, command)


class NoSuchCommand(Exception):
    def __init__(self, command, supercommand):
        super(NoSuchCommand, self).__init__("No such command: %s" % command)

        self.command = command
        self.supercommand = supercommand
