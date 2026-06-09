import sys
import os
from dotenv import load_dotenv

project_home = '/home/hakandeveli24/gmail-podcast'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

# PA web process'i --user site-packages'ı otomatik yüklemiyor
user_packages = '/home/hakandeveli24/.local/lib/python3.13/site-packages'
if user_packages not in sys.path:
    sys.path.insert(0, user_packages)

os.chdir(project_home)
load_dotenv(os.path.join(project_home, '.env'), override=True)

from app import app as application
