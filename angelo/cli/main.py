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
from operator import attrgetter

from . import errors
from . import signals
from .. import __version__
from ..config import ConfigurationError
from ..config import parse_environment
from ..config import parse_labels
from ..config import resolve_build_args
from ..config.environment import Environment
from ..config.serialize import serialize_config
from ..config.types import VolumeSpec
from ..const import IS_WINDOWS_PLATFORM
from ..errors import StreamParseError
from ..progress_stream import StreamOutputError
from .command import get_config_from_options
from .command import project_from_options
from .docopt_command import DocoptDispatcher
from .docopt_command import get_handler
from .docopt_command import NoSuchCommand
from .errors import UserError
from .formatter import ConsoleWarningFormatter
from .formatter import Formatter
from .log_printer import build_log_presenters
from .log_printer import LogPrinter
from .utils import get_version_info
from .utils import human_readable_file_size
from .utils import yesno

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
        {'options_first': True, 'version': get_version_info('compose')})

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
        # Skip looking up the compose file.
        handler(command_options)
        return

    if options['COMMAND'] == 'config':
        command = TopLevelCommand(None, options=options)
        handler(command, command_options)
        return

    project = project_from_options('.', options)
    command = TopLevelCommand(project, options=options)
    with errors.handle_connection_errors(project.client):
        handler(command, command_options)


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.DEBUG)

    # Disable requests logging
    logging.getLogger("requests").propagate = False


def setup_parallel_logger(noansi):
    if noansi:
        import compose.parallel
        compose.parallel.ParallelStreamWriter.set_noansi()


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
    """Define and run applications with Angelo.

    Usage:
      angelo [-f <arg>...] [options] [COMMAND] [ARGS...]
      angelo -h|--help

    Options:
      -f, --file FILE             Specify an alternate compose file
                                  (default: docker-compose.yml)
      -p, --project-name NAME     Specify an alternate project name
                                  (default: directory name)
      --verbose                   Show more output
      --log-level LEVEL           Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
      --no-ansi                   Do not print ANSI control characters
      -v, --version               Print version and exit
      -H, --host HOST             Daemon socket to connect to

      --tls                       Use TLS; implied by --tlsverify
      --tlscacert CA_PATH         Trust certs signed only by this CA
      --tlscert CLIENT_CERT_PATH  Path to TLS certificate file
      --tlskey TLS_KEY_PATH       Path to TLS key file
      --tlsverify                 Use TLS and verify the remote
      --skip-hostname-check       Don't check the daemon's hostname against the
                                  name specified in the client certificate
      --project-directory PATH    Specify an alternate working directory
                                  (default: the path of the Compose file)
      --compatibility             If set, Compose will attempt to convert keys
                                  in v3 files to their non-Swarm equivalent
      --env-file PATH             Specify an alternate environment file

    Commands:
      build              Build or rebuild services
      bundle             Generate a Docker bundle from the Compose file
      config             Validate and view the Compose file
      create             Create services
      down               Stop and remove containers, networks, images, and volumes
      events             Receive real time events from containers
      exec               Execute a command in a running container
      help               Get help on a command
      images             List images
      kill               Kill containers
      logs               View output from containers
      pause              Pause services
      port               Print the public port for a port binding
      ps                 List containers
      pull               Pull service images
      push               Push service images
      restart            Restart services
      rm                 Remove stopped containers
      run                Run a one-off command
      scale              Set number of containers for a service
      start              Start services
      stop               Stop services
      top                Display the running processes
      unpause            Unpause services
      up                 Create and start containers
      version            Show the Docker-Compose version information
    """

    def __init__(self, project, options=None):
        self.project = project
        self.toplevel_options = options or {}

    @property
    def project_dir(self):
        return self.toplevel_options.get('--project-directory') or '.'

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