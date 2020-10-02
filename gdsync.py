
#
#    Copyright 2020 Three Guys Labs, LLC
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
#

import io
import json
import pickle
import os.path
import sys
import tarfile
import tempfile

from datetime import datetime

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaInMemoryUpload

CONFIG_VERSION = '0.1a'

# ===============================================================================
# ===============================================================================
#
# Credential related functions
#

SCOPES = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.metadata.readonly'
    ]

def get_credentials():
    config_dir = get_app_directory()
    token_path = os.path.join(config_dir, 'token.pickle')
    creds_path = os.path.join(config_dir, 'credentials.json')

    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This opens a browser window to let user login
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
    
    return creds

# ===============================================================================
# ===============================================================================
#
# TARchive related functions
#

def create_archive(src_path):
    if not os.path.exists(src_path):
        raise ValueError('Source path: %s does not exist' % src_path)

    now = datetime.now()
    project_name = os.path.basename(src_path)
    dst_name = '%s-%s.tar.gz' % (project_name, now.strftime('%Y%m%d-%H%M%S'))

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        tar.add(src_path, arcname=project_name)

    buffer.seek(0)
    return dst_name, buffer

def verify_archive(tar, project_name):
    info = tar.getmember(project_name)
    if info is None:
        raise ValueError('Project %s was not found in the archive!' % project_name)
    if not info.isdir():
        raise ValueError('The project %s is not a directory in the archive' % project_name)

    print('Scanning tarfile contents...')
    prefix = '%s/' % project_name
    for m in tar.getmembers():
        if not m.name.startswith(prefix) and m.name != project_name:
            raise ValueError('Found illegal file in project archive: %s' % m.name)
        else:
            print(m.name)
    
    return True

def extract_archive(project_name, dst_path, buffer):
    buffer.seek(0)
    with tarfile.open(fileobj=buffer, mode='r:gz') as tar:
        if verify_archive(tar, project_name):
            print('Extracting project: %s' % project_name)
            tar.extractall(path=dst_path)

# ===============================================================================
# ===============================================================================
#
# Project config related functions and classes
# Drive Syncing
#

def get_app_directory():
    config_dir = os.path.join(os.path.expanduser('~'), '.gdsync')
    if not os.path.isdir(config_dir):
        os.makedirs(config_dir, mode=0o755)
        os.makedirs(os.path.join(config_dir, 'backup'), mode=0o755)
    return config_dir

def get_default_config():
    return { 'version': CONFIG_VERSION, 'folder': 'gdsync-projects' }

def get_config():
    config_dir = get_app_directory()
    config_file = os.path.join(config_dir, 'gdsync.json')
    if os.path.isfile(config_file):
        with open(config_file, 'rt') as fh:
            return config_dir, json.load(fh)
    
    return config_dir, get_default_config()

def project_from_config(project_name, config=None, creds=None):
    path = project_name
    name = os.path.basename(project_name) if os.path.isdir(project_name) else project_name
    if config is None:
        config = get_default_config()

    prj = SyncerProject(name=name, path=path,
                        folder=config['folder'],
                        backups=config.get('backups'))
    syncer = DriveSyncer(creds=creds)
    return prj, syncer

class SyncerProject:
    def __init__(self, name, path=None, folder='gdsync-projects', backups=None):
        self.name = name
        self.path = path
        self.folder = folder
        self.backups = backups

    def should_backup(self):
        return self.backups is not None

class DriveSyncer:
    def __init__(self, creds=None):
        if creds is None:
            creds = get_credentials()

        self.service = build('drive', 'v3', credentials=creds)
        
    def make_folder(self, folder_name):
        resp = self.service.files().list(q="mimeType='application/vnd.google-apps.folder' and name='%s'" % folder_name,
                                        fields='nextPageToken, files(id, name)',
                                        corpora='user').execute()
        
        for file in resp.get('files', []):
            return file.get('id')

        # Create the folder
        body = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
        }
        file = self.service.files().create(body=body, fields='id').execute()
        return file.get('id')

    def upload_project(self, folder_id, file_name, buffer, mimetype='application/tar+gzip'):
        metadata = { 'name': file_name, 'parents': [ folder_id ] }
        media = MediaInMemoryUpload(buffer.getvalue(), mimetype=mimetype)
        file = self.service.files().create(body=metadata, media_body=media, fields='id').execute()
        return file.get('id'), file_name

    def find_latest(self, folder_id, project_name):
        query = ("mimeType='application/tar+gzip' and name contains '%s' and '%s' in parents"
                % (project_name, folder_id))

        resp = self.service.files().list(orderBy='name desc', q=query,
                                        fields='nextPageToken, files(id, name)', corpora='user').execute()
        for file in resp.get('files', []):
            return file.get('id'), file.get('name')

        return None, None

    def download_project(self, file_id, project_name, output_path=None):
        request = self.service.files().get_media(fileId=file_id)
        
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print('Download %d%%.' % int(status.progress() * 100))
            print('Buffer size: ', len(buffer.getvalue()))

        # Start at the beginning
        # buffer.seek(0)
        return buffer

# ===============================================================================
# ===============================================================================
#
# Entry points
#
def upload_projects(projects):
    app_dir, cfg_json = get_config()

    for project_path in projects:
        config, syncer = project_from_config(project_path, cfg_json)

        # Get or create google drive folder
        folder_id = syncer.make_folder(config.folder)
        print('Syncing to folder ["%s"::"%s"]' % (config.folder, folder_id))

        # Create in-memory archive of the project
        archive_name, buffer = create_archive(project_path)
        print('Created project archive %s size: %d bytes' % (archive_name, sys.getsizeof(buffer)))

        # Upload to google drive
        file_id, file_name = syncer.upload_project(folder_id, archive_name, buffer)
        print('Uploaded %d bytes to file ["%s"::"%s"]' % (sys.getsizeof(buffer), file_name, file_id))

def download_projects(projects):
    dst_path = os.path.abspath('.')
    for project_name in projects:
        config, syncer = project_from_config(project_name)

        if os.path.isdir(project_name) or os.path.isfile(project_name):
            raise ValueError('%s already exists, please delete before proceeding!' % project_name)

        # Get or create google drive folder
        folder_id = syncer.make_folder(config.folder)
        print('Syncing from folder {"%s":"%s"}' % (config.folder, folder_id))

        # Lookup the latest project file
        file_id, file_name = syncer.find_latest(folder_id, project_name)
        if file_id is None:
            print('No archives found with the name: %s' % project_name)
            return

        print('Found archive: {%s:%s}' % (file_name, file_id))
        buffer = syncer.download_project(file_id, project_name, project_name)
        extract_archive(project_name, dst_path, buffer)
