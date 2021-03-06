#!/usr/bin/env python2
from datetime import datetime, timedelta
from time import time, mktime
from calendar import timegm
from pymongo import Connection
import numpy as np
from pytz import timezone
from matplotlib.dates import strpdate2num, epoch2num, num2date
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import sys
import ConfigParser as cp

if len(sys.argv) > 0:
    configfile = sys.argv[1]
else:
    sys.exit
config = cp.ConfigParser()
config.read(configfile)

emailfrom = config.get("Mail", 'from')
password = config.get("Mail", 'password')
emailserver = config.get("Mail", 'server')
emailport = config.getint("Mail", 'port')
TLS = config.getboolean("Mail", 'tls')
emailto = config.get("Mail", 'to').split(',')
tz = timezone(config.get('Setup', 'timezone'))

def getremote(mongos, database, collection, filename=None):
    connection = Connection(mongos)
    db = connection[database]
    coll = db[collection]

    datenow = datetime.utcnow()
    datelimit = datenow - timedelta(hours=24)

    results = coll.find({'date': {"$gte": datelimit, "$lte": datenow}})
    num = results.count()
    logs = np.zeros((num, 3))

    for i, point in enumerate(results):
        date = timegm(point['date'].timetuple())
        try:
            logs[i, :] = [date, point['humidity'], point['temperature']]
        except (IndexError):
            pass

    if filename:
        np.save(filename, logs)

    return logs, datenow, datelimit

# Create base filename
basenow = datetime.now()
basefilename = basenow.strftime("%Y%m%d-%H%M")
subject = "LabWeather: %s" %(basefilename)

mongos = config.get('Database', 'mongos').split(',')
db = config.get('Database', 'db')
collection = config.get('Database', 'collection')
getremote(mongos, db, collection, basefilename)

logs = np.load('%s.npy' %basefilename)
import smooth
import sendmail

dates = epoch2num(logs[:, 0])
dates = num2date(dates, tz)
humidity = logs[:, 1]
temperature = logs[:, 2]
wlen2 = 500
wlen = wlen2 * 2 + 1
kalman = smooth.kalman(temperature)
if kalman is None:  # there was a problem with the data, report and bye
    text = "Check weather recording, nothing to report at the moment."
    sendmail.sendout(subject, emailfrom, password, emailto, text, [], emailserver, emailport, TLS)
    sys.exit(0)

fig = plt.figure(figsize=(11.27, 8.69))

ax1 = fig.add_subplot(211)
ax1.plot_date(dates, humidity, 'k-')
ax1.set_ylabel("Humidity (%)")
fig.autofmt_xdate()

ax2 = fig.add_subplot(212)
ax2.plot_date(dates, temperature, 'k.', label="measurement")
ax2.plot_date(dates, kalman, 'r-', linewidth=2, label="Kalman-filter")
ax2.set_ylabel("Temperature (C)")
ax2.set_xlabel("Time", fontsize=16)
ax2.set_title("Temperature + Kalman-filtered measurement")
fig.autofmt_xdate()

ax1.set_title("%s -> %s" %(dates[0], dates[-1]))

plt.savefig("%s.png" %(basefilename))

hmean, hmax, hmin = np.mean(humidity), np.max(humidity), np.min(humidity)
tmean, tmax, tmin = np.mean(temperature), np.max(temperature), np.min(temperature)
smean, smax, smin = np.mean(kalman), np.max(kalman), np.min(kalman)

text = ""
text += "Lab weather report for %s -> %s \n" %(dates[0], dates[-1])
text += "Humidity [%%] (avg/min/max): %.1f / %.1f / %.1f \n" %(hmean, hmin, hmax)
text += "Temperature [C] (avg/min/max): %.2f / %.2f / %.2f (filtered)\n" %(smean, smin, smax)

images = ['%s.png' %(basefilename)]

sendmail.sendout(subject, emailfrom, password, emailto, text, images, emailserver, emailport, TLS)
