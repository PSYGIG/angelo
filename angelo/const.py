from __future__ import absolute_import
from __future__ import unicode_literals

import sys

from .version import AngeloVersion

DEFAULT_TIMEOUT = 10
HTTP_TIMEOUT = 60
IS_WINDOWS_PLATFORM = (sys.platform == "win32")

SECRETS_PATH = '/run/secrets'
WINDOWS_LONGPATH_PREFIX = '\\\\?\\'

ANGELOFILE_V1_0 = AngeloVersion('1')

NANOCPUS_SCALE = 1000000000
PARALLEL_LIMIT = 64

API_VERSIONS = {
    ANGELOFILE_V1_0: '1.00',
}

API_VERSION_TO_ENGINE_VERSION = {
    API_VERSIONS[ANGELOFILE_V1_0]: '1.9.0'
}
