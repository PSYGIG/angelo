# -*- coding: utf-8 -*- 
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
from ..config.environment import Environment
from ..errors import StreamParseError
from ..errors import OperationFailedError
from ..progress_stream import StreamOutputError
from ..system import NoSuchService
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
    except (NoSuchService) as e:
        log.error(e.msg)
        sys.exit(1)
    except (OperationFailedError) as e:
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
      up                 Start services
      down               Stop services
      restart            Restart services
      help               Get help on a command
      kill               Kill services
      logs               View output from services
      ps                 List services
      top                Display the running services
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
        Starts services defined in config file.

        Unless they are already running, this command also starts any linked services.

        The `angelo up` command aggregates the output of each service. When
        the command exits, all services are stopped. Running `angelo up -d`
        starts the services in the background and leaves them running.

        Usage: up [options] [--scale SERVICE=NUM...] [SERVICE...]

        Options:
            -d, --detach               Detached mode: Run services in the background,
                                       print new services names. Incompatible with
                                       --abort-on-services-exit.
            --no-color                 Produce monochrome output.
            --no-deps                  Don't start linked services.
            -t, --timeout TIMEOUT      Use this timeout in seconds for service
                                       shutdown when attached or when services are
                                       already running. (default: 10)
            --exit-code-from SERVICE   Return the exit code of the selected service
                                       service. Implies --abort-on-container-exit.
            --env-file PATH            Specify an alternate environment file
        """
        start_deps = not options['--no-deps']
        exit_value_from = exitval_from_opts(options, self.directory)
        service_names = options['SERVICE']
        timeout = timeout_from_opts(options)
        detached = options.get('--detach')

        if detached and exit_value_from:
            raise UserError("--abort-on-container-exit and -d cannot be combined.")

        environment_file = options.get('--env-file')
        environment = Environment.from_env_file(self.root_dir, environment_file)
  
        self.directory.up(
                    service_names=service_names,
                    start_deps=start_deps,
                    timeout=timeout,
                    detached=detached,
        )

    def down(self, options):
        """
        Stops services created by `up`.

        Usage: down [options] [SERVICE...]

        Options:
            -t, --timeout TIMEOUT   Specify a shutdown timeout in seconds.
                                    (default: 10)
            --env-file PATH         Specify an alternate environment file
        """
        service_names = options['SERVICE']
        environment_file = options.get('--env-file')
        environment = Environment.from_env_file(self.root_dir, environment_file)

        timeout = timeout_from_opts(options)
        self.directory.down(
            service_names=service_names,
            timeout=timeout)

    def restart(self, options):
        """
        Restart running services.

        Usage: restart [options] [SERVICE...]

        Options:
          -t, --timeout TIMEOUT      Specify a shutdown timeout in seconds.
                                     (default: 10)
        """
        service_names = options['SERVICE']

        self.directory.restart(
            service_names=service_names,
            timeout=timeout_from_opts(options))

    def ps(self, options):
        """
        List services.
    
        Usage: ps [options] [SERVICE...]    
        """
        service_names = options['SERVICE']

        self.directory.top(
            service_names=service_names)

    def top(self, options):
        """
        Display the running services

        Usage: top [SERVICE...]
        """
        service_names = options['SERVICE']

        self.directory.top(
            service_names=service_names)

    def restart(self, options):
        """
        Restart running services.

        Usage: restart [options] [SERVICE...]

        Options:
          -t, --timeout TIMEOUT      Specify a shutdown timeout in seconds.
                                     (default: 10)
        """
        service_names = options['SERVICE']

        self.directory.restart(
            service_names=service_names,
            timeout=timeout_from_opts(options))

    def kill(self, options):
        """
        Force stop services.

        Usage: kill [options] [SERVICE...]
        
        Options:
            -s SIGNAL         SIGNAL to send to the container.
                              Default signal is SIGKILL.
                              Can be one of SIGTERM, SIGHUP, 
                              SIGINT, SIGQUIT, SIGKILL, 
                              SIGUSR1, or SIGUSR2.
        """
        signal = options.get('-s', 'SIGKILL')

        self.directory.kill(service_names=options['SERVICE'], signal=signal)

    def logs(self, options):
        """
        View output from services.

        Usage: logs [options] [SERVICE...]
        
        Options:
            --no-color          Produce monochrome output.
            -f, --follow        Follow log output.
            --tail="all"        Number of lines to show from the end of the logs
                                for each container.
        """        
        tail = options['--tail']
        if tail is not None:
            if tail.isdigit():
                tail = int(tail)
            elif tail == 'all':
                tail = int(sys.maxsize)
            else:
                raise UserError("tail flag must be all or a number")

        self.directory.logs(
            service_names=options['SERVICE'],
            follow=options['--follow'],
            tail=tail)

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

def exitval_from_opts(options, project):
    exit_value_from = options.get('--exit-code-from')
    if exit_value_from:
        if not options.get('--abort-on-container-exit'):
            log.warning('using --exit-code-from implies --abort-on-container-exit')
            options['--abort-on-container-exit'] = True
        if exit_value_from not in [s.name for s in project.get_services()]:
            log.error('No service named "%s" was found in your compose file.',
                      exit_value_from)
            sys.exit(2)
    return exit_value_from

def timeout_from_opts(options):
    timeout = options.get('--timeout')
    return None if timeout is None else int(timeout)