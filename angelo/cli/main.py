#  Copyright (C) 2019 PSYGIG株式会社

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import contextlib
import functools
import json
import logging
import pipes
import re
import subprocess
import sys
from distutils.spawn import find_executable
from inspect import getdoc

from . import errors
from . import signals
from .. import __version__
from ..config.serialize import serialize_config
from ..errors import StreamParseError
from ..progress_stream import StreamOutputError
from .command import get_config_from_options
from .command import system_from_options
from .docopt_command import DocoptDispatcher
from .docopt_command import get_handler
from .docopt_command import NoSuchCommand
from .errors import UserError
from .formatter import ConsoleWarningFormatter
from .utils import get_version_info

log = logging.getLogger(__name__)
console_handler = logging.StreamHandler(sys.stderr)


def main():
    signals.ignore_sigpipe()
    try:
        command = dispatch()
        command()
    except (KeyboardInterrupt, signals.ShutdownException):
        log.error("Aborting.")
        sys.exit(1)
    except (UserError) as e:
        log.error(e.msg)
        sys.exit(1)
    except StreamOutputError as e:
        log.error(e)
        sys.exit(1)
    except NoSuchCommand as e:
        commands = "\n".join(parse_doc_section("commands:", getdoc(e.supercommand)))
        log.error("No such command: %s\n\n%s", e.command, commands)
        sys.exit(1)
    except (errors.ConnectionError, StreamParseError):
        sys.exit(1)

def dispatch():
    setup_logging()
    dispatcher = DocoptDispatcher(
        TopLevelCommand,
        {'options_first': True, 'version': get_version_info('angelo')})

    options, handler, command_options = dispatcher.parse(sys.argv[1:])
    setup_console_handler(console_handler,
                          options.get('--verbose'),
                          options.get('--no-ansi'),
                          options.get("--log-level"))
    setup_parallel_logger(options.get('--no-ansi'))
    if options.get('--no-ansi'):
        command_options['--no-color'] = True
    return functools.partial(perform_command, options, handler, command_options)

def perform_command(options, handler, command_options):
    if options['COMMAND'] in ('help', 'version'):
        # Skip looking up the angelo file.
        handler(command_options)
        return

    if options['COMMAND'] == 'config':
        command = TopLevelCommand(None, options=options)
        handler(command, command_options)
        return

    system = system_from_options('.', options)
    command = TopLevelCommand(system, options=options)

    handler(command, command_options)


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.DEBUG)

    # Disable requests logging
    logging.getLogger("requests").propagate = False


def setup_parallel_logger(noansi):
    if noansi:
        import angelo.parallel
        angelo.parallel.ParallelStreamWriter.set_noansi()


def setup_console_handler(handler, verbose, noansi=False, level=None):
    if handler.stream.isatty() and noansi is False:
        format_class = ConsoleWarningFormatter
    else:
        format_class = logging.Formatter

    if verbose:
        handler.setFormatter(format_class('%(name)s.%(funcName)s: %(message)s'))
        loglevel = logging.DEBUG
    else:
        handler.setFormatter(format_class())
        loglevel = logging.INFO

    if level is not None:
        levels = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        loglevel = levels.get(level.upper())
        if loglevel is None:
            raise UserError(
                'Invalid value for --log-level. Expected one of DEBUG, INFO, WARNING, ERROR, CRITICAL.'
            )

    handler.setLevel(loglevel)


# stolen from docopt master
def parse_doc_section(name, source):
    pattern = re.compile('^([^\n]*' + name + '[^\n]*\n?(?:[ \t].*?(?:\n|$))*)',
                         re.IGNORECASE | re.MULTILINE)
    return [s.strip() for s in pattern.findall(source)]

class TopLevelCommand(object):
    """Configure and run applications with Angelo.

    Usage:
      angelo [-f <arg>...] [options] [COMMAND] [ARGS...]
      angelo -h|--help

    Options:
      -f, --file FILE             Specify an alternate angelo file
                                  (default: angelo.yml)
      --verbose                   Show more output
      --log-level LEVEL           Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
      -v, --version               Print version and exit
      --root-directory PATH       Specify an alternate working directory
                                  (default: the path of the Angelo file)

    Commands:
      config             Validate and view the Angelo file
      down               Stop process
      events             Receive real time events from containers
      help               Get help on a command
      kill               Kill processes
      logs               View output from containers
      ps                 List processes
      stop               Stop services
      top                Display the running processes
      up                 Start services
      version            Show the Angelo version information
    """

    def __init__(self, directory, options=None):
        self.directory = directory
        self.toplevel_options = options or {}

    @property
    def root_dir(self):
        return self.toplevel_options.get('--root-directory') or '.'

    @classmethod
    def help(cls, options):
        """
        Get help on a command.

        Usage: help [COMMAND]
        """
        if options['COMMAND']:
            subject = get_handler(cls, options['COMMAND'])
        else:
            subject = cls

        print(getdoc(subject))

    def config(self, options):
        """
        Validate and view the Angelo file.

        Usage: config [options]

        Options:
            --no-interpolate         Don't interpolate environment variables
            -q, --quiet              Only validate the configuration, don't print
                                     anything.
            --services               Print the service names, one per line.
        """

        additional_options = {'--no-interpolate': options.get('--no-interpolate')}
        angelo_config = get_config_from_options('.', self.toplevel_options, additional_options)
        image_digests = None


        if options['--quiet']:
            return

        if options['--services']:
            print('\n'.join(service['name'] for service in angelo_config.services))
            return

        print(serialize_config(angelo_config, image_digests, not options['--no-interpolate']))

    def up(self, options):
        """
        Starts, and attaches to process for a service.

        Unless they are already running, this command also starts any linked services.

        The `angelo up` command aggregates the output of each service. When
        the command exits, all processes are stopped. Running `angelo up -d`
        starts the processes in the background and leaves them running.

        Usage: up [options] [--scale SERVICE=NUM...] [SERVICE...]

        Options:
            -d, --detach               Detached mode: Run services in the background,
                                       print new services names. Incompatible with
                                       --abort-on-services-exit.
            --no-color                 Produce monochrome output.
            --quiet-pull               Pull without printing progress information
            --no-deps                  Don't start linked services.
            -t, --timeout TIMEOUT      Use this timeout in seconds for service
                                       shutdown when attached or when services are
                                       already running. (default: 10)
            --exit-code-from SERVICE   Return the exit code of the selected service
                                       service. Implies --abort-on-container-exit.
            --env-file PATH            Specify an alternate environment file
        """

    @classmethod
    def version(cls, options):
        """
        Show version information

        Usage: version [--short]

        Options:
            --short     Shows only Angelo's version number.
        """
        if options['--short']:
            print(__version__)
        else:
            print(get_version_info('full'))