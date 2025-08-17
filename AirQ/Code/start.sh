#!/bin/bash

echo "Checking status of processes"

###########  Sensor manager  ###########
senmanag=$(pgrep -f sensor_manager.py | wc -l)
echo "Sensor manager process count: $senmanag"
if [ $senmanag -ge 1 ]
then
    echo "Sensor manager is up"
else
    echo "Sensor manager is down... Let's start it"
    cd /home/shootconstantin/DELTA
    nohup python3 /home/shootconstantin/DELTA/sensor_manager.py > /home/shootconstantin/DELTA/logs/sensor_manager.log 2>&1 &
    sleep 5  # Wait for the process to start
fi

###########  All sensors  ###########
declare -a listProcesses=("PMS.py" "SCD30.py" "DHT22.py" "enviro.py")

for p in "${listProcesses[@]}"; do
  p_exists=$(pgrep -f $p | wc -l)
  echo "$p process count: $p_exists"
  if [ $p_exists -ge 1 ]
  then
    echo "Sensor $p is up"
  else
    echo "Sensor $p is down... Let's start it"
    cd /home/shootconstantin/DELTA
    nohup python3 /home/shootconstantin/DELTA/sensors/$p > /home/shootconstantin/DELTA/logs/$p.log 2>&1 &
    sleep 5  # Add a delay between starting processes
  fi
done

echo "Process check complete."
