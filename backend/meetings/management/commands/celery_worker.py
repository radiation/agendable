import logging
import shlex
import subprocess
import sys

from django.core.management.base import BaseCommand
from django.utils import autoreload

logger = logging.getLogger(__name__)


def restart_celery():
    celery_worker_cmd = "celery -A agendable worker"
    cmd = f'pkill -f "{celery_worker_cmd}"'
    if sys.platform == "win32":
        cmd = "taskkill /f /t /im celery.exe"

    subprocess.run(shlex.split(cmd))
    subprocess.run(
        shlex.split(
            f"{celery_worker_cmd} --loglevel=info -Q high_priority,low_priority,default"
        )
    )


class Command(BaseCommand):
    def handle(self, *args, **options):
        logger.info("Starting celery worker with autoreload...")
        autoreload.run_with_reloader(restart_celery)
