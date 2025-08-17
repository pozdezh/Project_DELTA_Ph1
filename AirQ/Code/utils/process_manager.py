#Import python files
import os
import sys
import datetime
import time
import psutil
import signal

#Import actua modules
import utils.config_manager as cfg
import utils.database_manager as db
import utils.logger_manager as lm

# logging
filename = os.path.splitext(os.path.basename(__file__))[0]
logger = lm.setup_logger(filename)


'''
Check if process is executing
'''
def is_process_running(s):
    script = s + '.py'
    
    for q in psutil.process_iter():
        if q.name().startswith('python'):
            if len(q.cmdline())>1 and script in q.cmdline()[1] and q.pid!=os.getpid():
                #logger.debug('Process %s is already running' % script)
                return True
    return False

'''
Kill the process
'''
def kill_process(s):
    try:
        process = s + '.py'
        for line in os.popen("ps ax | grep " + process + " | grep -v grep"):
            fields = line.split()
            pid = fields[0]
            os.kill(int(pid), signal.SIGKILL)
        logger.info('Killing process %s ' % s)
         
    except:
        logger.error('Error while killing process %s' % s)


'''
Validates if the process is running and if it's recording data to the database
'''
def is_process_active(sensor):
    
    # 1) check if process is executing
    running = is_process_running(sensor)
    if not running:
        return False
    if (sensor=="switch"):
        return True
    
    # 2) check last row inserted in database
    cfg_data = cfg.load_sensor_configuration(sensor)
    tag = cfg_data['tag']
    minuts = db.last_insert(tag)
    '''
    if minuts is not None:
        if (minuts == datetime.timedelta(minutes=555)):  #flag: no records found
            #3) check last CSV exportation (perhaps it is recently, so process is fine...)
            minuts_lgcsv = db.last_generated_csv()
            now = datetime.datetime.now()
            last_inserted_time = datetime.datetime.strptime(minuts_lgcsv, "%Y-%m-%d %H:%M:%S")
            comp = (now - last_inserted_time)
            if (comp < datetime.timedelta(minutes=15)):
                return True
            else:
                return False
        else:
            cfg_db_data = cfg.load_db_configuration()
            max_time_nodata = int(cfg_db_data['max_time_nodata'])

            # if minutes is higher than the max writing threshold, we assume process is not running fine
            # otherwise, the process is writing correctly
            if (minuts>datetime.timedelta(minutes=max_time_nodata)):
                return False 
            else:
                return True
    else:
        return False
    
    '''
    
    #default
    return True
