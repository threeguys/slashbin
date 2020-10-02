# slashbin
Useful scripts and helpful commands for personal use

# gdsync

|Command|Syntax|Description|
|-------|------|-----------|
|gd-upload| gd-upload *path* | Tar/gzips a directory and uploads a timestamped archive to Google Drive |
|gd-download| gd-download *name* | Downloads latest archive file (based on name) and unzips to the current directory |

## Setup
In order to setup the *gdsync* project, you will need to <a href="https://developers.google.com/drive/api/v3/quickstart/python#step_2_install_the_google_client_library">install the Google Client Library for Python</a>:

```
pip3 install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
```
