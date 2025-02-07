import logging
import os
from datetime import datetime
from logging.handlers import BaseRotatingHandler
from logging.handlers import TimedRotatingFileHandler
from logging import Logger as LoggingLogger


def custom_rotate(self, source: str, dest: str):
    if callable(self.rotator):
        self.rotator(source, dest)

BaseRotatingHandler.rotate = custom_rotate


class DateFolderRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, *args, **kwargs):
        self._file_name_template = args[0]
        base_file_name = self.create_path()
        super().__init__(base_file_name, **kwargs)

    def doRollover(self) -> None:
        self.baseFilename = self.create_path()
        return super().doRollover()

    def create_path(self):
        base_file_name = datetime.now().strftime(self._file_name_template)
        base_path_list = base_file_name.split('/')
        dir_path = '/'.join(base_path_list[:-1])
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        return base_file_name


class Logger():
    _ROLLOVER_SUFFIX = '%Y-%m-%d'

    def get_logger(self, name: str, file_name: str='log', console: bool=True) -> LoggingLogger:
        self._console = console
        self._file_name = file_name
        self._logger = logging.getLogger(name)
        if not self._logger.hasHandlers():
            self._init_logger()
        return self._logger

    def _init_logger(self):
        self._log_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s")
        self._init_console_logger()
        self._init_file_logger(file_name=self._file_name)
        self._logger.setLevel("DEBUG")

    def _init_console_logger(self):
        if self._console:
            s_handler = logging.StreamHandler()
            s_handler.setFormatter(self._log_format)
            self._logger.addHandler(s_handler)

    def _init_file_logger(self, file_name: str=""):
        log_path = self._get_log_path(file_name)
        r_handler = DateFolderRotatingFileHandler(log_path, when='midnight', interval=1)
        r_handler.setFormatter(self._log_format)
        self._logger.addHandler(r_handler)

    def _get_log_path(self, file_name: str) -> str:
        log_path = f"logs/{self._ROLLOVER_SUFFIX}/{file_name}.log"
        return log_path