#!/bin/bash

# Update system and install required packages
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv i2c-tools libgpiod2 sqlite3 sqlitebrowser

# Install Python packages globally (with --break-system-packages)
pip3 install --upgrade pip
pip3 install --break-system-packages adafruit-circuitpython-dht bme280 enviroplus ltr559 numpy pms5003 scd30_i2c smbus smbus2 pandas psutil requests

# Enable UART for PMS5003 (edit /boot/firmware/config.txt)
sudo bash -c 'echo "# pms5003" >> /boot/firmware/config.txt'
sudo bash -c 'echo "dtoverlay=pi3-miniuart-bt" >> /boot/firmware/config.txt'

# Configure serial port (disable console, enable hardware UART)
sudo raspi-config nonint do_serial_hw 0
sudo raspi-config nonint do_serial_cons 1

# Enable SPI and I2C via raspi-config
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0

# Add cron job for start.sh (if not already present)
CRON_JOB="@reboot sleep 20; /home/shootconstantin/DELTA/start.sh > /home/shootconstantin/DELTA/start.log 2>&1"
if ! (crontab -l | grep -q "$CRON_JOB"); then
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Cron job added for automatic startup."
else
    echo "Cron job already exists. Skipping."
fi

echo "✅ Setup completed! Rebooting in 5 seconds..."
sleep 5
sudo reboot