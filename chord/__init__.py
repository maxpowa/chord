
# flake8: noqa
__title__ = 'chord'
__author__ = 'maxpowa'
__license__ = 'MIT'
__copyright__ = 'Copyright 2015-2016 maxpowa'
__version__ = '0.1.0'

import sys

__user_agent__ = "chord (https://github.com/maxpowa/chord {0}) Python/{1[0]}.{1[1]}".format(__version__, sys.version_info)

from chord.client import Client
from chord.errors import *
from chord.util import start_logging, get_token, invalidate_token, get_gateway, check_token, get_user_for_token
from chord.util import http_patch, http_post
