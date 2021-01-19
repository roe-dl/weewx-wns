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
        T5AKT_ = column that holds 5cm-temperature

4) restart weewx

sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start
