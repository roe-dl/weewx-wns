wns - weewx extension that sends data to Wetternetz-Sachsen
Copyright 2020 Johanna Roedenbeck
Distributed under the terms of the GNU Public License (GPLv3)

You will need an account at Wetternetz-Sachsen

  http://www.wetternetz-sachsen.de

Installation instructions:

1) download

wget -O weewx-wns.zip https://github.com/roe-dl/weewx-wns/archive/master.zip

2) run the installer

sudo wee_extension --install weewx-wns.zip

3) enter parameters in the weewx configuration file

[StdRESTful]
    [[Wns]]
        enable = true
        station = station ID
        api_key = WNS-Kennung
        T5AKT_ = observation type that holds 5cm-temperature
        SOD1D_ = observation type that holds sun duration
        skip_upload = false
        log_url = false

4) restart weewx

   for SysVinit systems:

   ```
   sudo /etc/init.d/weewx stop
   sudo /etc/init.d/weewx start
   ```

   for systemd systems:

   ```
   sudo systemctl stop weewx
   sudo systemctl start weewx
   ```

Configuration instructions:

Station ID and WNS-Kennung are mandatory. You get them from the Wetternetz
Sachsen administrator. 

Set T5AKT_ = None if you do not measure 5cm temperature. Otherwise give the
WeeWX observation type you use for that value.

Set SOD1D_ to the observation type of sun duration. If you do not have
such an observation type set it to None.

Set `TSOI10`, `TSOI20`, and `TSOI50` to the appropriate WeeWX observation
types if you measure soil temperatures. The number is the depth in cm.

Set skip_upload to true to do all the calculation and preparation without
doing the real upload. This is for testing.

Set log_url to true to log the URL sent to Wetternetz Sachsen to syslog.
This is for trouble shooting.
