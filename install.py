# installer WNS
# Copyright 2020 Johanna Roedenbeck
# Distributed under the terms of the GNU Public License (GPLv3)
# derived from Windy

from weecfg.extension import ExtensionInstaller

def loader():
    return WnsInstaller()

class WnsInstaller(ExtensionInstaller):
    def __init__(self):
        super(WnsInstaller, self).__init__(
            version="0.5",
            name='WNS',
            description='Upload weather data to WNS.',
            author="Johanna Roedenbeck",
            author_email="",
            restful_services='user.wns.Wns',
            config={
                'StdRESTful': {
                    'Wns': {
                        'enable':'true',
                        'station': 'replace_me',
                        'api_key': 'replace_me',
                        'T5AKT_':'None',
                        'skip_upload':'false',
                        'log_url':'false'}}},
            files=[('bin/user', ['bin/user/wns.py'])]
            )
