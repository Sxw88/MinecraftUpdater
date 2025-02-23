import os
import time
import shutil
import hashlib
import time
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import requests
import configparser

"""
README

MinecraftUpdater

This is a python package to automate the updating of your Minecraft server.

It's very annoying to have to download the jar, ftp it over, stop the server, back up your world, etc. This automates alll that. just git clone this in the root of your server so there is an extra folder. Then run python3 update.py in the new folder. 

It will check if you have the latest version of Minecraft using the Mojang provided manfest URL. If your server is out of date, it will download the latest minecraft server jar from the official Mojang S3 bucket. 

Then using screen it will announce to the server that it is going to restart for an update, and give a 30 seconds countdown before stopping the server. 

Next it will then backup your world into a new folder, incase something goes wrong. It then updates the server jar and starts the server back up in a screen session so it's in the background.

# Configuration

Latest vs. Snapshot

UPDATE_TO_SNAPSHOT = <True,False> whether to update to the latest snapshot, or main release

# Backup Directory

BACKUP_DIR = <name of directory to save files>

# Log File

LOG_FILENAME = <name of file to save log messages>

# Ram Settings

RAM_INITIAL = <amount of ram to start the server with>
RAM_MAX = <maximum amount of ram to allocate torwards the server>

# Scheduling Updates
This script is intended to be run as a cron job.
"""
# Change directory to the path where the script is located
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# CONFIGURATION
UPDATE_TO_SNAPSHOT = False
BACKUP_DIR = 'world_backups'
LOG_FILENAME = 'auto_updater.log'
RAM_INITIAL = '1G'      # Default
RAM_MAX = '4G'          # Default
FOLDER_NAME = os.path.basename(os.path.dirname(os.getcwd()))
SCREEN_NAME = f"minecraft_{FOLDER_NAME}"
MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest.json"

# Read server.resources config file and get the RAM settings
resource_config = configparser.ConfigParser()
resource_config.read('../server.resources')
RAM_INITIAL = resource_config['RESOURCE_ALLOCATION']['init_memory']
RAM_MAX = resource_config['RESOURCE_ALLOCATION']['max_memory']

# Get the Name of Minecraft World
# Define path to server.properties file
config_file_path = '../server.properties'
WORLD_NAME = 'minecraft_world'

with open(config_file_path, 'r') as config_file:
    # Read each line in the file
    for line in config_file:
        # Strip any leading/trailing whitespace and check if it starts with 'level-name='
        if line.startswith('level-name='):
            # Extract the value after 'level-name=' and strip any whitespace
            WORLD_NAME = line[len('level-name='):].strip()
            break  


# Max log filesize 1 MB
log_handler = RotatingFileHandler(LOG_FILENAME, maxBytes=1000000, backupCount=5)

logging.basicConfig(
	handlers = [log_handler],
	format="%(asctime)s:%(levelname)s - %(message)s",
	level=logging.INFO
)

os.chdir(os.path.dirname(os.path.abspath(__file__)))

logging.info("Parent Directory: " + FOLDER_NAME)
logging.info("Extracted Name of Minecraft World: " + WORLD_NAME)


# retrieve version manifest
response = requests.get(MANIFEST_URL)
data = response.json()

if UPDATE_TO_SNAPSHOT:
    minecraft_ver = data['latest']['snapshot']
else:
    minecraft_ver = data['latest']['release']

# get checksum of running server
if os.path.exists('../minecraft_server.jar'):
    sha = hashlib.sha1()
    f = open("../minecraft_server.jar", 'rb')
    sha.update(f.read())
    cur_ver = sha.hexdigest()
else:
    cur_ver = ""

for version in data['versions']:
    if version['id'] == minecraft_ver:
        jsonlink = version['url']
        jar_data = requests.get(jsonlink).json()
        jar_sha = jar_data['downloads']['server']['sha1']

        logging.info('Your sha1 is ' + cur_ver + '. Latest version is ' + str(minecraft_ver) + " with sha1 of " + jar_sha)
        
        with open("latest_version", "w") as f:
            f.write(str(minecraft_ver))

        if cur_ver != jar_sha:
            logging.info('Updating server...')
            link = jar_data['downloads']['server']['url']
            logging.info('Downloading .jar from ' + link + '...')
            response = requests.get(link)
            with open('minecraft_server.jar', 'wb') as jar_file:
                jar_file.write(response.content)
            logging.info('Downloaded.')
            os.system(f'screen -S {SCREEN_NAME} -X stuff \"say ATTENTION: Server will shutdown temporarily to update in 30 seconds.$(printf \\\\r)\"')
            logging.info('Shutting down server in 30 seconds.')

            for i in range(20, 9, -10):
                time.sleep(10)
                os.system(f'screen -S {SCREEN_NAME} -X stuff \"say Shutdown in ' + str(i) + ' seconds$(printf \\\\r)\"')

            for i in range(9, 0, -1):
                time.sleep(1)
                os.system(f'screen -S {SCREEN_NAME} -X stuff \"say Shutdown in ' + str(i) + ' seconds$(printf \\\\r)\"')
            time.sleep(1)

            logging.info('Stopping server.')
            os.system(f'screen -S {SCREEN_NAME} -X stuff \"stop$(printf \\\\r)\"')
            time.sleep(5)
            logging.info('Backing up world...')

            if not os.path.exists(BACKUP_DIR):
                os.makedirs(BACKUP_DIR)

            backupPath = os.path.join(
                BACKUP_DIR,
                "world" + "_backup_" + datetime.now().isoformat().replace(':', '-') + "_sha=" + cur_ver)
            shutil.copytree(f'../{WORLD_NAME}', backupPath)

            logging.info('Backed up world.')
            logging.info('Updating server .jar')
            
            # Keep version n-1 of the JAR file, just in case
            if os.path.exists('../minecraft_server.jar.old'):
                os.remove('../minecraft_server.jar.old')
            if os.path.exists('../minecraft_server.jar'):
                os.rename('../minecraft_server.jar', '../minecraft_server.jar.old')

            os.rename('minecraft_server.jar', '../minecraft_server.jar')
            logging.info('Starting server...')
            os.chdir("..")
            os.system(f'screen -S {SCREEN_NAME} -d -m java -server -Xms{RAM_INITIAL} -Xmx{RAM_MAX} -jar minecraft_server.jar nogui')

        else:
            logging.info('Server is already up to date.')

        break
