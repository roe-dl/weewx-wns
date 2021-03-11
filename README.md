# weewx-wns

wns - weewx extension that sends data to Wetternetz-Sachsen

Distributed under the terms of the GNU Public License (GPLv3)

## Prerequisites

You will need an account at Wetternetz-Sachsen

  http://www.wetternetz-sachsen.de

## Installation instructions:

1) download

   ```
   wget -O weewx-wns.zip https://github.com/roe-dl/weewx-wns/archive/master.zip
   ```

2) run the installer

   ```
   sudo wee_extension --install weewx-wns.zip
   ```

3) enter parameters in the weewx configuration file

   ```
   [StdRESTful]
       [[Wns]]
           enable = true
           station = station ID
           api_key = WNS-Kennung
           T5AKT_ = column that holds 5cm-temperature
           skip_upload = false
           log_url = false
   ```

4) restart weewx

   ```
   sudo /etc/init.d/weewx stop
   sudo /etc/init.d/weewx start
   ```

## Configuration instructions:

* Station ID and WNS-Kennung are mandatory. You get them from the Wetternetz
  Sachsen administrator. 

* Set T5AKT_ = None if you do not measure 5cm temperature. Otherwise give the
  WeeWX observation type you use for that value.

* Set skip_upload to true to do all the calculation and preparation without
  doing the real upload. This is for testing. Set log_url=true to see what
  would be uploaded.

* Set log_url to true to log the URL sent to Wetternetz Sachsen to syslog.
  This is for trouble shooting.
