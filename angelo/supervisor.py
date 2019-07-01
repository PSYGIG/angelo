# -*- coding: utf-8 -*- 
"""

Copyright (C) 2019 PSYGIG株式会社
Copyright (c) 2011 Ryan Kelly

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

djsupervisor.management.commands.supervisor:  djsupervisor mangement command
----------------------------------------------------------------------------

This module defines the main management command for the djsupervisor app.
The "supervisor" command acts like a combination of the supervisord and
supervisorctl programs, allowing you to start up, shut down and manage all
of the proceses defined in your Django project.

The "supervisor" command suports several modes of operation:

    * called without arguments, it launches supervisord to spawn processes.

    * called with the single argument "getconfig", is prints the merged
      supervisord config to stdout.

    * called with the single argument "autoreload", it watches for changes
      to python modules and restarts all processes if things change.

    * called with any other arguments, it passes them on the supervisorctl.

"""

from __future__ import absolute_import, with_statement

import sys
import os
import errno
import hashlib
import time
from textwrap import dedent
import traceback
from configparser import RawConfigParser, NoSectionError, NoOptionError
from io import StringIO
from supervisor import supervisord, supervisorctl
from signal import SIGTERM

class Supervisor(object):

    DEFAULT_CONFIG = """

;  All programs are auto-reloaded by default.
[program:__defaults__]
redirect_stderr=true

[supervisord]
loglevel=warn

[supervisorctl]

"""

    def __init__(self, services):
        self.services = services
        self.pid_file = "supervisord.pid"
        self.mqtt_pid = "mqtt.pid"

    def run_supervisor(self):
        cfg_file = OnDemandStringIO(self.get_merged_config)
        newpid = os.fork()
        if newpid == 0:
            supervisord.main(("-c",cfg_file))
        exit()

    def start_process(self, name="all"):
        cfg_file = OnDemandStringIO(self.get_merged_config)
        try:
            supervisorctl.main(("-c",cfg_file, "start", name))
        except:
            pass

    def stop_process(self, name="all"):
        cfg_file = OnDemandStringIO(self.get_merged_config)
        try:
            supervisorctl.main(("-c",cfg_file, "stop", name))
        except:
            pass

    def restart_process(self, name="all"):
        cfg_file = OnDemandStringIO(self.get_merged_config)
        try:
            supervisorctl.main(("-c", cfg_file, "restart", name))
        except:
            pass

    def reload_config(self):
        os.kill(self.get_pid(), SIGTERM)
        time.sleep(3)
        self.run_supervisor()

    def signal_process(self, name="all", signal="SIGKILL"):
        cfg_file = OnDemandStringIO(self.get_merged_config)
        try:
            supervisorctl.main(("-c",cfg_file, "signal", signal, name))  
        except:
            pass
            
    def get_process_status(self, name=None):
        cfg_file = OnDemandStringIO(self.get_merged_config)
        args = list()
        if name is not None:
            args.append(name)
        try:            
            supervisorctl.main(("-c",cfg_file, "status") + tuple(args))
        except:
            pass
    
    def logs(self, name, follow=False, tail=1600):
        cfg_file = OnDemandStringIO(self.get_merged_config)
        args = list()
        if follow:
            args.append("-f")
        else:
            args.append("-" + str(tail))
        args.append(name)

        try:            
            supervisorctl.main(("-c",cfg_file, "tail") + tuple(args))  
        except:
            pass

    def is_running(self):
        """
        Check if the daemon is running.
        """
        pid = self.get_pid()
        if pid is None:
            return False
        # The PID file may still exist even if the daemon isn't running,
        # for example if it has crashed.
        try:
            os.kill(pid, 0)
        except OSError as e:
            if e.errno == errno.ESRCH:
                # In this case the PID file shouldn't have existed in
                # the first place, so we remove it
                os.remove(self.pid_file)
                return False
            # We may also get an exception if we're not allowed to use
            # kill on the process, but that means that the process does
            # exist, which is all we care about here.
        return True

    def get_pid(self):
        """
        Get PID of daemon process or ``None`` if daemon is not running.
        """
        return self.read_pid()

    def read_pid(self):
        """
        Return the PID of the process owning the lock.
        Returns ``None`` if no lock is present.
        """
        try:
            with open(self.pid_file, 'r') as f:
                s = f.read().strip()
                if not s:
                    return None
                return int(s)
        except IOError as e:
            if e.errno == errno.ENOENT:
                return None
            raise

    def get_merged_config(self, **options):
        """Get the final merged configuration for supvervisord, as a string.

        This is the top-level function exported by this module.  It combines
        the config file from the main project with default settings and those
        specified in the command-line, processes various special section names,
        and returns the resulting configuration as a string.
        """
        config_file = "supervisord.conf"
        
        #  Initialise the ConfigParser.
        #  Fortunately for us, ConfigParser has merge-multiple-config-files
        #  functionality built into it.  You just read each file in turn, and
        #  values from later files overwrite values from former.
        cfg = RawConfigParser()
        #  Start from the default configuration options.
        cfg.readfp(StringIO(self.DEFAULT_CONFIG))
        """
        #  Add in the project-specific config file.
        with open(config_file,"r") as f:
            data = f.read()            
        cfg.readfp(StringIO(data))
        """
        #  Add in the options from the self.services
        cfg.readfp(StringIO(self.get_config_from_services()))
        #  Add in the options specified on the command-line.
        cfg.readfp(StringIO(self.get_config_from_options(**options)))
        #  Add options from [program:__defaults__] to each program section
        #  if it happens to be missing that option.
        PROG_DEFAULTS = "program:__defaults__"
        if cfg.has_section(PROG_DEFAULTS):
            for option in cfg.options(PROG_DEFAULTS):
                default = cfg.get(PROG_DEFAULTS,option)
                for section in cfg.sections():
                    if section.startswith("program:"):
                        if not cfg.has_option(section,option):
                            cfg.set(section,option,default)
            cfg.remove_section(PROG_DEFAULTS)
        #  Add options from [program:__overrides__] to each program section
        #  regardless of whether they already have that option.
        PROG_OVERRIDES = "program:__overrides__"
        if cfg.has_section(PROG_OVERRIDES):
            for option in cfg.options(PROG_OVERRIDES):
                override = cfg.get(PROG_OVERRIDES,option)
                for section in cfg.sections():
                    if section.startswith("program:"):
                        cfg.set(section,option,override)
            cfg.remove_section(PROG_OVERRIDES)
        #  Make sure we've got a port configured for supervisorctl to
        #  talk to supervisord.  It's passworded based on secret key.
        #  If they have configured a unix socket then use that, otherwise
        #  use an inet server on localhost at fixed-but-randomish port.
        
        username = hashlib.md5("angelo".encode('utf-8')).hexdigest()[:7]
        password = hashlib.md5(username.encode('utf-8')).hexdigest()
        if cfg.has_section("unix_http_server"):
            self.set_if_missing(cfg,"unix_http_server","username",username)
            self.set_if_missing(cfg,"unix_http_server","password",password)
            serverurl = "unix://" + cfg.get("unix_http_server","file")
        else:
            #  This picks a "random" port in the 9000 range to listen on.
            #  It's derived from the secret key, so it's stable for a given
            #  project but multiple projects are unlikely to collide.
            port = int(hashlib.md5(password.encode('utf-8')).hexdigest()[:3],16) % 1000
            addr = "127.0.0.1:9%03d" % (port,)
            self.set_if_missing(cfg,"inet_http_server","port",addr)
            self.set_if_missing(cfg,"inet_http_server","username",username)
            self.set_if_missing(cfg,"inet_http_server","password",password)
            serverurl = "http://" + cfg.get("inet_http_server","port")
        self.set_if_missing(cfg,"supervisorctl","serverurl",serverurl)
        self.set_if_missing(cfg,"supervisorctl","username",username)
        self.set_if_missing(cfg,"supervisorctl","password",password)
        self.set_if_missing(cfg,"rpcinterface:supervisor",
                        "supervisor.rpcinterface_factory",
                        "supervisor.rpcinterface:make_main_rpcinterface")
        
        #  Remove any [program:] sections with exclude=true
        for section in cfg.sections():
            try:
                if cfg.getboolean(section,"exclude"):
                    cfg.remove_section(section)
            except NoOptionError:
                pass
        #  Sanity-check to give better error messages.
        for section in cfg.sections():
            if section.startswith("program:"):
                if not cfg.has_option(section,"command"):
                    msg = "Process name '%s' has no command configured"
                    raise ValueError(msg % (section.split(":",1)[-1]))
        #  Write it out to a StringIO and return the data
        s = StringIO()
        cfg.write(s)
        return s.getvalue()

    def rerender_options(options):
        """Helper function to re-render command-line options.

        This assumes that command-line options use the same name as their
        key in the options dictionary.
        """
        args = []
        for name,value in options.iteritems():
            name = name.replace("_","-")
            if value is None:
                pass
            elif isinstance(value,bool):
                if value:
                    args.append("--%s" % (name,))
            elif isinstance(value,list):
                for item in value:
                    args.append("--%s=%s" % (name,item))
            else:
                args.append("--%s=%s" % (name,value))
        return " ".join(args)

    def get_config_from_services(self):
        """Get config file fragment reflecting self.services"""
        data = []
        for service in self.services:
            data.append("[program:%s]\ncommand=%s\n\n" % (service.name, service.options['command']))

        return "".join(data)

    def get_config_from_options(self,**options):
        """Get config file fragment reflecting command-line options."""
        data = []
        #  Set whether or not to daemonize.
        #  Unlike supervisord, our default is to stay in the foreground.
        data.append("[supervisord]\n")
        if options.get("pidfile",None):
            data.append("pidfile=%s\n" % (options["pidfile"],))
        if options.get("logfile",None):
            data.append("logfile=%s\n" % (options["logfile"],))
        #  Set which programs to launch automatically on startup.
        for progname in options.get("launch",None) or []:
            data.append("[program:%s]\nautostart=true\n" % (progname,))
        for progname in options.get("nolaunch",None) or []:
            data.append("[program:%s]\nautostart=false\n" % (progname,))
        #  Set which programs to include/exclude from the config
        for progname in options.get("include",None) or []:
            data.append("[program:%s]\nexclude=false\n" % (progname,))
        for progname in options.get("exclude",None) or []:
            data.append("[program:%s]\nexclude=true\n" % (progname,))
        #  Set which programs to autoreload when code changes.
        #  When this option is specified, the default for all other
        #  programs becomes autoreload=false.
        if options.get("autoreload",None):
            data.append("[program:autoreload]\nexclude=false\nautostart=true\n")
            data.append("[program:__defaults__]\nautoreload=false\n")
            for progname in options["autoreload"]:
                data.append("[program:%s]\nautoreload=true\n" % (progname,))
        #  Set whether to use the autoreloader at all.
        if options.get("noreload",False):
            data.append("[program:autoreload]\nexclude=true\n")
        return "".join(data)

    def set_if_missing(self,cfg,section,option,value):
        """If the given option is missing, set to the given value."""
        try:
            cfg.get(section,option)
        except NoSectionError:
            cfg.add_section(section)
            cfg.set(section,option,value)
        except NoOptionError:
            cfg.set(section,option,value)

class OnDemandStringIO(object):
    """StringIO standin that demand-loads its contents and resets on EOF.

    This class is a little bit of a hack to make supervisord reloading work
    correctly.  It provides the readlines() method expected by supervisord's
    config reader, but it resets itself after indicating end-of-file.  If
    the supervisord process then SIGHUPs and tries to read the config again,
    it will be re-created and available for updates.
    """

    def __init__(self, callback, *args, **kwds):
        self._fp = None
        self.callback = callback
        self.args = args
        self.kwds = kwds

    def __iter__(self):
        return self

    def __next__(self):
        line = self.fp.readline(*self.args, **self.kwds)
        if not line:
            self._fp = None
            raise StopIteration
        return line

    @property
    def fp(self):
        if self._fp is None:
            self._fp = StringIO(self.callback(*self.args, **self.kwds))
        return self._fp

    def read(self, *args, **kwds):
        data = self.fp.read(*args, **kwds)
        if not data:
            self._fp = None
        return data

    def readline(self, *args, **kwds):
        line = self.fp.readline(*args, **kwds)
        if not line:
            self._fp = None
        return line