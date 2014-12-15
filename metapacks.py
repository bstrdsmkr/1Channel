"""
    1Channel XBMC Addon
    Copyright (C) 2014 Bstrdsmkr

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import os
import string
import time
import urllib
import sys
import xbmc
import xbmcgui
from addon.common.addon import Addon
try: from metahandler import metahandlers
except: xbmc.executebuiltin("XBMC.Notification(%s,%s,2000)" % ('Import Failed','metahandler')); pass
try: from metahandler import metacontainers
except: xbmc.executebuiltin("XBMC.Notification(%s,%s,2000)" % ('Import Failed','metahandler')); pass
import utils

AZ_DIRECTORIES = (ltr for ltr in string.ascii_uppercase)
_1CH = Addon('plugin.video.1channel')

# Links and info about metacontainers.
# Update this file to update the containers.

# Size is in MB

#return dictionary of strings and integers
# noinspection PyDictCreation
def list():
    containers = {}

    #date updated
    containers['date'] = 'Dec 2011'

    #--- Database Meta Container ---#
    #containers['Container_Name.zip'] = (url,size)
    containers['MetaPack-tvshow-A-G.zip'] = ('http://minus.com/meozfvFsy', 624)
    containers['MetaPack-tvshow-H-N.zip'] = ('http://minus.com/meozfvFsy', 498)
    containers['MetaPack-tvshow-O-U.zip'] = ('http://minus.com/meozfvFsy', 690)
    containers['MetaPack-tvshow-V-123.zip'] = ('http://minus.com/meozfvFsy', 133)

    containers['MetaPack-movie-A-A.zip'] = ('http://minus.com/meozfvFsy', 377)
    containers['MetaPack-movie-B-C.zip'] = ('http://minus.com/meozfvFsy', 765)
    containers['MetaPack-movie-D-E.zip'] = ('http://minus.com/meozfvFsy', 490)
    containers['MetaPack-movie-F-G.zip'] = ('http://minus.com/meozfvFsy', 507)
    containers['MetaPack-movie-H-J.zip'] = ('http://minus.com/meozfvFsy', 520)
    containers['MetaPack-movie-K-M.zip'] = ('http://minus.com/meozfvFsy', 785)
    containers['MetaPack-movie-N-R.zip'] = ('http://minus.com/meozfvFsy', 677)
    containers['MetaPack-movie-S-S.zip'] = ('http://minus.com/meozfvFsy', 524)
    containers['MetaPack-movie-T-T.zip'] = ('http://minus.com/meozfvFsy', 904)
    containers['MetaPack-movie-U-123.zip'] = ('http://minus.com/meozfvFsy', 538)
    return containers

# Commented out because url produces a blank page
# def scan_by_letter(section, letter):
#     import traceback
# 
#     try: _1CH.log('Building meta for %s letter %s' % (section, letter))
#     except: pass
#     dlg = xbmcgui.DialogProgress()
#     dlg.create('Scanning %s Letter %s' % (section, letter))
#     if section == 'tvshow':
#         url = BASE_URL + '/alltvshows.php'
#     else:
#         url = BASE_URL + '/allmovies.php'
#     html = get_url(url)
# 
#     pattern = '%s</h2>(.+?)(?:<h2>|<div class="clearer">)' % letter
#     container = re.search(pattern, html, re.S).group(1)
#     item_pattern = re.compile(r'<a.+?>(.+?)</a> \[ (\d{4}) \]</div>')
#     for item in item_pattern.finditer(container):
#         title, year = item.groups()
#         success = False
#         attempts_remaining = 4
#         while attempts_remaining and not success:
#             dlg.update(0, '%s (%s)' % (title, year))
#             try:
#                 __metaget__.get_meta(section, title, year=year)
#                 success = True
#             except Exception, e:
#                 attempts_remaining -= 1
#                 line1 = '%s (%s)' % (title, year)
#                 line2 = 'Failed: %s  attempts remaining' % attempts_remaining
#                 line3 = str(e)
#                 dlg.update(0, line1, line2, line3)
#                 traceback.print_exc()
#             if dlg.iscanceled(): break
#         if dlg.iscanceled(): break
#     return


def zipdir(basedir, archivename):
    from contextlib import closing
    from zipfile import ZipFile, ZIP_DEFLATED

    assert os.path.isdir(basedir)
    with closing(ZipFile(archivename, "w", ZIP_DEFLATED)) as zfile:
        for root, dirs, files in os.walk(basedir):
            #NOTE: ignore empty directories
            for fname in files:
                absfn = os.path.join(root, fname)
                zfn = absfn[len(basedir) + len(os.sep):] #XXX: relative path
                zfile.write(absfn, zfn)


def extract_zip(src, dest):
    try:
        print 'Extracting ' + str(src) + ' to ' + str(dest)
        #make sure there are no double slashes in paths
        src = os.path.normpath(src)
        dest = os.path.normpath(dest)

        #Unzip - Only if file size is > 1KB
        if os.path.getsize(src) > 10000:
            xbmc.executebuiltin("XBMC.Extract(" + src + "," + dest + ")")
        else:
            print '************* Error: File size is too small'
            return False

    except:
        print 'Extraction failed!'
        return False
    else:
        print 'Extraction success!'
        return True


def create_meta_packs():
    import shutil

    global __metaget__
    container = metacontainers.MetaContainer()
    savpath = container.path
    AZ_DIRECTORIES.append('#')
    letters_completed = 0
    letters_per_zip = 27
    start_letter = ''
    end_letter = ''

    for video_type in ('tvshow', 'movie'):
        for letter in AZ_DIRECTORIES:
            if letters_completed == 0:
                start_letter = letter
                __metaget__.__del__()
                shutil.rmtree(container.cache_path)
                __metaget__ = metahandlers.MetaData()

            if letters_completed <= letters_per_zip:
                #scan_by_letter(video_type, letter)
                letters_completed += 1

            if (letters_completed == letters_per_zip
                or letter == '123' or utils.get_dir_size(container.cache_path) > (500 * 1024 * 1024)):
                end_letter = letter
                arcname = 'MetaPack-%s-%s-%s.zip' % (video_type, start_letter, end_letter)
                arcname = os.path.join(savpath, arcname)
                __metaget__.__del__()
                zipdir(container.cache_path, arcname)
                __metaget__ = metahandlers.MetaData()
                letters_completed = 0
                xbmc.sleep(5000)


def copy_meta_contents(root_src_dir, root_dst_dir):
    import shutil

    for root, dirs, files in os.walk(root_src_dir):

        #figure out where we're going
        dest = root_dst_dir + root.replace(root_src_dir, '')

        #if we're in a directory that doesn't exist in the destination folder
        #then create a new folder
        if not os.path.isdir(dest):
            os.mkdir(dest)
            print 'Directory created at: ' + dest

        #loop through all files in the directory
        for this_file in files:
            if not this_file.endswith('.db') and not this_file.endswith('.zip'):
                #compute current (old) & new file locations
                old_loc = os.path.join(root, this_file)

                new_loc = os.path.join(dest, this_file)
                if not os.path.isfile(new_loc):
                    try:
                        shutil.copy2(old_loc, new_loc)
                        try: _1CH.log('File %s copied' % this_file)
                        except: pass
                    except IOError:
                        try: _1CH.log('File %s already exists' % this_file)
                        except: pass
            else:
                try: _1CH.log('Skipping file %s' % this_file)
                except: pass


def install_metapack(pack):
    pass


def install_local_zip(zip_file):
    mc = metacontainers.MetaContainer()
    work_path = mc.work_path
    cache_path = mc.cache_path

    extract_zip(zip_file, work_path)
    xbmc.sleep(5000)
    copy_meta_contents(work_path, cache_path)
    for table in mc.table_list:
        mc._insert_metadata(table)


def install_all_meta():
    all_packs = list()
    skip = ['MetaPack-tvshow-A-G.zip', 'MetaPack-tvshow-H-N.zip', 'MetaPack-tvshow-O-U.zip',
            'MetaPack-tvshow-V-123.zip']
    for pack in all_packs:
        if pack not in skip:
            install_metapack(pack)


class StopDownloading(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


def download_metapack(url, dest, displayname=False):
    print 'Downloading Metapack'
    print 'URL: %s' % url
    print 'Destination: %s' % dest
    if not displayname:
        displayname = url
    dlg = xbmcgui.DialogProgress()
    dlg.create('Downloading', '', displayname)
    start_time = time.time()
    if os.path.isfile(dest):
        print 'File to be downloaded already esists'
        return True
    try:
        urllib.urlretrieve(url, dest, lambda nb, bs, fs: _pbhook(nb, bs, fs, dlg, start_time))
    except:
        #only handle StopDownloading (from cancel),
        #ContentTooShort (from urlretrieve), and OS (from the race condition);
        #let other exceptions bubble 
        if sys.exc_info()[0] in (urllib.ContentTooShortError, StopDownloading, OSError):
            return False
        else:
            raise
    return True


def is_metapack_installed(pack):
    pass

def _pbhook(numblocks, blocksize, filesize, dlg, start_time):
    try:
        percent = min(numblocks * blocksize * 100 / filesize, 100)
        currently_downloaded = float(numblocks) * blocksize / (1024 * 1024)
        kbps_speed = numblocks * blocksize / (time.time() - start_time)
        if kbps_speed > 0:
            eta = (filesize - numblocks * blocksize) / kbps_speed
        else:
            eta = 0
        kbps_speed /= 1024
        total = float(filesize) / (1024 * 1024)
        mbs = '%.02f MB of %.02f MB' % (currently_downloaded, total)
        est = 'Speed: %.02f Kb/s ' % kbps_speed
        est += 'ETA: %02d:%02d' % divmod(eta, 60)
        dlg.update(percent, mbs, est)

    except:
        percent = 100
        dlg.update(percent)
    if dlg.iscanceled():
        dlg.close()
        raise StopDownloading('Stopped Downloading')
