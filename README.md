# weewx-wns

wns - weewx extension that sends data to Wetternetz-Sachsen

Distributed under the terms of the GNU Public License (GPLv3)

## Prerequisites

You will need an account at Wetternetz-Sachsen

  http://www.wetternetz-sachsen.de

## Installation instructions:

1) download

   ```shell
   wget -O weewx-wns.zip https://github.com/roe-dl/weewx-wns/archive/master.zip
   ```

2) run the installer

   WeeWX up to version 4.X

   ```shell
   sudo wee_extension --install weewx-wns.zip
   ```

   WeeWX from version 5.0 on after WeeWX packet installation

   ```shell
   sudo weectl extension install weewx-wns.zip
   ```

   WeeWX from version 5.0 on after WeeWX pip installation into an virtual environment

   ```shell
   source ~/weewx-venv/bin/activate
   weectl extension install weewx-svg2png.zip
   ```
   
3) enter parameters in the weewx configuration file

   ```
   [StdRESTful]
       [[Wns]]
           enable = true
           station = station ID
           api_key = WNS-Kennung
           T5AKT_ = observation type that holds 5cm-temperature
           SOD1D_ = observation type that holfs sunshine duration
           skip_upload = false
           log_url = false
   ```

4) restart weewx

   for SysVinit systems:

   ```shell
   sudo /etc/init.d/weewx stop
   sudo /etc/init.d/weewx start
   ```

   for systemd systems:

   ```shell
   sudo systemctl stop weewx
   sudo systemctl start weewx
   ```

## Configuration instructions:

* Station ID and WNS-Kennung are mandatory. You get them from the Wetternetz
  Sachsen administrator. 

* Set `T5AKT_ = None` if you do not measure 5cm temperature. Otherwise give the
  WeeWX observation type you use for that value.

* Set `SOD1D_` to the observation type of sun duration. If you do not have
  such an observation type set it to None.

* Set `TSOI10`, `TSOI20`, and `TSOI50` to the appropriate WeeWX observation
  types if you measure soil temperatures. The number is the depth in cm.

* Set skip_upload to true to do all the calculation and preparation without
  doing the real upload. This is for testing. Set log_url=true to see what
  would be uploaded.

* Set log_url to true to log the URL sent to Wetternetz Sachsen to syslog.
  This is for trouble shooting.

## Links:

* [WeeWX homepage](http://weewx.com) - [WeeWX Wiki](https://github.com/weewx/weewx/wiki)
* [Wöllsdorf weather conditions](https://www.woellsdorf-wetter.de)
