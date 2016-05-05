__title__ = 'cord'
__author__ = 'maxpowa'
__license__ = 'MIT'
__copyright__ = 'Copyright 2015-2016 maxpowa'
__version__ = '0.1.0'

import sys

__user_agent__ = "cord (https://github.com/maxpowa/cord {0}) Python/{1[0]}.{1[1]}".format(__version__, sys.version_info)

from cord.client import Client
from cord.errors import *
from cord.util import start_logging, get_token, invalidate_token, get_gateway
