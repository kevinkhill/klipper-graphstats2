import os
import webbrowser
from fabric import Connection

from graphstats2 import parse_log, draw_graphs

toy_factory = Connection("rock5.home.local")

remote_log = "printer_data/logs/klippy.log"
local_log = os.path.join(os.getcwd(), "klippy.log")

if __name__ == "__main__":
    if not os.path.exists(local_log):
        print("Grabbing klippy.log")
        toy_factory.get(remote_log)

    data = parse_log(local_log)
    if not data:
        print("klippy.log not found")

    print("Parsed; Plotting...")
    draw_graphs(data, heater="heater_bed,extruder")

    url = os.path.join("file:///", os.getcwd(), "klippy.log.html")
    webbrowser.open(url, new=2)

    print("Done!")
