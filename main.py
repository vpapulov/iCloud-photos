import contextlib
import sys
import os

import click
import requests
import warnings
from pprint import pprint
from pyicloud import PyiCloudService
from urllib3.exceptions import InsecureRequestWarning

from config import ICLOUD_LOGIN, STORE_FOLDER, DOWNLOAD_LIMIT

# Handle certificate warnings by ignoring them
old_merge_environment_settings = requests.Session.merge_environment_settings


@contextlib.contextmanager
def no_ssl_verification():
    opened_adapters = set()

    def merge_environment_settings(self, url, proxies, stream, verify, cert):
        # Verification happens only once per connection so we need to close
        # all the opened adapters once we're done. Otherwise, the effects of
        # verify=False persist beyond the end of this context manager.
        opened_adapters.add(self.get_adapter(url))

        settings = old_merge_environment_settings(
            self, url, proxies, stream, verify, cert
        )
        settings["verify"] = False

        return settings

    requests.Session.merge_environment_settings = merge_environment_settings

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InsecureRequestWarning)
            yield
    finally:
        requests.Session.merge_environment_settings = old_merge_environment_settings

        for adapter in opened_adapters:
            try:
                adapter.close()
            except:
                pass


password = input('Password:')

api = PyiCloudService(ICLOUD_LOGIN, password)
if api.requires_2sa:
    print("Two-factor authentication required. Your trusted devices are:")

    devices = api.trusted_devices
    for i, device in enumerate(devices):
        print(
            "  %s: %s"
            % (i, device.get("deviceName", "SMS to %s") % device.get("phoneNumber"))
        )

    device = click.prompt("Which device would you like to use?", default=0)
    device = devices[device]
    if not api.send_verification_code(device):
        print("Failed to send verification code")
        sys.exit(1)

    code = click.prompt("Please enter validation code")
    if not api.validate_verification_code(device, code):
        print("Failed to verify verification code")
        sys.exit(1)

# This request will not fail, even if using intercepting proxies.
with no_ssl_verification():
    pprint(api.account)

    base_folder = STORE_FOLDER
    downloaded_count = 0
    for idx, photo in enumerate(api.photos.all.photos):
        if photo.id == 'AaHHQJN+jHexyB7jiQD5LYt+nx+4':
            photo_date = photo.added_date  # проблемная фотка какая-то ассет дейт не извлекается
        else:
            photo_date = photo.asset_date
        folder = base_folder + str(photo_date.year) + '\\' + photo_date.strftime('%Y-%m-%d') + '\\'
        if not os.path.isdir(folder):
            os.makedirs(folder)
        photo_ts = photo_date.timestamp()
        filename = folder + photo.filename
        if os.path.isfile(filename):
            # file exists
            if os.path.getsize(filename) == photo.size and os.path.getmtime(filename) == photo_ts:
                continue
            else:
                name_and_ext = photo.filename.split('.')
                filename = folder + name_and_ext[0] + '_' + photo_date.strftime('%H-%M-%S') \
                           + '.' + name_and_ext[1] if len(name_and_ext) > 0 else ''
                if os.path.isfile(filename):
                    continue
        url = photo.versions['original']['url']
        print(f'#{downloaded_count + 1} ({idx + 1}) {filename}: {round(photo.size / 1024 / 1024, 1)}Mb')
        response = requests.get(url, allow_redirects=True)
        with open(filename, 'wb') as fo:
            fo.write(response.content)
        os.utime(filename, (photo_ts, photo_ts))
        downloaded_count += 1
        if downloaded_count >= DOWNLOAD_LIMIT:
            print('limited ', downloaded_count)
            break
    print('done')
