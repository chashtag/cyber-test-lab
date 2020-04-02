import os
import urllib.request
from urllib.error import ContentTooShortError, HTTPError
from socket import socket
import ssl
import hashlib
import datetime
import OpenSSL
import requests
import magic
import json
import gzip
import base64
import re
import mysql.connector as mysql
import defusedxml.ElementTree as ET

from bs4 import BeautifulSoup
from google.cloud import bigquery
from google.cloud import storage


class MirrorCrawler(object):

    def __init__(self):
        self.config = {
            'mirror': os.environ.get('MIRROR'),
            'project': os.environ.get('PROJECT'),
            'bq_dataset': os.environ.get('BQ_DATASET'),
            'bq_table': os.environ.get('BQ_TABLE'),
            'bucket_name': os.environ.get('BUCKET_NAME'),
            'bucket_path': os.environ.get('BUCKET_PATH'),
            'local_path': os.environ.get('LOCAL_PATH'),
            'use_sql':  os.environ.get('USE_SQL'),
            'sql_server': os.environ.get('SQL_SERVER'),
            'sql_username': os.environ.get('SQL_USERNAME'),
            'sql_password': os.environ.get('SQL_PASSWORD'),
            'sql_db': os.environ.get('SQL_DB'),
            'sql_table':  os.environ.get('SQL_TABLE'),
            }
        self.sess = requests.session()
        self.sess.verify = os.environ.get('ALLOW_INSECURE_SSL')
        self.repo_type = None
        self.only_export_packages = True
        self.group_insert_count = 2500 # > 0 enables batch inserts 

        # lets disable Google cloud stuff for now while I figure out free tier pricing, or make and alt solution
        if not os.environ.get('NO_GCSTORAGE'):
            self.storage_client = storage.Client()
        else:
            self.storage_client = None
        
        if not os.environ.get('NO_GBQ'):
            self.bq_client = bigquery.Client()
            self.table_id = self.config['project'] + '.' + \
                       self.config['bq_dataset'] + '.' + \
                       self.config['bq_table']
            self.table = self.bq_client.get_table(self.table_id)
            print('Setup to use Google Big Query')
        else:
            print('Not using Google Big Query')
            self.bq_client = None
            self.table_id = None
            self.table = None
        
        if self.config.get('use_sql'):
            self.mydb = mysql.connect(
            host = self.config.get('sql_server'),
            user = self.config.get('sql_username'),
            passwd = self.config.get('sql_password'),
            database = self.config.get('sql_db'))
            print('Setup to use SQL')
        else:
            print('Not using SQL')
            self.mydb = None


        self.xlator_dict = {'ada': {'field': 'ada', 'type': str},
                            'adherence': {'field': 'adherence', 'type': str},
                            'arch': {'field': 'arch', 'type': str},
                            'architecture': {'field': 'architecture', 'type': str},
                            'book': {'field': 'book', 'type': str},
                            'breaks': {'field': 'breaks', 'type': str},
                            'build-essential': {'field': 'build_essential', 'type': str},
                            'build-ids': {'field': 'build_ids', 'type': str},
                            'builder': {'field': 'builder', 'type': str},
                            'built-using': {'field': 'built_using', 'type': str},
                            'checksum': {'field': 'checksum', 'type': str},
                            'checksum_type': {'field': 'checksum_type', 'type': str},
                            'conflicts': {'field': 'conflicts', 'type': str},
                            'crush': {'field': 'crush', 'type': str},
                            'cython': {'field': 'cython', 'type': str},
                            'decode': {'field': 'decode', 'type': str},
                            'depends': {'field': 'depends', 'type': str},
                            'description': {'field': 'description', 'type': str},
                            'description-md5': {'field': 'description_md5', 'type': str},
                            'endgame': {'field': 'endgame', 'type': str},
                            'enhances': {'field': 'enhances', 'type': str},
                            'essential': {'field': 'essential', 'type': str},
                            'filename': {'field': 'filename', 'type': str},
                            'filter': {'field': 'filter', 'type': str},
                            'format': {'field': 'format', 'type': str},
                            'formats': {'field': 'formats', 'type': str},
                            'framework': {'field': 'framework', 'type': str},
                            'french': {'field': 'french', 'type': str},
                            'functions': {'field': 'functions', 'type': str},
                            'go-import-path': {'field': 'go_import_path', 'type': str},
                            'gui': {'field': 'gui', 'type': str},
                            'homepage': {'field': 'homepage', 'type': str},
                            'hosting': {'field': 'hosting', 'type': str},
                            'hpi': {'field': 'hpi', 'type': str},
                            'installed-size': {'field': 'size_installed', 'type': str},
                            'installer-menu-item': {'field': 'installer_menu_item','type': str},
                            'interface': {'field': 'interface', 'type': str},
                            'kernel-version': {'field': 'kernel_version', 'type': str},
                            'lasso': {'field': 'lasso', 'type': str},
                            'library': {'field': 'library', 'type': str},
                            'lisp': {'field': 'lisp', 'type': str},
                            'location': {'field': 'location', 'type': str},
                            'lua': {'field': 'lua', 'type': str},
                            'lua-versions': {'field': 'lua_versions', 'type': str},
                            'maintainer': {'field': 'maintainer', 'type': str},
                            'masses': {'field': 'masses', 'type': str},
                            'md5sum': {'field': 'md5sum', 'type': str},
                            'method': {'field': 'method', 'type': str},
                            'mkl': {'field': 'mkl', 'type': str},
                            'multi-arch': {'field': 'multi_arch', 'type': str},
                            'name': {'field': 'name', 'type': str},
                            'nmh': {'field': 'nmh', 'type': str},
                            'original-maintainer': {'field': 'original_maintainer','type': str},
                            'package': {'field': 'package', 'type': str},
                            'packager': {'field': 'packager', 'type': str},
                            'pkgid': {'field': 'pkgid', 'type': str},
                            'planescape': {'field': 'planescape', 'type': str},
                            'png': {'field': 'png', 'type': str},
                            'pre-depends': {'field': 'pre_depends', 'type': str},
                            'prefixes': {'field': 'prefixes', 'type': str},
                            'priority': {'field': 'priority', 'type': str},
                            'provides': {'field': 'provides', 'type': str},
                            'python': {'field': 'python', 'type': str},
                            'python-egg-name': {'field': 'python_egg_name', 'type': str},
                            'python-hdf4': {'field': 'python_hdf4', 'type': str},
                            'python-version': {'field': 'python_version', 'type': str},
                            'qusage': {'field': 'qusage', 'type': str},
                            'r': {'field': 'r', 'type': str},
                            'rails': {'field': 'rails', 'type': str},
                            'raptor': {'field': 'raptor', 'type': str},
                            'received': {'field': 'received', 'type': str},
                            'recommends': {'field': 'recommends', 'type': str},
                            'replaces': {'field': 'replaces', 'type': str},
                            'ruby-versions': {'field': 'ruby_versions', 'type': str},
                            'section': {'field': 'section', 'type': str},
                            'services': {'field': 'services', 'type': str},
                            'sha256': {'field': 'sha256', 'type': str},
                            'shim': {'field': 'shim', 'type': str},
                            'size': {'field': 'size', 'type': str},
                            'size_archive': {'field': 'size_archive', 'type': str},
                            'size_installed': {'field': 'size_installed', 'type': str},
                            'size_package': {'field': 'size_package', 'type': str},
                            'source': {'field': 'source', 'type': str},
                            'subarchitecture': {'field': 'subarchitecture', 'type': str},
                            'suggests': {'field': 'suggests', 'type': str},
                            'summary': {'field': 'summary', 'type': str},
                            'support': {'field': 'support', 'type': str},
                            'synthesizer': {'field': 'synthesizer', 'type': str},
                            'system': {'field': 'system', 'type': str},
                            'tads3-version': {'field': 'tads3_version', 'type': str},
                            'tag': {'field': 'tag', 'type': str},
                            'time_build': {'field': 'time_build', 'type': str},
                            'time_file': {'field': 'time_file', 'type': str},
                            'timestamps': {'field': 'timestamps', 'type': str},
                            'tldr': {'field': 'tldr', 'type': str},
                            'toolkit': {'field': 'toolkit', 'type': str},
                            'tools': {'field': 'tools', 'type': str},
                            'ufo': {'field': 'ufo', 'type': str},
                            'url': {'field': 'url', 'type': str},
                            'utf8-cpp': {'field': 'utf8_cpp', 'type': str},
                            'utilities': {'field': 'utilities', 'type': str},
                            'version': {'field': 'version', 'type': str},
                            'version_epoch': {'field': 'version_epoch', 'type': str},
                            'version_rel': {'field': 'version_rel', 'type': str},
                            'version_ver': {'field': 'version_ver', 'type': str},
                            'writebuffer': {'field': 'writebuffer', 'type': str},
                            'x-cargo-built-using': {'field': 'x_cargo_built_using','type': str},
                            'xstrings': {'field': 'xstrings', 'type': str},
                            'zone': {'field': 'zone', 'type': str},
                            'repo_url': {'field': 'repo_url', 'type': str},
                            }


    def parse(self, url, filename) -> list:
        with open(filename, 'r') as f:
            soup = BeautifulSoup(f, 'html.parser')
        links = soup.find_all('a')

        filtered_links = {}
        for link in links:
            print(link)
            href = link.get('href')
            if (href.startswith(url) or not href.startswith('http')) and not \
                    (href.startswith('?') or href.startswith('/')):
                filtered_links[href] = 1
        try:
            os.unlink(filename)
        except FileNotFoundError as e:
            raise Exception('could not delete: ' + str(e))

        return list(filtered_links.keys())
    
    def parse_rpm_entity(self,xml_data) -> dict:
        rpm_data = {}
        xmlns = ''
        if xml_data.tag.startswith('{'):
            xmlns = xml_data.tag.split('{')[1].split('}')[0]
        name = None
        arch = None
        version_epoch = None
        version_ver = None
        version_rel = None
        checksum = None
        checksum_type = None
        pkgid = None
        summary = None
        description = None
        package = None
        packager = None
        r_url = None
        time_file = None
        time_build = None
        size_package = None
        size_installed = None
        size_archive = None
        location = None
        r_format = None
        
        if not xml_data.find('{{{0}}}name'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}name'.format(xmlns))
            name = ent.text
        
        if not xml_data.find('{{{0}}}arch'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}arch'.format(xmlns))
            arch = ent.text
        
        if not xml_data.find('{{{0}}}arch'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}arch'.format(xmlns))
            arch = ent.text

        if not xml_data.find('{{{0}}}version'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}version'.format(xmlns))
            version_epoch = ent.get('epoch')
            version_rel = ent.get('rel')
            version_ver = ent.get('ver')
        
        if not xml_data.find('{{{0}}}checksum'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}checksum'.format(xmlns))
            checksum = ent.text
            checksum_type = ent.get('type')
            if ent.get('pkgid') == 'YES':
                pkgid = checksum

        if not xml_data.find('{{{0}}}summary'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}summary'.format(xmlns))
            summary = ent.text
        
        if not xml_data.find('{{{0}}}description'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}description'.format(xmlns))
            description = ent.text
        
        if not xml_data.find('{{{0}}}packager'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}packager'.format(xmlns))
            packager = ent.text
        
        if not xml_data.find('{{{0}}}packager'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}packager'.format(xmlns))
            packager = ent.text
        
        if not xml_data.find('{{{0}}}url'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}url'.format(xmlns))
            r_url = ent.text
        
        if not xml_data.find('{{{0}}}time'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}time'.format(xmlns))
            time_file = ent.get('file')
            time_build = ent.get('build')

        if not xml_data.find('{{{0}}}size'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}size'.format(xmlns))
            size_package = ent.get('package')
            size_installed = ent.get('installed')
            size_archive = ent.get('archive')
        
        if not xml_data.find('{{{0}}}location'.format(xmlns)) == None:
            ent = xml_data.find('{{{0}}}location'.format(xmlns))
            location = ent.get('href')
        
        #if not xml_data.find('{{{0}}}format'.format(xmlns)) == None:
        #    ent = xml_data.find('{{{0}}}format'.format(xmlns))
        #    r_format = ent.text

        return {'name' : name,
                'arch' : arch,
                'version_epoch' : version_epoch,
                'version_ver' : version_ver,
                'version_rel' : version_rel,
                'checksum' : checksum,
                'checksum_type' : checksum_type,
                'pkgid' : pkgid,
                'summary' : summary,
                'description' : description,
                'package' : package,
                'packager' : packager,
                'url' : r_url,
                'time_file' : time_file,
                'time_build' : time_build,
                'size_package' : size_package,
                'size_installed' : size_installed,
                'size_archive' : size_archive,
                'location' : location,
                'format' : None,
                }

    def ident_repo(self, url) -> str:
        if not url.endswith('/'):
            url += '/'
        if self.sess.get(url + 'repodata/repomd.xml').status_code == 200:
            self.repo_type = 'Yum'
        elif self.sess.get(url + 'Release').status_code == 200:
            self.repo_type = 'Deb'
        else:
            self.repo_type = None
        return self.repo_type
            
    def get_package_list_yum(self, repo) -> dict:
        xmlns = ''
        repo_data = {
            'type' : 'yum',
            'location': repo,
            'packages':{},
            'repomd':{},
        }
        
        data = self.sess.get(repo + 'repodata/repomd.xml').text
        root = ET.fromstring(data)
        
        if root.tag.startswith('{'):
            xmlns = root.tag.split('{')[1].split('}')[0]

        for child in root:
            if child.attrib.get('type'):
                location = None
                checksum = None
                checksum_type = None
                open_checksum = None
                open_checksum_type = None
                size = None
                open_size = None
                timestamp = None
                
                if not child.find('{{{0}}}location'.format(xmlns)) == None:
                    ent = child.find('{{{0}}}location'.format(xmlns))
                    location = ent.get('href')

                if not child.find('{{{0}}}checksum'.format(xmlns)) == None:
                    ent = child.find('{{{0}}}checksum'.format(xmlns))
                    checksum_type = ent.get('type')
                    checksum = ent.text

                if not child.find('{{{0}}}open-checksum'.format(xmlns)) == None:
                    ent = child.find('{{{0}}}open-checksum'.format(xmlns))
                    open_checksum_type = ent.get('type')
                    open_checksum = ent.text
                
                if not child.find('{{{0}}}size'.format(xmlns)) == None:
                    ent = child.find('{{{0}}}size'.format(xmlns))
                    size = ent.text
                
                if not child.find('{{{0}}}size'.format(xmlns)) == None:
                    ent = child.find('{{{0}}}size'.format(xmlns))
                    open_size = ent.text
                
                if not child.find('{{{0}}}timestamp'.format(xmlns)) == None:
                    ent = child.find('{{{0}}}timestamp'.format(xmlns))
                    timestamp = ent.text
                

                repo_data['repomd'][child.attrib.get('type')] = \
                    {'location': location,
                        'checksum': checksum,
                        'checksum-type': checksum_type,
                        'open-checksum': open_checksum,
                        'open-checksum-type': open_checksum_type,
                        'size': size,
                        'open-size': open_size,
                        'timestamp': timestamp,
                    }
        
        for data_set in repo_data['repomd']:
            data = None
            data_set_loc = repo_data['repomd'][data_set].get('location')
            data = self.sess.get(repo+data_set_loc).content

            if data_set_loc.endswith('.xml.gz'):
                repo_data['repomd'][data_set]['raw_xml'] = gzip.decompress(data).decode('utf-8')

            elif data_set_loc.endswith('.xml'):
                repo_data['repomd'][data_set]['raw_xml'] = data.decode('utf-8')
            
            else:
                repo_data['repomd'][data_set]['raw_data'] = base64.b64encode(data).decode('utf-8')
            
            if data_set == 'primary': # lets go fast for now and work with the primary set once we see it
                break
            
        if repo_data['repomd'].get('primary') and repo_data['repomd']['primary'].get('raw_xml'):

            root = ET.fromstring(repo_data['repomd']['primary'].get('raw_xml'))
            xmlns = ''
            if root.tag.startswith('{'):
                xmlns = root.tag.split('{')[1].split('}')[0]
            
            if root.attrib.get('packages'):
                repo_data['packages_count'] = root.attrib.get('packages')

            for child in root:
                if child.attrib.get('type') == "rpm":
                    _rpm = self.parse_rpm_entity(child)
                    if not repo_data['packages'].get(_rpm.get('pkgid')):
                        repo_data['packages'][_rpm.get('pkgid')] = _rpm
                    else:
                        raise Exception('Duplicate Package ID: {}'.format(_rpm.get('pkgid')))
                else:
                    print('unk pkg type {}'.format(child.attrib.get('type')))

            if not repo_data['packages_count']:
                repo_data['packages_count'] = len(repo_data['packages'])
            else:
                repo_data['packages_count'] = int(repo_data['packages_count'])

        else:
            raise Exception('Could not find primary data set')

        return repo_data
            
    def get_package_list_deb(self, repo) -> dict:
        
        hash_types = ['MD5Sum','SHA256']
        data = self.sess.get(repo + 'Release').text
        data_split = re.split(r'([A-Z\-a-z0-9]+)\:\s', data, re.DOTALL)[1:]
        release_dict = dict(zip(*[map(lambda x: x.strip(), data_split[i::2]) for i in [0,1]]))
        release_dict['packages'] = {}

        if release_dict.get('Architectures'):
            release_dict['Architectures'] = release_dict.get('Architectures').split(' ')
        if release_dict.get('Components'):
            release_dict['Components'] = release_dict.get('Components').split(' ')
        for hash_type in hash_types:
            if release_dict.get(hash_type):
                find = re.findall(r'\b([a-zA-Z0-9\/\-\.\_]+)',release_dict.get(hash_type).replace('\n ','\n'))
                _x = list(zip(*[find[i::3] for i in [0,1,2]]))
                build_list = []
                for i in _x:
                    build_list.append({'hash': i[0],
                                       'size': i[1],
                                       'location': i[2],                
                                        })
                release_dict[hash_type] = build_list
        
        for x in release_dict['MD5Sum']:
            if x.get('location') and x['location'].endswith('Packages.gz'): # look at Packages.gz only, for now
                data = self.sess.get(repo + x['location']).content
                data = gzip.decompress(data).decode('utf-8') # does it ever not come as utf8?
                if data:
                    for item in data.split('\n\n'):
                        parsed = self.parse_deb_entity(item)
                        
                        if parsed.get('SHA256'):
                            _checksum = parsed.get('SHA256')
                        elif parsed.get('MD5sum'):
                            _checksum = parsed.get('MD5sum')
                        elif parsed.get('MD5um'):
                            _checksum = parsed.get('MD5sum')
                        else:
                            _checksum = "UNK-"+hashlib.md5(os.urandom(16)).hexdigest()
                        parsed.update({'checksum':_checksum})
                        release_dict['packages'][parsed.get('MD5sum')] = parsed
        return release_dict

                

    def parse_deb_entity(self,data):
        
        ### need to revist this, and tweek it for "tags:"
        #data_split = re.split(r'([A-Z\-a-z0-9]+)\:\s', data, re.DOTALL)[1:]
        #dict_map = dict(zip(*[map(lambda x: x.strip(),data_split[i::2]) for i in [0,1]]))
        #if dict_map.get('Depends'):
        #    dict_map['Depends'] = dict_map['Depends'].split(',')
        #print(dict_map)

        data_split = [x.split(': ') for x in data.split('\n') if ': ' in x]
        normalize = [x if len(x) == 2 else [x[0]]+[': '.join(x[1:])] for x in data_split]
        
        normalize = dict(normalize)
        #if normalize.get('Depends'):
            #normalize['Depends'] = dict_map['Depends'].split(',')

        return normalize
        
    def download_lf(self, url, filename):
        # Large file download support
        with self.s.get(url, stream=True) as r:
            _total = 0 
            r.raise_for_status()
            with open(fp, 'wb') as f:
                for chunk in r.iter_content(chunk_size=self.block_size):
                    if chunk:
                        f.write(chunk)
                        _total += len(chunk) # we can implement progress bars later
                f.flush()
            
    def download(self, url, filename):
        server_cert = None
        cert_valid = None

        # capture server cert
        if url.startswith('https'):
            hostname = url.split('/')[2]
            cert = ssl.get_server_certificate((hostname, 443))
            x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
            server_cert = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM,
                                                                                                        x509)

        try:
            cert_valid = True
            # req = urllib.request.Request(
            #         url,
            #         data=None,
            #         headers={
            #                 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.116 Safari/537.36'
            #         }
            # )
            # urllib.request.urlretrieve(url, filename)
            response = urllib.request.urlopen(url)
            data = response.read()
            with open(filename, 'wb') as f:
                f.write(data)
        except ssl.SSLError as e:
            try:
                cert_valid = False
                context = ssl._create_unverified_context()
                response = urllib.request.urlopen(url, context=context)
                data = response.read()
                with open(filename, 'wb') as f:
                    f.write(data)
            except Exception as e:
                raise e
        except urllib.error.URLError as e:
            raise e
        except Exception as e:
            # todo: be more precise with exception handling
            raise e

        return server_cert, cert_valid

    def mirror(self, url, cert, directory):
        index_path = directory + '/index.html'

        links = self.parse(url, index_path)
        for link in links:

            # avoid previous directory links
            if '/../' in link:
                continue
            deeper_url = url + '/' + link

            if link.endswith('/'):
                basename = link.split('/')[-2]
                try:
                    os.mkdir(directory + '/' + basename)
                except FileExistsError as e:
                    pass
                deeper_directory = directory + '/' + basename
                self.download(deeper_url, deeper_directory + '/index.html')
                self.mirror(deeper_url, cert, deeper_directory)
            else:
                basename = link.split('/')[-1]
                path = directory + '/' + basename
                self.download(deeper_url, path)
                self.process_file(deeper_url, cert, path)
    
    def insert_rows(self,data) -> list:
        print(data)
        ret = []
        if not os.environ.get('NO_GBQ'):
            ret = self.bq_client.insert_rows_json(self.table, data)
            if ret:
                print('problem on insert {}'.format(ret))
        
        if self.config.get('use_sql'):
            _keys = []
            prep = []
            for i in data:
                _keys.extend(i.keys())

            _keys = set(_keys)
            prep.extend([tuple([i.get(k) for k in _keys]) for i in data])
            
            sql = 'INSERT IGNORE INTO {0} ({1}) VALUES {2}'.format(self.config.get('sql_table'), ','.join(_keys)
                , ''.join([str(x).replace('None','NULL').replace('"','\"') for x in prep]) )
            
            sql = 'INSERT IGNORE INTO {0} ({1}) VALUES ({2})'.format(self.config.get('sql_table'), ','.join(_keys),','.join(['%s']*len(_keys)))

            _cursor = self.mydb.cursor()
            ret = _cursor.executemany(sql, [tuple([str(a).replace('None','NULL') for a in x ]) for x in prep])
            self.mydb.commit()
            
        print('Inserted {0} rows'.format(len(data)))
        return ret


    def process_packages(self,url,packages) -> int:
        _total = 0
        if type(packages) == dict:
            is_dict = True
        else:
            is_dict = False
        ready_to_insert = []
        for p in packages:
            _total += 1
            if is_dict:
                p = packages[p]
                p.update({'repo_url':url})
            x = self.xlate(p)

            if self.group_insert_count:
                ready_to_insert.append(x)
            
            if len(ready_to_insert) >= self.group_insert_count:
                self.insert_rows(ready_to_insert)
                ready_to_insert = []
        
        if len(ready_to_insert): # finish out batch
            self.insert_rows(ready_to_insert)
            ready_to_insert = []
        print('Total inserted: {0}'.format(_total))

        return _total
            
            
            #rows_to_insert = [{'name':'asd','checksum':'asd'},{'name':'asdd','checksum':'aq'}]
            #print(self.bq_client.insert_rows_json(table, rows_to_insert))
            

    
    def process_file(self, url, cert, path):
        filename = os.path.basename(path)
        with open(path, 'rb') as f:
            file_bytes = f.read()
        sha256 = hashlib.sha256(file_bytes).hexdigest()

        query = "SELECT " \
                "  filename AS filename, " \
                "  sha256 AS sha256, " \
                "FROM {}.{} " \
                "WHERE filename = '{}' AND sha256 = '{}'".format(self.config['bq_dataset'],
                                                                 self.config['bq_table'],
                                                                 filename,
                                                                 sha256)
        if self.bq_client:
            query_job = self.bq_client.query(query)
            results = query_job.result()
        else:
            results = []

        if len(list(results)) == 0:
            now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            server_cert = u''
            if cert[0]:
                server_cert = cert[0].decode('utf-8')
            else:
                server_cert = None
            rows_to_insert = [(filename, sha256, url, now, server_cert, cert[1])]
            table_id = self.config['project'] + '.' + \
                       self.config['bq_dataset'] + '.' + \
                       self.config['bq_table']
        
        if self.bq_client:
                table = self.bq_client.get_table(table_id)
                errors = self.bq_client.insert_rows(table, rows_to_insert)
                if errors:
                    raise Exception('bq insert failed on ' + str(rows_to_insert))
                else:
                    print('[+] inserted ' + str(rows_to_insert))
            
        if self.storage_client:
            bucket_name = self.config['bucket_name']
            bucket = self.storage_client.get_bucket(bucket_name)
            url_path = url.replace('http://', '').replace('https://', '').replace('//', '/')
            blob = bucket.blob(self.config['bucket_path'] + url_path + '/' + filename)
            blob.upload_from_filename(path)
        print('[+] uploaded ' + path + ' to GCS')

        try:
            os.unlink(path)
        except IOError as e:
            raise Exception('failed to delete ' + path + ': ' + str(e))

    def xlate(self, data, for_sql=False):
        def try_trans(t,d):
            try:
                return t(d)
            except:
                return d

        return dict([(self.xlator_dict[k.lower()]['field'],try_trans(self.xlator_dict[k.lower()]['type'],v)) for \
            k,v in data.items() if self.xlator_dict.get(k.lower())])


        pass


def main():
    url = os.environ.get('MIRROR')

    mc = MirrorCrawler()
    
    repo_type = mc.ident_repo(url)
    
    if repo_type == 'Yum':
        ret = mc.get_package_list_yum(url)

    elif repo_type == 'Deb':
        ret = mc.get_package_list_deb(url)
    
    else:
        raise Exception('Unknown repo')
        exit()
    
    mc.process_packages(url,ret.get('packages'))
        
    
        

        

if __name__ == '__main__':
    main()



