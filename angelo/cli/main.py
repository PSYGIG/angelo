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
import os
import errno
from distutils.spawn import find_executable
from inspect import getdoc
import random
import ssl
import websockets
import asyncio
import os
import sys
import json
import argparse
import re

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

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

log = logging.getLogger(__name__)
console_handler = logging.StreamHandler(sys.stderr)


def main():
    signals.ignore_sigpipe()
    try:
        conf_file = os.path.expanduser("~") + "/.angelo/angelo.conf"
        if not os.path.exists(conf_file):
            os.makedirs(os.path.dirname(conf_file), exist_ok=True)
            with open(conf_file, 'w+') as f:
                f.write('[app.psygig.com]')
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

    system = system_from_options(os.environ.get('ANGELO_PATH') or '.', options)
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
      register           Register device on the PSYGIG platform
      up                 Start services
      down               Stop services
      start              Start all processes (services, MQTT client, webserver)
      stop               Stop all processes
      reload             Reload a new config file and start services
      restart            Restart services
      help               Get help on a command
      kill               Kill services
      logs               View output from services
      ps                 List services
      top                Display the running services
      live               Send live video stream from device to server
      offline            Stop the live video stream from the device to server
      broadcast          Broadcast video stream from device to all clients connected to server
      version            Show the Angelo version information
      install            Install module for custom video and data processing
      run                Run the module already installed with angelo
      publish            Publish your module to the PSYGIG platform
      track              Track this device's GPS location on the PSYGIG platform
    """

    def __init__(self, directory, options=None):
        self.directory = directory
        self.toplevel_options = options or {}

    @property
    def root_dir(self):
        return self.toplevel_options.get('--root-directory') or os.environ.get('ANGELO_PATH') or '.'

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
        angelo_config = get_config_from_options(os.environ.get('ANGELO_PATH'), self.toplevel_options, additional_options)
        image_digests = None


        if options['--quiet']:
            return

        if options['--services']:
            print('\n'.join(service['name'] for service in angelo_config.services))
            return

        print(serialize_config(angelo_config, image_digests, not options['--no-interpolate']))

    def register(self, options):
        """
        Register this device onto the PSYGIG platform.
        Required to communicate with the device management app.

        Usage: register
        """
        identifier = input("Identifier: ").strip()
        id = input("App ID: ").strip()
        secret = input("App Secret: ").strip()
        try:
            assert identifier != ""
            if len(id.split(' ')) != 1 or len(secret.split(' ')) != 1:
                raise NameError("ID and/or secret must not have spaces.")
            assert id != ""
            assert secret != ""
            int(id)
        except NameError as e:
            logging.error(e)
            sys.exit(1)
        except ValueError as e:
            logging.error("ID must be a number.")
            sys.exit(1)
        except AssertionError as e:
            logging.error("All fields are required.")
            sys.exit(1)

        self.directory.register(identifier, id, secret)

    def up(self, options):
        """
        Starts services defined in config file.

        Unless they are already running, this command also starts any linked services.

        The `angelo up` command aggregates the output of each service. When
        the command exits, all services are stopped. Running `angelo up -d`
        starts the services in the background and leaves them running.

        Usage: up [options] [SERVICE...]

        Options:
            -d, --detach               Detached mode: Run services in the background,
                                       print new services names. Incompatible with
                                       --abort-on-services-exit.
            --no-deps                  Don't start linked services.
            -t, --timeout TIMEOUT      Use this timeout in seconds for service
                                       shutdown when attached or when services are
                                       already running. (default: 10)
        """
        start_deps = not options['--no-deps']
        exit_value_from = exitval_from_opts(options, self.directory)
        service_names = options['SERVICE']
        timeout = timeout_from_opts(options)
        detached = options.get('--detach')

        if detached and exit_value_from:
            raise UserError("--abort-on-container-exit and -d cannot be combined.")

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
        # service_names = options['SERVICE']
        # environment_file = options.get('--env-file')
        # environment = Environment.from_env_file(self.root_dir, environment_file)

        # timeout = timeout_from_opts(options)
        # self.directory.down(
        #     service_names=service_names,
        #     timeout=timeout)
        self.directory.down()

    def start(self, options):
        """
        Starts all services defined in the config file, MQTT client, and webserver.

        Usage: start [options]

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
        timeout = timeout_from_opts(options)
        detached = options.get('--detach')

        if detached and exit_value_from:
            raise UserError("--abort-on-container-exit and -d cannot be combined.")

        environment_file = options.get('--env-file')
        environment = Environment.from_env_file(self.root_dir, environment_file)

        self.directory.start(
            start_deps=start_deps,
            timeout=timeout,
            detached=detached,
        )

    def stop(self, options):
        """
        Stops all processes created by `start` and `up`.

        Usage: stop [options]

        Options:
            -t, --timeout TIMEOUT   Specify a shutdown timeout in seconds.
                                    (default: 10)
            --env-file PATH         Specify an alternate environment file
        """
        environment_file = options.get('--env-file')
        environment = Environment.from_env_file(self.root_dir, environment_file)

        timeout = timeout_from_opts(options)
        self.directory.stop(
            timeout=timeout)

    def reload(self, options):
        """
        Reload new config file on the system and start services defined in new config file.

        Usage: reload
        """
        self.directory.reload()

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

    def live(self, options):
        """
        Send live video stream from device to server.

        Usage: live [options]

        Options:
            -e, --experimental         Stream immediately to a connection
                                       without a connected peer.
        """
        Gst.init(None)
        if not check_plugins():
            sys.exit(1)

        if options['--experimental']:
            self.directory.live(experimental=True)
        else:
            self.directory.live()

    def offline(self, options):
        """
        Stop the video stream from this device.

        Usage: offline
        """
        self.directory.offline()

    def broadcast(self, options):
        """
        Broadcast video stream from device to all clients connected to server

        Usage: broadcast [options]

        Options:
            -s, --server SERVER         Specify an rtmp ingestion endpoint.

        """

        cmd = "gst-launch-1.0 v4l2src device=/dev/video0 ! queue ! videoconvert ! queue ! x264enc ! flvmux streamable=true ! queue ! rtmpsink location="

        nv_cmd = "gst-launch-1.0 -e nvarguscamerasrc ! 'video/x-raw(memory:NVMM), width=(int)1920, height=(int)1080, format=(string)NV12, \
        framerate=(fraction)30/1' ! nvvidconv flip-method=0 ! 'video/x-raw, format=(string)BGRx' ! queue ! videoconvert ! queue ! \
        x264enc ! flvmux streamable=true ! queue ! rtmpsink location="

        location = options['--server'] or "rtmp://52.185.136.118/LiveApp/242243369345776013882004"

        if is_jetson_nano():
            cmd = nv_cmd + location
        else:
            cmd = cmd + location

        print("Broadcast starting now...")
        subprocess.check_output(cmd, shell=True)

    def install(self, options):
        """
        Install pluggable module for custom video and data processing.
        Tries a local install, then checks the marketplace.

        Usage: install [options] [MODULE]

        Options:
            -i         Install a local module. MODULE must be an absolute path.

        """
        if options['MODULE']:
            versioned_module = options['MODULE'].split('#')
            if len(versioned_module) == 2:
                module_name = versioned_module[0]
                version = versioned_module[1]
            elif len(versioned_module) == 1:
                module_name = versioned_module[0]
                version = None
            else:
                print("Invalid formatting, must be like <MODULE_NAME>#<MAJOR.MINOR.PATCH> or <MODULE_NAME>")
                return
            try:
                if options['-i']:
                    self.directory.install(module_name)
                else:
                    self.directory.install(module_name, True, version)
            except FileNotFoundError:
                print("Module could not be found locally or remotely")
        else:
            print("No module is given")

    def run(self, options):
        """
        Run the installed pluggable module

        Usage: run [MODULE_ID]
        """
        # TODO: check if the module id is installed
        if options['MODULE_ID']:
            self.directory.run(options['MODULE_ID'])
        else:
            print("No module is given")

    def publish(self, options):
        """
        Publish your pluggable module

        Usage: publish [options] [MODULE]

        Options:
            -o          Publish to organization
        """
        if options['MODULE']:
            if options['-o']:
                self.directory.publish(options['MODULE'], True)
            else:
                self.directory.publish(options['MODULE'])
        else:
            print("No module given")

    def track(self, options):
        """
        Track this device's GPS location on the PSYGIG platform.
        
        Usage: track
        """
        self.directory.track()

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

def is_jetson_nano():
    answer = False
    cmd = "cat /proc/device-tree/model"
    try:
        result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
        if result == 'jetson-nano' or result == b'NVIDIA Jetson Nano Developer Kit\x00':
            answer = True
    except subprocess.CalledProcessError:
        pass
    return answer

def check_plugins():
    needed = ["opus", "vpx", "nice", "webrtc", "dtls", "srtp", "rtp",
              "rtpmanager", "videotestsrc", "audiotestsrc"]
    missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
    if len(missing):
        print('Missing gstreamer plugins:', missing)
        return False
    return True

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