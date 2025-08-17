#Import python files
import os
import logging
import logging.handlers as handlers

#Import actua modules
import utils.config_manager as cfg


#Load configuration
cfg_lm_data = cfg.load_logger_configuration()
PATH = cfg_lm_data['path']
MAX_BYTES =  int(cfg_lm_data['size'])
BACKUP_COUNT = int(cfg_lm_data['backups'])

'''
This function setups the logger and returns the instance to use it for logging porpuses
'''
def setup_logger(name):
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logHandler = handlers.RotatingFileHandler(PATH, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
    logHandler.setLevel(logging.INFO)
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
    
    return logger