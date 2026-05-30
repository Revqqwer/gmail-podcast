import sys
import os
from dotenv import load_dotenv

project_home = '/home/hakandeveli24/gmail-podcast'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.chdir(project_home)
load_dotenv(os.path.join(project_home, '.env'), override=True)

from app import app as application
