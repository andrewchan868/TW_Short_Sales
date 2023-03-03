import codecs
import logging
import os
import time
from logging.handlers import BaseRotatingHandler

LOG_LEVEL = logging.INFO

class MultiProcessSafeDailyRotatingFileHandler(BaseRotatingHandler):
    """
    Similar with `logging.TimedRotatingFileHandler`, while this one is
    - Multi process safe
    - Rotate at midnight only
    - Utc not supported
    - This log will create day by day.
    """
    def __init__(self, filename, encoding=None, delay=False, utc=False, **kwargs):
        self.utc = utc
        self.suffix = "%Y%m%d.log"
        self.baseFilename = os.path.abspath(filename)
        self.currentFileName = self._compute_fn()
        BaseRotatingHandler.__init__(self, filename, 'a', encoding, delay)

    def shouldRollover(self, record):
        if self.currentFileName != self._compute_fn():
            return True
        return False

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        self.currentFileName = self._compute_fn()

    def _compute_fn(self):
        return self.baseFilename + "." + time.strftime(self.suffix, time.localtime())

    def _open(self):
        if self.encoding is None:
            stream = open(self.currentFileName, self.mode)
        else:
            stream = codecs.open(self.currentFileName, self.mode, self.encoding)
        # simulate file name structure of `logging.TimedRotatingFileHandler`
        if os.path.exists(self.baseFilename):
            try:
                os.remove(self.baseFilename)
            except OSError:
                pass
        try:
            # Create the symlink point the lastest log file.
            os.symlink(self.currentFileName, self.baseFilename)
        except OSError:
            pass
        return stream


def get_logger(logger_name='default logger', log_path='', format_string='', add_handler=True, log_level=LOG_LEVEL):
    """
        - `logger_name`建议按Python的包名来设置，可以捕获sub-library的log
        - `log_path`要求输入文件的路径（包括文件名），例如`logs/xxx.log`，默认存在get_logger.py的同一级
        - `format_string` 不填则有默认值，填写方法可参考 https://docs.python.org/3.6/library/logging.html#logrecord-attributes
        - `add_handler` 是否添加handler，若为主logger，不需要再次添加handler，否则每行log都会重复1次
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)

    if add_handler and (not logger.hasHandlers()):
        current_file_abs_path = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_file_abs_path,"log")
        if not os.path.isdir(path): 
            os.mkdir(path)
        th = MultiProcessSafeDailyRotatingFileHandler(filename= os.path.join(path,"log.log"),when="S",interval=10)
        formatter = logging.Formatter('%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(processName)s - %(threadName)s: %(message)s')
        th.setFormatter(formatter)
        logger.addHandler(th)

        """ if log_path:
            fh = logging.FileHandler(log_path, encoding='utf-8')
        else:
            current_file_abs_path = os.path.dirname(os.path.abspath(__file__))
            fh = logging.FileHandler(f'{current_file_abs_path}/log_{time.strftime("%Y%m%d_%H%M")}.log', encoding='utf-8')
        fh.setLevel(logging.DEBUG) """

        sh = logging.StreamHandler()
        sh.setLevel(log_level)

        if format_string:
            formatter = logging.Formatter(format_string)
        else:
            formatter = logging.Formatter('%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(processName)s - %(threadName)s: %(message)s')

        #fh.setFormatter(formatter)
        sh.setFormatter(formatter)

        #logger.addHandler(fh)
        logger.addHandler(sh)

    return logger
