# encoding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals

import pytest
import mock
import unittest

from angelo.config.config import Config
from angelo.system import System
from angelo.const import ANGELOFILE_V1_0 as V1

class SystemTest(unittest.TestCase):
    def setUp(self):
        pass

    def test_from_config_v1(self):
        config = Config(
            version=V1,
            services=[
                {
                    'name': 'command',
                    'command': 'command run',
                },
                {
                    'name': 'conquer',
                    'command': 'conquer all',
                },
            ],
            secrets=None,
            configs=None,
        )
        system = System.from_config(
            name='angelotest',
            config_data=config
        )
        assert len(system.services) == 2
        assert system.get_service('command').name == 'command'
        assert system.get_service('command').options['command'] == 'command run'
        assert system.get_service('conquer').name == 'conquer'
        assert system.get_service('conquer').options['command'] == 'conquer all'