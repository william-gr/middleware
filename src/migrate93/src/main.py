import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freenasUI.settings')
# Make sure to load all modules
from django.db.models.loading import cache
cache.get_apps()
from django.core.management import call_command

call_command('syncdb', interactive=False, merge=True, delete_ghosts=True, migrate=True)
