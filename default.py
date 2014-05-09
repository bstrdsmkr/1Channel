"""
    1Channel XBMC Addon
    Copyright (C) 2012 Bstrdsmkr

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
# pylint: disable=C0301
# pylint: disable=F0401
# pylint: disable=W0621
import re,os,sys,time,datetime,string,urllib,urllib2,HTMLParser
from operator import itemgetter
import xbmc,xbmcgui,xbmcaddon,xbmcplugin
import xbmcvfs
from t0mm0.common.addon import Addon
from t0mm0.common.net import Net
try: from metahandler import metahandlers
except: xbmc.executebuiltin("XBMC.Notification(%s,%s,2000)" % ('Import Failed','metahandler')); pass
try: from metahandler import metacontainers
except: xbmc.executebuiltin("XBMC.Notification(%s,%s,2000)" % ('Import Failed','metahandler')); pass
import metapacks
from utils import *

_1CH = Addon('plugin.video.1channel', sys.argv)

def addstv(id,value=''): _1CH.addon.setSetting(id=id,value=value) ## Save Settings
def addst(r,s=''): return _1CH.get_setting(r)   ## Get Settings
def addpr(r,s=''): return _1CH.queries.get(r,s) ## Get Params
def tfalse(r,d=False): ## Get True / False
	if   (r.lower()=='true' ): return True
	elif (r.lower()=='false'): return False
	else: return d

def Logg(o):
	try: _1CH.log(o)
	except: pass
try:
    DB_NAME = _1CH.get_setting('db_name')
    DB_USER = _1CH.get_setting('db_user')
    DB_PASS = _1CH.get_setting('db_pass')
    DB_ADDR = _1CH.get_setting('db_address')

    if _1CH.get_setting('use_remote_db') == 'true' and \
                    DB_ADDR is not None and \
                    DB_USER is not None and \
                    DB_PASS is not None and \
                    DB_NAME is not None:
        import mysql.connector as orm

        try: _1CH.log('Loading MySQL as DB engine')
        except: pass
        DB = 'mysql'
    else:
        try: _1CH.log('MySQL not enabled or not setup correctly')
        except: pass
        raise ValueError('MySQL not enabled or not setup correctly')
except:
    try:
        from sqlite3 import dbapi2 as orm

        try: _1CH.log('Loading sqlite3 as DB engine')
        except: pass
    except:
        from pysqlite2 import dbapi2 as orm

        try: _1CH.log('pysqlite2 as DB engine')
        except: pass
    DB = 'sqlite'
    __translated__ = xbmc.translatePath("special://database")
    DB_DIR = os.path.join(__translated__, 'onechannelcache.db')

META_ON = _1CH.get_setting('use-meta') == 'true'
FANART_ON = _1CH.get_setting('enable-fanart') == 'true'
USE_POSTERS = _1CH.get_setting('use-posters') == 'true'
POSTERS_FALLBACK = _1CH.get_setting('posters-fallback') == 'true'
THEME_LIST = ['Classic', 'Glossy_Black', 'PrimeWire']
THEME = THEME_LIST[int(_1CH.get_setting('theme'))]
THEME_PATH = os.path.join(_1CH.get_path(), 'art', 'themes', THEME)
AUTO_WATCH = _1CH.get_setting('auto-watch') == 'true'

AZ_DIRECTORIES = (ltr for ltr in string.ascii_uppercase)
BASE_URL = _1CH.get_setting('domain')
if (tfalse(addst("enableDomain"))==True) and (len(addst("customDomain")) > 10):
	BASE_URL=addst("customDomain")

USER_AGENT = ("User-Agent:Mozilla/5.0 (Windows NT 6.2; WOW64)"
              "AppleWebKit/537.17 (KHTML, like Gecko)"
              "Chrome/24.0.1312.56")
GENRES = ['Action', 'Adventure', 'Animation', 'Biography', 'Comedy',
          'Crime', 'Documentary', 'Drama', 'Family', 'Fantasy', 'Game-Show',
          'History', 'Horror', 'Japanese', 'Korean', 'Music', 'Musical',
          'Mystery', 'Reality-TV', 'Romance', 'Sci-Fi', 'Short', 'Sport',
          'Talk-Show', 'Thriller', 'War', 'Western', 'Zombies']

PREPARE_ZIP = False
__metaget__ = metahandlers.MetaData(preparezip=PREPARE_ZIP)

if not xbmcvfs.exists(_1CH.get_profile()): 
	try: xbmcvfs.mkdirs(_1CH.get_profile())
	except: os.path.mkdir(_1CH.get_profile())

def art(name): art_img = os.path.join(THEME_PATH, name); return art_img

def init_database():
    try: _1CH.log('Building PrimeWire Database')
    except: pass
    if DB == 'mysql':
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        cur = db.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS seasons (season INTEGER UNIQUE, contents TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS favorites (type VARCHAR(10), name TEXT, url VARCHAR(255) UNIQUE, year VARCHAR(10))')
        cur.execute('CREATE TABLE IF NOT EXISTS subscriptions (url VARCHAR(255) UNIQUE, title TEXT, img TEXT, year TEXT, imdbnum TEXT, day TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS bookmarks (video_type VARCHAR(10), title VARCHAR(255), season INTEGER, episode INTEGER, year VARCHAR(10), bookmark VARCHAR(10))')
        cur.execute('CREATE TABLE IF NOT EXISTS url_cache (url VARCHAR(255), response TEXT, timestamp TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS db_info (setting TEXT, value TEXT)')
        
        try: 
            cur.execute('CREATE UNIQUE INDEX unique_bmk ON bookmarks (video_type, title, season, episode, year)')
        except:
            #todo: delete all non-unique bookmarks and try again
            pass

        cur.execute('SELECT value FROM db_info WHERE setting = "version"')
        db_ver = cur.fetchall() or [0]
        #todo: write version number comparison logic to handle letters and etc
        if _1CH.get_version() > db_ver[0]:
	        ### Try to add the 'day' column to upgrade older DBs. If an error pops, it's either successful
	        #or there's nothing else we can do about it. Either way: ignore it and try to keep going
	        try: 
	            cur.execute('ALTER TABLE subscriptions ADD day TEXT')
	        #cur.execute('(SELECT IF((SELECT COUNT(day) FROM subscriptions) > 0,"SELECT 1","ALTER TABLE table_name ADD col_name VARCHAR(100)"))')
	        except: #todo: catch the specific exception
	            pass

    else:
        if not xbmcvfs.exists(os.path.dirname(DB_DIR)): 
        	try: xbmcvfs.mkdirs(os.path.dirname(DB_DIR))
        	except: os.path.mkdir(os.path.dirname(DB_DIR))
        db = orm.connect(DB_DIR)
        db.execute('CREATE TABLE IF NOT EXISTS seasons (season UNIQUE, contents)')
        db.execute('CREATE TABLE IF NOT EXISTS favorites (type, name, url, year)')
        db.execute('CREATE TABLE IF NOT EXISTS subscriptions (url, title, img, year, imdbnum, day)')
        db.execute('CREATE TABLE IF NOT EXISTS bookmarks (video_type, title, season, episode, year, bookmark)')
        db.execute('CREATE TABLE IF NOT EXISTS url_cache (url UNIQUE, response, timestamp)')
        db.execute('CREATE TABLE IF NOT EXISTS db_info (setting TEXT, value TEXT)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_fav ON favorites (name, url)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_sub ON subscriptions (url, title, year)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_bmk ON bookmarks (video_type, title, season, episode, year)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_url ON url_cache (url)')
        
        db_ver = db.execute('SELECT value FROM db_info WHERE setting = "version"').fetchall() or [0]
        #todo: write version number comparison logic to handle letters and etc
        if _1CH.get_version() > db_ver[0]:
	        ### Try to add the 'day' column to upgrade older DBs. If an error pops, it's either successful
	        #or there's nothing else we can do about it. Either way: ignore it and try to keep going
	        try: 
	            cur.execute('ALTER TABLE subscriptions ADD day')
	        #cur.execute('(SELECT IF((SELECT COUNT(day) FROM subscriptions) > 0,"SELECT 1","ALTER TABLE table_name ADD col_name VARCHAR(100)"))')
	        except: #todo: catch the specific exception
	            pass

    sql = "REPLACE INTO db_info (setting, value) VALUES(%s,%s)"
    if DB == 'sqlite':
        sql = 'INSERT OR ' + sql.replace('%s', '?')
        db.execute(sql, ('version', _1CH.get_version()))
    else:
        cur.execute(sql, ('version', _1CH.get_version()))
    db.close()


def save_favorite(fav_type, name, url, img, year):
    log_msg = 'Saving Favorite type: %s name: %s url: %s img: %s year: %s'
    try: _1CH.log(log_msg % (fav_type, name, url, img, year))
    except: pass
    if fav_type != 'tv':
        fav_type = 'movie'
    if website_is_integrated():
        try: _1CH.log('Saving favorite to website')
        except: pass
        id_num = re.search(r'.+(?:watch|tv)-([\d]+)-', url)
        if id_num:
            save_url = "%s/addtofavs.php?id=%s&whattodo=add"
            save_url = save_url % (BASE_URL, id_num.group(1))
            print save_url
            net = Net()
            cookiejar = _1CH.get_profile()
            cookiejar = os.path.join(cookiejar, 'cookies')
            net.set_cookies(cookiejar)
            html = net.http_GET(save_url).content
            net.save_cookies(cookiejar)
            ok_message = '<div class="ok_message">Movie added to favorites'
            error_message = '<div class="error_message">This video is already'
            if ok_message in html:
                builtin = 'XBMC.Notification(Save Favorite,Added to Favorites,2000)'
                xbmc.executebuiltin(builtin)
            elif error_message in html:
                builtin = 'XBMC.Notification(Save Favorite,Item already in Favorites,2000)'
                xbmc.executebuiltin(builtin)
            else:
                try: _1CH.log('Unable to confirm success')
                except: pass
                try: _1CH.log(html)
                except: pass
    else:
        statement = 'INSERT INTO favorites (type, name, url, year) VALUES (%s,%s,%s,%s)'
        if DB == 'mysql':
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        else:
            db = orm.connect(DB_DIR)
            statement = statement.replace("%s", "?")
        cursor = db.cursor()
        try:
            title = urllib.unquote_plus(unicode(name, 'latin1'))
            cursor.execute(statement, (fav_type, title, url, year))
            builtin = 'XBMC.Notification(Save Favorite,Added to Favorites,2000)'
            xbmc.executebuiltin(builtin)
        except orm.IntegrityError:
            builtin = 'XBMC.Notification(Save Favorite,Item already in Favorites,2000)'
            xbmc.executebuiltin(builtin)
        db.commit()
        db.close()


def delete_favorite(fav_type, name, url):
    if fav_type != 'tv':
        fav_type = 'movie'
    try: _1CH.log('Deleting Fav: %s\n %s\n %s\n' % (fav_type, name, url))
    except: pass
    if website_is_integrated():
        try: _1CH.log('Deleting favorite from website')
        except: pass
        id_num = re.search(r'.+(?:watch|tv)-([\d]+)-', url)
        if id_num:
            del_url = "%s/addtofavs.php?id=%s&whattodo=delete"
            del_url = del_url % (BASE_URL, id_num.group(1))
            print del_url
            net = Net()
            cookiejar = _1CH.get_profile()
            cookiejar = os.path.join(cookiejar, 'cookies')
            net.set_cookies(cookiejar)
            net.http_GET(del_url)
            net.save_cookies(cookiejar)

    else:
        sql_del = 'DELETE FROM favorites WHERE type=%s AND name=%s AND url=%s'
        if DB == 'mysql':
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        else:
            db = orm.connect(DB_DIR)
            sql_del = sql_del.replace('%s', '?')
        cursor = db.cursor()
        cursor.execute(sql_del, (fav_type, name, url))
        db.commit()
        db.close()


def get_url(url, cache_limit=8):
    try: _1CH.log('Fetching URL: %s' % url)
    except: pass
    if DB == 'mysql':
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
    else:
        db = orm.connect(DB_DIR)
    cur = db.cursor()
    now = time.time()
    limit = 60 * 60 * cache_limit
    cur.execute('SELECT * FROM url_cache WHERE url = "%s"' % url)
    cached = cur.fetchone()
    if cached:
        created = float(cached[2])
        age = now - created
        if age < limit:
            try: _1CH.log('Returning cached result for %s' % url)
            except: pass
            db.close()
            return cached[1].encode('utf-8')
        else:
            try: _1CH.log('Cache too old. Requesting from internet')
            except: pass
    else:
        try: _1CH.log('No cached response. Requesting from internet')
        except: pass

    req = urllib2.Request(url)

    host = re.sub('http://', '', BASE_URL)
    req.add_header('User-Agent', USER_AGENT)
    req.add_header('Host', host)
    req.add_header('Referer', BASE_URL)

    try:
        response = urllib2.urlopen(req, timeout=10)
        body = response.read()
        if '<title>Are You a Robot?</title>' in body:
            _1CH.log('bot detection')

            #download the captcha image and save it to a file for use later
            captchaimgurl = 'http://'+host+'/CaptchaSecurityImages.php'
            captcha_save_path = xbmc.translatePath('special://userdata/addon_data/plugin.video.1channel/CaptchaSecurityImage.jpg')
            req = urllib2.Request(captchaimgurl)
            host = re.sub('http://', '', BASE_URL)
            req.add_header('User-Agent', USER_AGENT)
            req.add_header('Host', host)
            req.add_header('Referer', BASE_URL)
            response = urllib2.urlopen(req)
            the_img = response.read()
            with open(captcha_save_path,'wb') as f:
                f.write(the_img)

            #now pop open dialog for input
            #TODO: make the size and loc configurable
            img = xbmcgui.ControlImage(550,15,240,100,captcha_save_path)
            wdlg = xbmcgui.WindowDialog()
            wdlg.addControl(img)
            wdlg.show()
            kb = xbmc.Keyboard('', 'Type the letters in the image', False)
            kb.doModal()
            capcode = kb.getText()
            if (kb.isConfirmed()):
                userInput = kb.getText()
            if userInput != '':
                #post back user string
                wdlg.removeControl(img)    
                capcode = kb.getText()
                data = {'security_code':capcode,
                        'not_robot':'I\'m Human! I Swear!'}
                data = urllib.urlencode(data)
                roboturl = 'http://'+host+'/are_you_a_robot.php'
                req = urllib2.Request(roboturl)
                host = re.sub('http://', '', BASE_URL)
                req.add_header('User-Agent', USER_AGENT)
                req.add_header('Host', host)
                req.add_header('Referer', BASE_URL)
                response = urllib2.urlopen(req, data)
                body = get_url(url)
               
            elif userInput == '':
                dialog = xbmcgui.Dialog()
                dialog.ok("Robot Check", "You must enter text in the image to continue")
            wdlg.close()

        body = unicode(body, 'iso-8859-1')
        parser = HTMLParser.HTMLParser()
        body = parser.unescape(body)
    except:
        dialog = xbmcgui.Dialog()
        dialog.ok("Connection failed", "Failed to connect to url", url)
        print "PrimeWire: Failed to connect to URL %s" % url
        return ''

    response.close()
    
    sql = "REPLACE INTO url_cache (url,response,timestamp) VALUES(%s,%s,%s)"
    if DB == 'sqlite':
        sql = 'INSERT OR ' + sql.replace('%s', '?')
    cur.execute(sql, (url, body, now))
    db.commit()
    db.close()    
    return body


def get_sources(url, title, img, year, imdbnum, dialog):
    url = urllib.unquote(url)
    try: _1CH.log('Getting sources from: %s' % url)
    except: pass

    pattern = r'tv-\d{1,10}-(.*)/season-(\d{1,4})-episode-(\d{1,4})'
    match = re.search(pattern, url, re.IGNORECASE | re.DOTALL)
    if match:
        video_type = 'episode'
        season = int(match.group(2))
        episode = int(match.group(3))
    else:
        video_type = 'movie'
        season = ''
        episode = ''

    net = Net()
    cookiejar = _1CH.get_profile()
    cookiejar = os.path.join(cookiejar, 'cookies')
    net.set_cookies(cookiejar)
    #html = net.http_GET(BASE_URL + url).content
    html = get_url(BASE_URL + url, cache_limit=2)
    net.save_cookies(cookiejar)
    adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
    adult = re.search(adultregex, html, re.DOTALL)
    if adult:
        try: _1CH.log('Adult content url detected')
        except: pass
        adulturl = BASE_URL + adult.group(1)
        headers = {'Referer': url}
        net.set_cookies(cookiejar)
        html = net.http_GET(adulturl, headers=headers).content
        net.save_cookies(cookiejar)

    sources = []
    hosters = []
    if META_ON and video_type == 'movie' and not imdbnum:
        imdbregex = 'mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7})"'
        match = re.search(imdbregex, html)
        if match:
            imdbnum = match.group(1)
            __metaget__.update_meta('movie', title, imdb_id='',
                                    new_imdb_id=imdbnum, year=year)

    if _1CH.get_setting('sorting-enabled') == 'true':
        sorts = [None, 'host', 'verified', 'quality', 'views', 'multi-part']
        if int(_1CH.get_setting('first-sort')) > 0:
            this_sort = sorts[int(_1CH.get_setting('first-sort'))]
            if _1CH.get_setting('first-sort-reversed') == 'true':
                this_sort = '-%s' % this_sort
            sorting = [this_sort]
            if int(_1CH.get_setting('second-sort')) > 0:
                this_sort = sorts[int(_1CH.get_setting('second-sort'))]
                if _1CH.get_setting('second-sort-reversed') == 'true':
                    this_sort = '-%s' % this_sort
                sorting.append(this_sort)
                if int(_1CH.get_setting('third-sort')) > 0:
                    this_sort = sorts[int(_1CH.get_setting('third-sort'))]
                    if _1CH.get_setting('third-sort-reversed') == 'true':
                        this_sort = '-%s' % this_sort
                    sorting.append(this_sort)
                    if int(_1CH.get_setting('fourth-sort')) > 0:
                        this_sort = sorts[int(_1CH.get_setting('fourth-sort'))]
                        if _1CH.get_setting('fourth-sort-reversed') == 'true':
                            this_sort = '-%s' % this_sort
                        sorting.append(this_sort)
                        if int(_1CH.get_setting('fifth-sort')) > 0:
                            this_sort = sorts[int(_1CH.get_setting('fifth-sort'))]
                            if _1CH.get_setting('fifth-sort-reversed') == 'true':
                                this_sort = '-%s' % this_sort
                            sorting.append(this_sort)
        else: sorting = []
    else:
        sorting = []

    container_pattern = r'<table[^>]+class="movie_version[ "][^>]*>(.*?)</table>'
    item_pattern = (
        r'quality_(?!sponsored|unknown)([^>]*)></span>.*?'
        r'url=([^&]+)&(?:amp;)?domain=([^&]+)&(?:amp;)?(.*?)'
        r'"version_veiws"> ([\d]+) views</')
    for version in re.finditer(container_pattern, html, re.DOTALL | re.IGNORECASE):
        for source in re.finditer(item_pattern, version.group(1), re.DOTALL):
            qual, url, host, parts, views = source.groups()

            item = {'host': host.decode('base-64'), 'url': url.decode('base-64')}
            if item==item: #urlresolver.HostedMediaFile(item['url']).valid_url():
                item['verified'] = source.group(0).find('star.gif') > -1
                item['quality'] = qual.upper()
                item['views'] = int(views)
                pattern = r'<a href=".*?url=(.*?)&(?:amp;)?.*?".*?>(part \d*)</a>'
                other_parts = re.findall(pattern, parts, re.DOTALL | re.I)
                if other_parts:
                    item['multi-part'] = True
                    item['parts'] = [part[0].decode('base-64') for part in other_parts]
                else:
                    item['multi-part'] = False
                hosters.append(item)

            if sorting:
                hosters = multikeysort(hosters, sorting, functions={'host': rank_host})
    if not hosters:
        _1CH.show_ok_dialog(['No sources were found for this item'], title='PrimeWire')
    if dialog and _1CH.get_setting(
            'auto-play') == 'false':  # we're comming from a .strm file and can't create a directory so we have to pop a
        sources = []                  # dialog if auto-play isn't on
        img = xbmc.getInfoImage('ListItem.Thumb')
        for item in hosters:
            try:
                label = format_label_source(item)
                hosted_media = urlresolver.HostedMediaFile(url=item['url'], title=label)
                sources.append(hosted_media)
                if item['multi-part']:
                    partnum = 2
                    for part in item['parts']:
                        label = format_label_source_parts(item, partnum)
                        hosted_media = urlresolver.HostedMediaFile(url=item['parts'][partnum - 2], title=label)
                        sources.append(hosted_media)
                        partnum += 1
            except:
                try: _1CH.log('Error while trying to resolve %s' % url)
                except: pass
        source = urlresolver.choose_source(sources).get_url()
        PlaySource(source, title, img, year, imdbnum, video_type, season, episode, strm=True)
    else:
        try:
            if _1CH.get_setting('auto-play') == 'false': raise # skips the next line and goes into the else clause
            dlg = xbmcgui.DialogProgress()
            line1 = 'Trying Sources...'
            dlg.create('PrimeWire', line1)
            total = len(hosters)
            count = 1
            success = False
            while not (success or dlg.iscanceled() or xbmc.abortRequested):
                for source in hosters:
                    if dlg.iscanceled(): return
                    percent = int((count * 100) / total)
                    label = format_label_source(source)
                    dlg.update(percent, line1, label)
                    try:
                        PlaySource(source['url'], title, img, year, imdbnum, video_type, season, episode)
                        dlg.close()
                        success = True
                        break  # Playback was successful, break out of the loop
                    except Exception, e:  # Playback failed, try the next one
                        dlg.update(percent, line1, label, str(e))
                        try: _1CH.log('%s source failed. Trying next source...' % source['host'])
                        except: pass
                        try: _1CH.log(str(e))
                        except: pass
                        count += 1
        except:
            for item in hosters:
                try: _1CH.log(item)
                except: pass
                label = format_label_source(item)
                _1CH.add_directory({'mode': 'PlaySource', 'url': item['url'], 'title': title,
                                    'img': img, 'year': year, 'imdbnum': imdbnum,
                                    'video_type': video_type, 'season': season, 'episode': episode},
                                   infolabels={'title': label}, is_folder=False, img=img, fanart=art('fanart.png'))
                if item['multi-part']:
                    partnum = 2
                    for part in item['parts']:
                        label = format_label_source_parts(item, partnum)
                        partnum += 1
                        _1CH.add_directory({'mode': 'PlaySource', 'url': part, 'title': title,
                                            'img': img, 'year': year, 'imdbnum': imdbnum,
                                            'video_type': video_type, 'season': season, 'episode': episode},
                                           infolabels={'title': label}, is_folder=False, img=img,
                                           fanart=art('fanart.png'))

            _1CH.end_of_directory()


def PlaySource(url, title, img, year, imdbnum, video_type, season, episode, strm=False):
    try: _1CH.log('Attempting to play url: %s' % url)
    except: pass
    stream_url = urlresolver.HostedMediaFile(url=url).resolve()
    
    #If urlresolver returns false then the video url was not resolved.
    if not type(stream_url) is str and not type(stream_url) is unicode:
        try: _1CH.log('Could not resove url: %s' % url) 
        except: pass
        return
        
    win = xbmcgui.Window(10000)
    win.setProperty('1ch.playing.title', title)
    win.setProperty('1ch.playing.year', year)
    win.setProperty('1ch.playing.imdb', imdbnum)
    win.setProperty('1ch.playing.season', str(season))
    win.setProperty('1ch.playing.episode', str(episode))

    listitem = xbmcgui.ListItem(title, iconImage=img, thumbnailImage=img)
    if META_ON:
        if video_type == 'episode':
            try:
                meta = __metaget__.get_episode_meta(title, imdbnum, season, episode)
                meta['TVShowTitle'] = title
                meta['title'] = format_tvshow_episode(meta)
                if not strm:
                    try:
                        img = meta['cover_url']
                    except:
                        img = ''
                listitem = xbmcgui.ListItem(title, iconImage=img, thumbnailImage=img)
                listitem.setInfo(type="Video", infoLabels=meta)
                listitem.setProperty('IsPlayable', 'true')
            except:
                try: _1CH.log('Failed to get metadata for Title: %s IMDB: %s Season: %s Episode %s' % (title, imdbnum, season, episode))
                except: pass
        elif video_type == 'movie':
            try:
                meta = __metaget__.get_meta('movie', title, year=year)
                meta['title'] = format_label_movie(meta)
                if not strm:
                    try:
                        img = meta['cover_url']
                    except:
                        img = ''
                listitem.setInfo(type="Video", infoLabels=meta)
                listitem.setProperty('IsPlayable', 'true')
            except:
                try: _1CH.log('Failed to get metadata for Title: %s IMDB: %s Season: %s Episode %s' % (title, imdbnum, season, episode))
                except: pass

    listitem.setPath(stream_url)
    xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, listitem)


def TrackProgress(player):
    while player._playbackLock:
        if player.isPlayingVideo():
            player._trackPosition()
            xbmc.sleep(250)


def ChangeWatched(imdb_id, video_type, name, season, episode, year='', watched='', refresh=False):
    __metaget__.change_watched(video_type, name, imdb_id, season=season, episode=episode, year=year, watched=watched)
    if refresh:
        xbmc.executebuiltin("XBMC.Container.Refresh")


def PlayTrailer(url):
    url = url.decode('base-64')
    try: _1CH.log('Attempting to resolve and play trailer at %s' % url)
    except: pass
    sources = []
    hosted_media = urlresolver.HostedMediaFile(url=url)
    sources.append(hosted_media)
    source = urlresolver.choose_source(sources)
    if source:
        stream_url = source.resolve()
    else:
        stream_url = ''
    xbmc.Player().play(stream_url)


def GetSearchQuery(section):
    last_search = _1CH.load_data('search')
    if not last_search: last_search = ''
    keyboard = xbmc.Keyboard()
    if section == 'tv':
        keyboard.setHeading('Search TV Shows')
    else:
        keyboard.setHeading('Search Movies')
    keyboard.setDefault(last_search)
    keyboard.doModal()
    if keyboard.isConfirmed():
        search_text = keyboard.getText()
        _1CH.save_data('search', search_text)
        if search_text.startswith('!#'):
            if search_text == '!#create metapacks': create_meta_packs()
            if search_text == '!#repair meta': repair_missing_images()
            if search_text == '!#install all meta': install_all_meta()
            if search_text.startswith('!#sql'):
                if DB == 'mysql':
                    db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
                else:
                    db = orm.connect(DB_DIR)
                db.execute(search_text[5:])
                db.commit()
                db.close()
        else:
            Search(section, keyboard.getText())
    else:
        BrowseListMenu(section)


def GetSearchQueryTag(section):
    last_search = _1CH.load_data('search')
    if not last_search: last_search = ''
    #
    keyboard2 = xbmc.Keyboard()
    keyboard2.setHeading('Search Tag')
    keyboard2.setDefault('')
    keyboard2.doModal()
    if keyboard2.isConfirmed():
        tag_text = keyboard2.getText()
    #
    keyboard = xbmc.Keyboard()
    if section == 'tv':
        keyboard.setHeading('Search TV Shows')
    else:
        keyboard.setHeading('Search Movies')
    keyboard.setDefault(last_search)
    keyboard.doModal()
    if keyboard.isConfirmed():
        search_text = keyboard.getText()
        _1CH.save_data('search', search_text)
        if search_text.startswith('!#'):
            if search_text == '!#create metapacks': create_meta_packs()
            if search_text == '!#repair meta': repair_missing_images()
            if search_text == '!#install all meta': install_all_meta()
            if search_text.startswith('!#sql'):
                if DB == 'mysql':
                    db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
                else:
                    db = orm.connect(DB_DIR)
                db.execute(search_text[5:])
                db.commit()
                db.close()
        else:
            SearchAdvanced(section, keyboard.getText(), tag_text)
            #SearchTag(section, query='', tag='', description=False, country='', genre='', actor='', director='', year='0', month='0', decade='0', host='', rating='', advanced='1')
    else:
        BrowseListMenu(section)


def GetSearchQueryAdvanced(section):
    last_search = _1CH.load_data('search')
    if not last_search: last_search = ''
    #
    keyboard2 = xbmc.Keyboard()
    keyboard2.setHeading('Search Tag')
    keyboard2.setDefault('')
    keyboard2.doModal()
    if keyboard2.isConfirmed(): tag_text = keyboard2.getText()
    else: tag_text = ''
    #
    keyboard2.setHeading('Search Actor')
    keyboard2.setDefault('')
    keyboard2.doModal()
    if keyboard2.isConfirmed(): actor_text = keyboard2.getText()
    else: actor_text = ''
    #
    keyboard2.setHeading('Search Directed By')
    keyboard2.setDefault('')
    keyboard2.doModal()
    if keyboard2.isConfirmed(): director_text = keyboard2.getText()
    else: director_text = ''
    #
    keyboard2 = xbmc.Keyboard()
    keyboard2.setHeading('Search Year (Numbers Only)')
    keyboard2.setDefault('0')
    keyboard2.doModal()
    if keyboard2.isConfirmed(): year_text = keyboard2.getText()
    else: year_text = ''
    #
    keyboard2 = xbmc.Keyboard()
    keyboard2.setHeading('Search Month (Numbers Only)')
    keyboard2.setDefault('0')
    keyboard2.doModal()
    if keyboard2.isConfirmed(): month_text = keyboard2.getText()
    else: month_text = ''
    #
    keyboard2 = xbmc.Keyboard()
    keyboard2.setHeading('Search Decade (Example: type 1980 for 1980s)')
    keyboard2.setDefault('0')
    keyboard2.doModal()
    if keyboard2.isConfirmed(): decade_text = keyboard2.getText()
    else: decade_text = ''
    #
    keyboard2.setHeading('Search Country (Capital First Letter)')
    keyboard2.setDefault('')
    keyboard2.doModal()
    if keyboard2.isConfirmed(): country_text = keyboard2.getText()
    else: country_text = ''
    keyboard2.setHeading('Search Genre (Capital First Letter)')
    keyboard2.setDefault('')
    keyboard2.doModal()
    if keyboard2.isConfirmed(): genre_text = keyboard2.getText()
    else: genre_text = ''
    #
    #
    #
    #
    keyboard = xbmc.Keyboard()
    if section == 'tv':
        keyboard.setHeading('Search TV Shows')
    else:
        keyboard.setHeading('Search Movies')
    keyboard.setDefault('')#keyboard.setDefault(last_search)
    keyboard.doModal()
    if keyboard.isConfirmed():
        search_text = keyboard.getText()
        _1CH.save_data('search', search_text)
        if search_text.startswith('!#'):
            if search_text == '!#create metapacks': create_meta_packs()
            if search_text == '!#repair meta': repair_missing_images()
            if search_text == '!#install all meta': install_all_meta()
            if search_text.startswith('!#sql'):
                if DB == 'mysql':
                    db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
                else:
                    db = orm.connect(DB_DIR)
                db.execute(search_text[5:])
                db.commit()
                db.close()
        else:
            SearchAdvanced(section, keyboard.getText(), tag_text, True, country_text, genre_text, actor_text, director_text, year_text, month_text, decade_text)
            #SearchTag(section, query='', tag='', description=False, country='', genre='', actor='', director='', year='0', month='0', decade='0', host='', rating='', advanced='1')
    else:
        BrowseListMenu(section)


def GetSearchQueryDesc(section):
    last_search = _1CH.load_data('search')
    if not last_search: last_search = ''
    keyboard = xbmc.Keyboard()
    if section == 'tv':
        keyboard.setHeading('Search TV Shows')
    else:
        keyboard.setHeading('Search Movies')
    keyboard.setDefault(last_search)
    keyboard.doModal()
    if keyboard.isConfirmed():
        search_text = keyboard.getText()
        _1CH.save_data('search', search_text)
        if search_text.startswith('!#'):
            if search_text == '!#create metapacks': create_meta_packs()
            if search_text == '!#repair meta': repair_missing_images()
            if search_text == '!#install all meta': install_all_meta()
            if search_text.startswith('!#sql'):
                if DB == 'mysql':
                    db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
                else:
                    db = orm.connect(DB_DIR)
                db.execute(search_text[5:])
                db.commit()
                db.close()
        else:
            SearchDesc(section, keyboard.getText())
    else:
        BrowseListMenu(section)


def Search(section, query):
    html = get_url(BASE_URL, cache_limit=0)
    r = re.search('input type="hidden" name="key" value="([0-9a-f]*)"', html).group(1)
    search_url = BASE_URL + '/index.php?search_keywords='
    search_url += urllib.quote_plus(query)
    search_url += '&key=' + r
    if section == 'tv':
        set_view('tvshows', 'tvshows-view')
        search_url += '&search_section=2'
        nextmode = 'TVShowSeasonList'
        video_type = 'tvshow'
        folder = True
        if DB == 'mysql':
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        else:
            db = orm.connect(DB_DIR)
        cur = db.cursor()
        cur.execute('SELECT url FROM subscriptions')
        subscriptions = cur.fetchall()
        db.close()
        subs = [row[0] for row in subscriptions]

    else:
        set_view('movies', 'movies-view')
        nextmode = 'GetSources'
        video_type = 'movie'
        folder = _1CH.get_setting('auto-play') == 'false'
        subs = []

    html = '> >> <'
    page = 0

    while html.find('> >> <') > -1 and page < 10:
        page += 1
        if page > 1:
            pageurl = '%s&page=%s' % (search_url, page)
        else:
            pageurl = search_url
        html = get_url(pageurl, cache_limit=0)

        r = re.search('number_movies_result">([0-9,]+)', html)
        if r:
            total = int(r.group(1).replace(',', ''))
        else:
            total = 0

        pattern = r'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
        regex = re.finditer(pattern, html, re.DOTALL)
        resurls = []
        for s in regex:
            resurl, title, year, thumb = s.groups()
            if resurl not in resurls:
                resurls.append(resurl)

                li = build_listitem(video_type, title, year, img, resurl, subs=subs)
                imdb = li.getProperty('imdb')
                thumb = li.getProperty('img')

                queries = {'mode': nextmode, 'title': title, 'url': resurl,
                           'img': thumb, 'imdbnum': imdb,
                           'video_type': video_type, 'year': year}
                li_url = _1CH.build_plugin_url(queries)
                xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, li,
                                            isFolder=folder, totalItems=total)
    _1CH.end_of_directory()


def SearchAdvanced(section, query='', tag='', description=False, country='', genre='', actor='', director='', year='0', month='0', decade='0', host='', rating='', advanced='1'):
    html = get_url(BASE_URL, cache_limit=0)
    r = re.search('input type="hidden" name="key" value="([0-9a-f]*)"', html).group(1)
    search_url = BASE_URL + '/index.php?search_keywords='
    search_url += urllib.quote_plus(query)
    if (description==True): search_url += '&desc_search=1'
    search_url += '&tag=' + urllib.quote_plus(tag)
    search_url += '&genre=' + urllib.quote_plus(genre)
    search_url += '&actor_name=' + urllib.quote_plus(actor)
    search_url += '&director=' + urllib.quote_plus(director)
    search_url += '&country=' + urllib.quote_plus(country)
    search_url += '&year=' + urllib.quote_plus(year)
    search_url += '&month=' + urllib.quote_plus(month)
    search_url += '&decade=' + urllib.quote_plus(decade)
    search_url += '&host=' + urllib.quote_plus(host)
    search_url += '&search_rating=' + urllib.quote_plus(rating) ## Rating higher than (#), 0-4
    search_url += '&advanced=' + urllib.quote_plus(advanced)
    ###search_url += 'search_section=1&genre=&director=&actor_name=&country=&search_rating=0&year=0&month=0&decade=0&host=&advanced=1'
    search_url += '&key=' + r
    if section == 'tv':
        set_view('tvshows', 'tvshows-view')
        search_url += '&search_section=2'
        nextmode = 'TVShowSeasonList'
        video_type = 'tvshow'
        folder = True
        if DB == 'mysql':
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        else:
            db = orm.connect(DB_DIR)
        cur = db.cursor()
        cur.execute('SELECT url FROM subscriptions')
        subscriptions = cur.fetchall()
        db.close()
        subs = [row[0] for row in subscriptions]
    else:
        set_view('movies', 'movies-view')
        nextmode = 'GetSources'
        video_type = 'movie'
        folder = _1CH.get_setting('auto-play') == 'false'
        subs = []
    html = '> >> <'
    page = 0
    while html.find('> >> <') > -1 and page < 10:
        page += 1
        if page > 1:
            pageurl = '%s&page=%s' % (search_url, page)
        else:
            pageurl = search_url
        html = get_url(pageurl, cache_limit=0)
        r = re.search('number_movies_result">([0-9,]+)', html)
        if r:
            total = int(r.group(1).replace(',', ''))
        else:
            total = 0
        pattern = r'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
        regex = re.finditer(pattern, html, re.DOTALL)
        resurls = []
        for s in regex:
            resurl, title, year, thumb = s.groups()
            if resurl not in resurls:
                resurls.append(resurl)
                li = build_listitem(video_type, title, year, img, resurl, subs=subs)
                imdb = li.getProperty('imdb')
                thumb = li.getProperty('img')
                queries = {'mode': nextmode, 'title': title, 'url': resurl,
                           'img': thumb, 'imdbnum': imdb,
                           'video_type': video_type, 'year': year}
                li_url = _1CH.build_plugin_url(queries)
                xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, li,
                                            isFolder=folder, totalItems=total)
    _1CH.end_of_directory()


def SearchDesc(section, query):
    html = get_url(BASE_URL, cache_limit=0)
    r = re.search('input type="hidden" name="key" value="([0-9a-f]*)"', html).group(1)
    search_url = BASE_URL + '/index.php?search_keywords='
    search_url += urllib.quote_plus(query)
    search_url += '&desc_search=1' ## 1 = Search Descriptions
    search_url += '&key=' + r
    if section == 'tv':
        set_view('tvshows', 'tvshows-view')
        search_url += '&search_section=2'
        nextmode = 'TVShowSeasonList'
        video_type = 'tvshow'
        folder = True
        if DB == 'mysql':
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        else:
            db = orm.connect(DB_DIR)
        cur = db.cursor()
        cur.execute('SELECT url FROM subscriptions')
        subscriptions = cur.fetchall()
        db.close()
        subs = [row[0] for row in subscriptions]
    else:
        set_view('movies', 'movies-view')
        nextmode = 'GetSources'
        video_type = 'movie'
        folder = _1CH.get_setting('auto-play') == 'false'
        subs = []
    html = '> >> <'
    page = 0
    while html.find('> >> <') > -1 and page < 10:
        page += 1
        if page > 1:
            pageurl = '%s&page=%s' % (search_url, page)
        else:
            pageurl = search_url
        html = get_url(pageurl, cache_limit=0)
        r = re.search('number_movies_result">([0-9,]+)', html)
        if r:
            total = int(r.group(1).replace(',', ''))
        else:
            total = 0
        pattern = r'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
        regex = re.finditer(pattern, html, re.DOTALL)
        resurls = []
        for s in regex:
            resurl, title, year, thumb = s.groups()
            if resurl not in resurls:
                resurls.append(resurl)
                li = build_listitem(video_type, title, year, img, resurl, subs=subs)
                imdb = li.getProperty('imdb')
                thumb = li.getProperty('img')
                queries = {'mode': nextmode, 'title': title, 'url': resurl,
                           'img': thumb, 'imdbnum': imdb,
                           'video_type': video_type, 'year': year}
                li_url = _1CH.build_plugin_url(queries)
                xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, li,
                                            isFolder=folder, totalItems=total)
    _1CH.end_of_directory()


def AddonMenu():  # homescreen
    try: _1CH.log('Main Menu')
    except: pass
    init_database()
    if has_upgraded():
        try: _1CH.log('Showing update popup')
        except: pass
        try: TextBox()
        except: pass
        adn = xbmcaddon.Addon('plugin.video.1channel')
        upgrade_db()
        fix_existing_strms()
        adn.setSetting('domain', 'http://www.primewire.ag')
        adn.setSetting('old_version', _1CH.get_version())
    _1CH.add_directory({'mode': 'BrowseListMenu', 'section': ''}, {'title': 'Movies'}, img=art('movies.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'BrowseListMenu', 'section': 'tv'}, {'title': 'TV shows'}, img=art('television.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'ResolverSettings'}, {'title': 'Resolver Settings'}, img=art('settings.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'Help'}, {'title': 'Help'}, img=art('help.png'), fanart=art('fanart.png'))
    # _1CH.add_directory({'mode': 'test'},   {'title':  'Test'}, img=art('settings.png'), fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def BrowseListMenu(section=None):
    try: _1CH.log('Browse Options')
    except: pass
    print 'section: %s' % section
    _1CH.add_directory({'mode': 'BrowseAlphabetMenu', 'section': section}, {'title': 'A-Z'}, img=art('atoz.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'GetSearchQuery', 'section': section}, {'title': 'Search'}, img=art('search.png'),
                       fanart=art('fanart.png'))
    if website_is_integrated():
        _1CH.add_directory({'mode': 'browse_favorites_website', 'section': section}, {'title': 'Website Favourites'},
                           img=art('favourites.png'), fanart=art('fanart.png'))
    else:
        _1CH.add_directory({'mode': 'browse_favorites', 'section': section}, {'title': 'Favourites'},
                           img=art('favourites.png'), fanart=art('fanart.png'))
    if section == 'tv':
        _1CH.add_directory({'mode': 'manage_subscriptions'}, {'title': 'Subscriptions'}, img=art('subscriptions.png'),
                           fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'BrowseByGenreMenu', 'section': section}, {'title': 'Genres'}, img=art('genres.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'featured'}, {'title': 'Featured'},
                       img=art('featured.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'views'}, {'title': 'Most Popular'},
                       img=art('most_popular.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'ratings'}, {'title': 'Highly rated'},
                       img=art('highly_rated.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'release'},
                       {'title': 'Date released'}, img=art('date_released.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'date'}, {'title': 'Date added'},
                       img=art('date_added.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'GetSearchQueryDesc', 'section': section}, {'title': 'Search (+Description)'}, img=art('search.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'GetSearchQueryTag', 'section': section}, {'title': 'Search (by Title & Tag)'}, img=art('search.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'GetSearchQueryAdvanced', 'section': section}, {'title': 'Search (Advanced Search)'}, img=art('search.png'),
                       fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def BrowseAlphabetMenu(section=None):
    try: _1CH.log('Browse by alphabet screen')
    except: pass
    _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'alphabet', 'letter': '123'},
                       {'title': '#123'}, img=art('123.png'), fanart=art('fanart.png'))
    # queries = {'mode': 'get_by_letter', 'video_type': section, 'letter': '#'}
    # _1CH.add_directory(queries, {'title':  '#123'}, img=art('#.png'), fanart=art('fanart.png'))
    for character in AZ_DIRECTORIES:
        _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'alphabet', 'letter': character},
                           {'title': character}, img=art(character + '.png'), fanart=art('fanart.png'))
        # queries = {'mode': 'get_by_letter', 'section': section, 'letter': character}
        # _1CH.add_directory(queries, {'title':  character}, img=art(character+'.png'), fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def BrowseByGenreMenu(section=None, letter=None): #2000
    print 'Browse by genres screen'
    for genre in GENRES:
        _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': '', 'genre': genre},
                           {'title': genre})
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def filename_filter_out_year(name=''):
	try:
		years=re.compile(' \((\d+)\)').findall('__'+name+'__')
		for year in years: name=name.replace(' ('+year+')','')
		name=name.replace('[B]','').replace('[/B]','').replace('[/COLOR]','').replace('[COLOR green]','')
		name=name.strip()
		return name
	except: name.strip(); return name

def add_contextsearchmenu(title, video_type, resurl=''):
    contextmenuitems = []
    nameonly=filename_filter_out_year(title); #print 'nameonly:  '+nameonly
    if os.path.exists(xbmc.translatePath("special://home/addons/") + 'plugin.video.solarmovie.so'):
    	if video_type == 'tv':
    		section = 'tv'
    		contextmenuitems.append(('Find AirDates', 'XBMC.Container.Update(%s?mode=%s&title=%s)' % ('plugin://plugin.video.solarmovie.so/','SearchForAirDates',nameonly)))
    	else: section = 'movies'
    	contextmenuitems.append(('Search Solarmovie.so', 'XBMC.Container.Update(%s?mode=%s&section=%s&title=%s)' % ('plugin://plugin.video.solarmovie.so/','ApiSearch',section,nameonly)))
    #if os.path.exists(xbmc.translatePath("special://home/addons/") + 'plugin.video.kissanime'):
    #	contextmenuitems.append(('Search KissAnime', 'XBMC.Container.Update(%s?mode=%s&pageno=1&pagecount=1&title=%s)' % ('plugin://plugin.video.kissanime/','Search',nameonly)))
    #if os.path.exists(xbmc.translatePath("special://home/addons/") + 'plugin.video.merdb'):
    #	if video_type == 'tv': section = 'tvshows'; surl='http://merdb.ru/tvshow/'
    #	else: section = 'movies'; surl='http://merdb.ru/'
    #	contextmenuitems.append(('Search MerDB', 'XBMC.Container.Update(%s?mode=%s&section=%s&url=%s&title=%s)' % ('plugin://plugin.video.merdb/','Search',section,urllib.quote_plus(surl),nameonly)))
    if os.path.exists(xbmc.translatePath("special://home/addons/") + 'plugin.video.icefilms'):
        contextmenuitems.append(('Search Icefilms',
                                 'XBMC.Container.Update(%s?mode=555&url=%s&search=%s&nextPage=%s)' % (
                                     'plugin://plugin.video.icefilms/', 'http://www.icefilms.info/', nameonly, '1')))
    if os.path.exists(xbmc.translatePath("special://home/addons/") + 'plugin.video.tubeplus'):
        if video_type == 'tv':
            section = 'tv-shows'
        else:
            section = 'movies'
        contextmenuitems.append(('Search tubeplus', 'XBMC.Container.Update(%s?mode=Search&section=%s&query=%s)' % (
            'plugin://plugin.video.tubeplus/', section, nameonly)))
    if os.path.exists(xbmc.translatePath("special://home/addons/") + 'plugin.video.tvlinks'):
        if video_type == 'tv':
            contextmenuitems.append(('Search tvlinks', 'XBMC.Container.Update(%s?mode=Search&query=%s)' % (
                'plugin://plugin.video.tvlinks/', nameonly)))
    #if os.path.exists(xbmc.translatePath("special://home/addons/") + 'plugin.video.solarmovie'):
    #    if video_type == 'tv':
    #        section = 'tv-shows'
    #    else:
    #        section = 'movies'
    #    contextmenuitems.append(('Search solarmovie', 'XBMC.Container.Update(%s?mode=Search&section=%s&query=%s)' % (
    #        'plugin://plugin.video.solarmovie/', section, title)))

    return contextmenuitems


def GetFilteredResults(section=None, genre=None, letter=None, sort='alphabet', page=None):
    try: _1CH.log('Filtered results for Section: %s Genre: %s Letter: %s Sort: %s Page: %s' % (section, genre, letter, sort, page))
    except: pass

    pageurl = BASE_URL + '/?'
    if section == 'tv': pageurl += 'tv'
    if genre:    pageurl += '&genre=' + genre
    if letter:    pageurl += '&letter=' + letter
    if sort:    pageurl += '&sort=' + sort
    if page: pageurl += '&page=%s' % page

    if page:
        page = int(page) + 1
    else:
        page = 2

    if section == 'tv':
        nextmode = 'TVShowSeasonList'
        video_type = 'tvshow'
        folder = True
        if DB == 'mysql':
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        else:
            db = orm.connect(DB_DIR)
        cur = db.cursor()
        cur.execute('SELECT url FROM subscriptions')
        subscriptions = cur.fetchall()
        db.close()
        subs = [row[0] for row in subscriptions]

    else:
        nextmode = 'GetSources'
        section = 'movie'
        video_type = 'movie'
        folder = _1CH.get_setting('auto-play') == 'false'
        subs = []

    html = get_url(pageurl)

    r = re.search('number_movies_result">([0-9,]+)', html)
    if r:
        total = int(r.group(1).replace(',', ''))
    else:
        total = 0
    total_pages = total / 24
    total = min(total, 24)

    pattern = r'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
    regex = re.finditer(pattern, html, re.DOTALL)
    resurls = []
    for s in regex:
        resurl, title, year, thumb = s.groups()
        if resurl not in resurls:
            resurls.append(resurl)
            li = build_listitem(video_type, title, year, thumb, resurl, subs=subs)
            imdb = li.getProperty('imdb')
            img = li.getProperty('img')
            li.setProperty('IsPlayable', 'true')
            queries = {'mode': nextmode, 'title': title, 'url': resurl,
                       'img': img, 'imdbnum': imdb,
                       'video_type': video_type, 'year': year}
            li_url = _1CH.build_plugin_url(queries)
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, li,
                                        isFolder=folder, totalItems=total)

    if html.find('> >> <') > -1:
        label = 'Skip to Page...'
        command = _1CH.build_plugin_url(
            {'mode': 'PageSelect', 'pages': total_pages, 'section': section, 'genre': genre, 'letter': letter,
             'sort': sort})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': 'Next Page >>'}
        _1CH.add_directory(
            {'mode': 'GetFilteredResults', 'section': section, 'genre': genre, 'letter': letter, 'sort': sort,
             'page': page},
            meta, menu_items, True, art('nextpage.png'), art('fanart.png'), is_folder=True)

    if video_type == 'tvshow':
        set_view('tvshows', 'tvshows-view')
    elif video_type == 'movie':
        set_view('movies', 'movies-view')
    _1CH.end_of_directory()


def TVShowSeasonList(url, title, year, old_imdb, old_tvdb=''):
    try: _1CH.log('Seasons for TV Show %s' % url)
    except: pass
    html = get_url(BASE_URL+url)
    adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
    r = re.search(adultregex, html, re.DOTALL)
    if r:
        try: _1CH.log('Adult content url detected')
        except: pass
        adulturl = BASE_URL + r.group(1)
        headers = {'Referer': url}
        net.set_cookies(cookiejar)
        html = net.http_GET(adulturl, headers=headers).content
        net.save_cookies(cookiejar)

    if DB == 'mysql':
        sql = 'INSERT INTO seasons(season,contents) VALUES(%s,%s) ON DUPLICATE KEY UPDATE contents = VALUES(contents)'
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True, autocommit=True)
    else:
        sql = 'INSERT or REPLACE into seasons (season,contents) VALUES(?,?)'
        db = orm.connect(DB_DIR)

    try:
        new_imdb = re.search('mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7})"', html).group(1)
    except:
        new_imdb = ''
    seasons = re.search('tv_container(.+?)<div class="clearer', html, re.DOTALL)
    if not seasons:
        _1CH.log_error('couldn\'t find seasons')
    else:
        season_container = seasons.group(1)
        season_nums = re.compile('<a href=".+?">Season ([0-9]{1,2})').findall(season_container)
        fanart = ''
        imdbnum = old_imdb
        if META_ON:
            if not old_imdb and new_imdb:
                try: _1CH.log('Imdb ID not recieved from title search, updating with new id of %s' % new_imdb)
                except: pass
                # TODO: WTF is up with xbmc.log() and utf-8 all of a sudden?
                # print 'title is unicode: %s' % isinstance(title, unicode)
                # print _1CH.log(title)
                try:
                    try: _1CH.log('Title: %s Old IMDB: %s Old TVDB: %s New IMDB %s Year: %s' % (title, old_imdb, old_tvdb, new_imdb, year))
                    except: pass
                    __metaget__.update_meta('tvshow', title, old_imdb, old_tvdb, new_imdb)
                except Exception, e:
                    try: _1CH.log('Error while trying to update metadata with:')
                    except: pass
                    # print 'Title: %s Old IMDB: %s Old TVDB: %s New IMDB %s Year: %s' % (
                    #     title, old_imdb, old_tvdb, new_imdb, year)
                    print str(e)
                imdbnum = new_imdb

            season_meta = __metaget__.get_seasons(title, imdbnum, season_nums)

        seasonList = season_container.split('<h2>')
        num = 0
        cur = db.cursor()
        for eplist in seasonList:
            temp = {'cover_url': ''}
            r = re.search(r'<a.+?>Season (\d+)</a>', eplist)
            if r:
                number = r.group(1)

                if META_ON:
                    temp = season_meta[num]
                    if FANART_ON:
                        try:
                            fanart = temp['backdrop_url']
                        except:
                            pass

                label = 'Season %s' % number
                temp['title'] = label
                cur.execute(sql, (number, eplist))

                listitem = xbmcgui.ListItem(label, iconImage=temp['cover_url'],
                                            thumbnailImage=temp['cover_url'])
                listitem.setInfo('video', temp)
                listitem.setProperty('fanart_image', fanart)
                queries = {'mode': 'TVShowEpisodeList', 'season': number,
                           'imdbnum': imdbnum, 'title': title}
                li_url = _1CH.build_plugin_url(queries)
                xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem,
                                            isFolder=True,
                                            totalItems=len(seasonList))

                num += 1
        cur.close()
        db.commit()
        xbmcplugin.endOfDirectory(int(sys.argv[1]))
        set_view('seasons', 'seasons-view')
        db.close()


def TVShowEpisodeList(ShowTitle, season, imdbnum, tvdbnum):
    sql = 'SELECT contents FROM seasons WHERE season=?'
    if DB == 'mysql':
        sql = sql.replace('?', '%s')
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
    else:
        db = orm.connect(DB_DIR)
    cur = db.cursor()
    cur.execute(sql, (season,))
    eplist = cur.fetchone()[0]
    db.close()
    r = '"tv_episode_item".+?href="(.+?)">(.*?)</a>'
    episodes = re.finditer(r, eplist, re.DOTALL)
    folder = _1CH.get_setting('auto-play') == 'false'
    for ep in episodes:
        epurl, eptitle = ep.groups()
        eptitle = re.sub(r'<[^<]+?>', '', eptitle.strip())
        eptitle = re.sub(r'\s\s+', ' ', eptitle)

        season = int(re.search('/season-([0-9]{1,4})-', epurl).group(1))
        epnum = int(re.search('-episode-([0-9]{1,3})', epurl).group(1))

        queries = {'mode': 'GetSources', 'url': epurl, 'imdbnum': imdbnum,
                   'title': ShowTitle, 'img': img}
        li_url = _1CH.build_plugin_url(queries)
        listitem = build_listitem('episode', ShowTitle, year, img, epurl, imdbnum, season, epnum)
        listitem.setProperty('IsPlayable', 'true')

        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem,
                                    isFolder=folder)

    set_view('episodes', 'episodes-view')
    _1CH.end_of_directory()


def browse_favorites(section):
    sql = 'SELECT type, name, url, year FROM favorites WHERE type = ? ORDER BY name'
    if DB == 'mysql':
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        sql = sql.replace('?', '%s')
    else:
        db = orm.connect(DB_DIR)
    cur = db.cursor()
    if section == 'tv':
        set_view('tvshows', 'tvshows-view')
    else:
        set_view('movies', 'movies-view')
    if section == 'tv':
        nextmode = 'TVShowSeasonList'
        video_type = 'tvshow'
        folder = True
        cur.execute('SELECT url FROM subscriptions')
        subscriptions = cur.fetchall()
        subs = [row[0] for row in subscriptions]
    else:
        nextmode = 'GetSources'
        video_type = 'movie'
        section = 'movie'
        subs = []
        folder = _1CH.get_setting('auto-play') == 'false'

    cur.execute(sql, (section,))
    favs = cur.fetchall()
    for row in favs:
        title = row[1]
        favurl = row[2]
        year = row[3]
        img = ''

        remfavstring = 'RunScript(plugin.video.1channel,%s,?mode=DeleteFav&section=%s&title=%s&year=%s&url=%s)' % (
            sys.argv[1], section, title, year, favurl)
        menu_items = [('Remove from Favorites', remfavstring)]

        liz = build_listitem(video_type, title, year, img, favurl, extra_cms=menu_items, subs=subs)
        img = liz.getProperty('img')
        queries = {'mode': nextmode, 'title': title, 'url': favurl,
                   'img': img, 'video_type': video_type}
        li_url = _1CH.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, liz,
                                    isFolder=folder)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))
    db.close()


def browse_favorites_website(section):
    sql = 'SELECT count(*) FROM favorites'
    if DB == 'mysql':
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        sql = sql.replace('?', '%s')
    else:
        db = orm.connect(DB_DIR)
    cur = db.cursor()
    cur.execute(sql)
    local_favs = cur.fetchall()

    if local_favs:
        _1CH.add_item({'mode': 'migrateFavs'}, {'title': 'Upload Local Favorites'})

    user = _1CH.get_setting('username')
    if not section: section = 'movies'
    url = '/profile.php?user=%s&fav&show=%s'
    url = BASE_URL + url % (user, section)
    cookiejar = _1CH.get_profile()
    cookiejar = os.path.join(cookiejar, 'cookies')
    net = Net()
    net.set_cookies(cookiejar)
    html = net.http_GET(url).content
    if not '<a href="/logout.php">[ Logout ]</a>' in html:
        html = login_and_retry(url)

    if section == 'tv':
        video_type = 'tvshow'
        nextmode = 'TVShowSeasonList'
        folder = True
        if DB == 'mysql':
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        else:
            db = orm.connect(DB_DIR)
        cur = db.cursor()
        cur.execute('SELECT url FROM subscriptions')
        subs = cur.fetchall()
    else:
        video_type = 'movie'
        nextmode = 'GetSources'
        folder = _1CH.get_setting('auto-play') == 'false'
        subs = []

    pattern = '''<div class="index_item"> <a href="(.+?)"><img src="(.+?(\d{1,4})?\.jpg)" width="150" border="0">.+?<td align="center"><a href=".+?">(.+?)</a></td>.+?class="favs_deleted"><a href=\'(.+?)\' ref=\'delete_fav\''''
    regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for item in regex.finditer(html):
        link, img, year, title, delete = item.groups()
        if not year or len(year) != 4:
            year = ''

        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(
            {'mode': 'DeleteFav', 'section': section, 'title': title, 'url': link, 'year': year})
        menu_items = [('Delete Favorite', runstring)]

        liz = build_listitem(video_type, title, year, img, link, extra_cms=menu_items, subs=subs)
        img = liz.getProperty('img')
        queries = {'mode': nextmode, 'title': title, 'url': link,
                   'img': img, 'video_type': video_type}
        li_url = _1CH.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, liz,
                                    isFolder=folder)
    _1CH.end_of_directory()


def migrate_favs_to_web():
    init_database()
    sql = 'SELECT type, name, url, year FROM favorites ORDER BY name'
    if DB == 'mysql':
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        sql = sql.replace('?', '%s')
    else:
        db = orm.connect(DB_DIR)
    cur = db.cursor()
    cur.execute(sql)
    all_favs = cur.fetchall()
    progress = xbmcgui.DialogProgress()
    ln1 = 'Uploading your favorites to www.primewire.ag...'
    progress.create('Uploading Favorites', ln1)
    net = Net()
    cookiejar = _1CH.get_profile()
    cookiejar = os.path.join(cookiejar, 'cookies')
    failures = []
    for fav in all_favs:
        if progress.iscanceled(): return
        title = fav[1]
        favurl = fav[2]
        progress.update(0, ln1, 'Adding %s' % title)
        try:
            id_num = re.search(r'.+(?:watch|tv)-([\d]+)-', favurl)
            if id:
                save_url = "%s/addtofavs.php?id=%s&whattodo=add" % BASE_URL
                save_url = save_url % id_num.group(1)
                try: _1CH.log(save_url)
                except: pass
                net.set_cookies(cookiejar)
                net.http_GET(save_url)
                net.save_cookies(cookiejar)
                progress.update(0, ln1, 'Adding %s' % title, 'Success')
                try: _1CH.log('%s added successfully' % title)
                except: pass
        except Exception, e:
            try: _1CH.log(e)
            except: pass
            failures.append((title, favurl))
    progress.close()
    dialog = xbmcgui.Dialog()
    ln1 = 'Do you want to remove the successful'
    ln2 = 'uploads from local favorites?'
    ln3 = 'THIS CANNOT BE UNDONE'
    yes = 'Keep'
    no = 'Delete'
    ret = dialog.yesno('Migration Complete', ln1, ln2, ln3, yes, no)
    # failures = [('title1','url1'), ('title2','url2'), ('title3','url3'), ('title4','url4'), ('title5','url5'), ('title6','url6'), ('title7','url7')]
    if ret:
        if failures:
            params = ', '.join('%s' if DB == 'mysql' else '?' for item in failures)
            sql_delete = 'DELETE FROM favorites WHERE url NOT IN (SELECT url FROM favorites WHERE url IN (%s))'
            sql_delete %= params
            try: _1CH.log(sql_delete)
            except: pass
            urls = [item[1] for item in failures]
            try: _1CH.log(urls)
            except: pass
            # cur.execute(sql_delete, failures)
        else:
            cur.execute('DELETE FROM favorites')


def get_by_letter(letter, section):
    try: _1CH.log('Showing results for letter: %s' % letter)
    except: pass
    if section == 'tv':
        url = '%s/alltvshows.php' % BASE_URL
        video_type = 'tvshow'
        nextmode = 'TVShowSeasonList'
        folder = True
        if DB == 'mysql':
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        else:
            db = orm.connect(DB_DIR)
        cur = db.cursor()
        cur.execute('SELECT url FROM subscriptions')
        subs = cur.fetchall()
    else:
        url = '%s/allmovies.php' % BASE_URL
        video_type = 'movie'
        nextmode = 'GetSources'
        folder = _1CH.get_setting('auto-play') == 'false'

    html = get_url(url)
    regex = r'<div class="regular_page">\s+<h1 class="titles">(.+)'
    regex += r'<div class="clearer"></div>\s+</div>'
    container = re.search(regex, html, re.DOTALL | re.I).group(1)
    ltr_regex = '[%s]</h2>(.+?)<h2>' % letter
    ltr_container = re.search(ltr_regex, container, re.DOTALL | re.I).group(1)
    item_regex = r'<div class="all_movies_item">'
    item_regex += r'<a href="(.+?)"> ?(.+?)</a> \[ (.+?) \]</div>'
    listings = re.finditer(item_regex, ltr_container)
    for item in listings:
        resurl, title, year = item.groups()

        listitem = build_listitem(video_type, title, year, img, resurl, subs=subs)
        url = '%s/%s' % (BASE_URL, resurl)
        # TODO: make a decision on handling meta here
        queries = {'mode': nextmode, 'title': title, 'url': url,
                   'img': meta['cover_url'], 'imdbnum': meta['imdb_id'],
                   'video_type': video_type, 'year': year}
        li_url = _1CH.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem,
                                    isFolder=folder)
    _1CH.end_of_directory()


def create_meta(video_type, title, year, thumb):
    try:
        year = int(year)
    except:
        year = 0
    year = str(year)
    meta = {'title': title, 'year': year, 'imdb_id': '', 'overlay': ''}
    if META_ON:
        try:
            if video_type == 'tvshow':
                meta = __metaget__.get_meta(video_type, title)
                if not (meta['imdb_id'] or meta['tvdb_id']):
                    meta = __metaget__.get_meta(video_type, title, year=year)

            else:  # movie
                meta = __metaget__.get_meta(video_type, title, year=year)
                alt_id = meta['tmdb_id']

            if video_type == 'tvshow' and not USE_POSTERS:
                meta['cover_url'] = meta['banner_url']
            if POSTERS_FALLBACK and meta['cover_url'] in ('/images/noposter.jpg', ''):
                meta['cover_url'] = thumb
        except:
            try: _1CH.log('Error assigning meta data for %s %s %s' % (video_type, title, year))
            except: pass
    return meta


def scan_by_letter(section, letter):
    import traceback

    try: _1CH.log('Building meta for %s letter %s' % (section, letter))
    except: pass
    dlg = xbmcgui.DialogProgress()
    dlg.create('Scanning %s Letter %s' % (section, letter))
    if section == 'tvshow':
        url = BASE_URL + '/alltvshows.php'
    else:
        url = BASE_URL + '/allmovies.php'
    html = get_url(url)

    pattern = '%s</h2>(.+?)(?:<h2>|<div class="clearer">)' % letter
    container = re.search(pattern, html, re.S).group(1)
    item_pattern = re.compile(r'<a.+?>(.+?)</a> \[ (\d{4}) \]</div>')
    for item in item_pattern.finditer(container):
        title, year = item.groups()
        success = False
        attempts_remaining = 4
        while attempts_remaining and not success:
            dlg.update(0, '%s (%s)' % (title, year))
            try:
                __metaget__.get_meta(section, title, year=year)
                success = True
            except Exception, e:
                attempts_remaining -= 1
                line1 = '%s (%s)' % (title, year)
                line2 = 'Failed: %s  attempts remaining' % attempts_remaining
                line3 = str(e)
                dlg.update(0, line1, line2, line3)
                traceback.print_exc()
            if dlg.iscanceled(): break
        if dlg.iscanceled(): break
    return


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
                __metaget__ = metahandlers.MetaData(preparezip=prepare_zip)

            if letters_completed <= letters_per_zip:
                scan_by_letter(video_type, letter)
                letters_completed += 1

            if (letters_completed == letters_per_zip
                or letter == '123' or get_dir_size(container.cache_path) > (500 * 1024 * 1024)):
                end_letter = letter
                arcname = 'MetaPack-%s-%s-%s.zip' % (video_type, start_letter, end_letter)
                arcname = os.path.join(savpath, arcname)
                __metaget__.__del__()
                zipdir(container.cache_path, arcname)
                __metaget__ = metahandlers.MetaData(preparezip=PREPARE_ZIP)
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
    all_packs = metapacks.list()
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


def format_eta(seconds):
    minutes, seconds = divmod(seconds, 60)
    if minutes > 60:
        hours, minutes = divmod(minutes, 60)
        return "ETA: %02d:%02d:%02d " % (hours, minutes, seconds)
    else:
        return "ETA: %02d:%02d " % (minutes, seconds)


def repair_missing_images():
    cont = metacontainers.MetaContainer()
    if DB == 'mysql':
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
    else:
        db = orm.connect(cont.videocache)
    dbcur = db.cursor()
    dlg = xbmcgui.DialogProgress()
    dlg.create('Repairing Images', '', '', '')
    for video_type in ('tvshow', 'movie'):
        total = 'SELECT count(*) from %s_meta WHERE ' % video_type
        total += 'imgs_prepacked = "true"'
        total = dbcur.execute(total).fetchone()[0]
        statement = 'SELECT title,cover_url,backdrop_url'
        if video_type == 'tvshow': statement += ',banner_url'
        statement += ' FROM %s_meta WHERE imgs_prepacked = "true"' % video_type
        complete = 1.0
        start_time = time.time()
        already_existing = 0

        for row in dbcur.execute(statement):
            title = row[0]
            cover = row[1]
            backdrop = row[2]
            if video_type == 'tvshow':
                banner = row[3]
            else:
                banner = False
            percent = int((complete * 100) / total)
            entries_per_sec = (complete - already_existing)
            entries_per_sec /= max(float((time.time() - start_time)), 1)
            total_est_time = total / max(entries_per_sec, 1)
            eta = total_est_time - (time.time() - start_time)

            eta = format_eta(eta)
            dlg.update(percent, eta + title, '')
            if cover:
                dlg.update(percent, eta + title, cover)
                img_name = __metaget__._picname(cover)
                img_path = os.path.join(__metaget__.mvcovers, img_name[0].lower())
                file_path = os.path.join(img_path, img_name)
                if not os.path.isfile(file_path):
                    retries = 4
                    while retries:
                        try:
                            __metaget__._downloadimages(cover, img_path, img_name)
                            break
                        except:
                            retries -= 1
                else:
                    already_existing -= 1
            if backdrop:
                dlg.update(percent, eta + title, backdrop)
                img_name = __metaget__._picname(backdrop)
                img_path = os.path.join(__metaget__.mvbackdrops, img_name[0].lower())
                file_path = os.path.join(img_path, img_name)
                if not os.path.isfile(file_path):
                    retries = 4
                    while retries:
                        try:
                            __metaget__._downloadimages(backdrop, img_path, img_name)
                            break
                        except:
                            retries -= 1
                else:
                    already_existing -= 1
            if banner:
                dlg.update(percent, eta + title, banner)
                img_name = __metaget__._picname(banner)
                img_path = os.path.join(__metaget__.tvbanners, img_name[0].lower())
                file_path = os.path.join(img_path, img_name)
                if not os.path.isfile(file_path):
                    retries = 4
                    while retries:
                        try:
                            __metaget__._downloadimages(banner, img_path, img_name)
                            break
                        except:
                            retries -= 1
                else:
                    already_existing -= 1
            if dlg.iscanceled(): return False
            complete += 1


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


def get_dir_size(start_path):
    print 'Calculating size of %s' % start_path
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for each_file in filenames:
            fpath = os.path.join(dirpath, each_file)
            total_size += os.path.getsize(fpath)
    print 'Calculated: %s' % total_size
    return total_size


def set_view(content, view_type):
    # set content type so library shows more views and info
    if content:
        xbmcplugin.setContent(int(sys.argv[1]), content)
    if _1CH.get_setting('auto-view') == 'true':
        view_mode = _1CH.get_setting(view_type)
        xbmc.executebuiltin("Container.SetViewMode(%s)" % view_mode)

    # set sort methods - probably we don't need all of them
    xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RATING)
    xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_PROGRAM_COUNT)
    xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
    xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_GENRE)


def add_to_library(video_type, url, title, img, year, imdbnum):
    try: _1CH.log('Creating .strm for %s %s %s %s %s %s' % (video_type, title, imdbnum, url, img, year))
    except: pass
    if video_type == 'tvshow':
        save_path = _1CH.get_setting('tvshow-folder')
        save_path = xbmc.translatePath(save_path)
        show_title = title.strip()
        net = Net()
        cookiejar = _1CH.get_profile()
        cookiejar = os.path.join(cookiejar, 'cookies')
        net.set_cookies(cookiejar)
        html = net.http_GET(BASE_URL + url).content
        net.save_cookies(cookiejar)
        adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
        adult = re.search(adultregex, html, re.DOTALL)
        if adult:
            try: _1CH.log('Adult content url detected')
            except: pass
            adulturl = BASE_URL + adult.group(1)
            headers = {'Referer': url}
            net.set_cookies(cookiejar)
            html = net.http_GET(adulturl, headers=headers).content
            net.save_cookies(cookiejar)
        seasons = re.search('tv_container(.+?)<div class="clearer', html, re.DOTALL)
        if not seasons:
            _1CH.log_error('No Seasons found for %s at %s' % (show_title, url))
        else:
            season_container = seasons.group(1)
            season_list = season_container.split('<h2>')
            for eplist in season_list:
                match = re.search('<a.+?>(.+?)</a>', eplist)
                if match:
                    season = match.group(1)
                    r = '"tv_episode_item".+?href="(.+?)">(.*?)</a>'
                    episodes = re.finditer(r, eplist, re.DOTALL)
                    for ep_line in episodes:
                        epurl, eptitle = ep_line.groups()
                        eptitle = re.sub('<[^<]+?>', '', eptitle.strip())
                        eptitle = re.sub(r'\s\s+', ' ', eptitle)

                        pattern = r'tv-\d{1,10}-.*/season-(\d{1,4})-episode-(\d{1,4})'
                        match = re.search(pattern, epurl, re.I | re.DOTALL)
                        seasonnum = match.group(1)
                        epnum = match.group(2)

                        filename = '%s S%sE%s.strm'
                        filename = filename % (show_title, seasonnum, epnum)
                        filename = re.sub(r'[^\w\-_\. ]', '_', filename)
                        show_title = re.sub(r'[^\w\-_\. ]', '_', show_title)
                        final_path = os.path.join(save_path, show_title, season, filename)
                        final_path = xbmc.makeLegalFilename(final_path)
                        if not xbmcvfs.exists(os.path.dirname(final_path)):
                            try:
                                try: xbmcvfs.mkdirs(os.path.dirname(final_path))
                                except: os.path.mkdir(os.path.dirname(final_path))
                            except:
                                try: _1CH.log('Failed to create directory %s' % final_path)
                                except: pass

                        queries = {'mode': 'GetSources', 'url': epurl, 'imdbnum': '', 'title': show_title, 'img': '',
                                   'dialog': 1, 'video_type': 'episode'}
                        strm_string = _1CH.build_plugin_url(queries)
                        try: _1CH.log('Writing strm: %s' % strm_string)
                        except: pass
                        # if not xbmcvfs.exists(final_path):
                        #temp disabled bc of change in .strm format. Reenable in next version
                        try:
                            file_desc = xbmcvfs.File(final_path, 'w')
                            file_desc.write(strm_string)
                            file_desc.close()
                        except Exception, e:
                            try: _1CH.log('Failed to create .strm file: %s\n%s' % (final_path, e))
                            except: pass

    elif video_type == 'movie':
        save_path = _1CH.get_setting('movie-folder')
        save_path = xbmc.translatePath(save_path)
        strm_string = _1CH.build_plugin_url(
            {'mode': 'GetSources', 'url': url, 'imdbnum': imdbnum, 'title': title, 'img': img, 'year': year,
             'dialog': 1, 'video_type': 'movie'})
        if year: title = '%s (%s)' % (title, year)
        filename = '%s.strm' % title
        filename = re.sub(r'[^\w\-_\. ]', '_', filename)
        title = re.sub(r'[^\w\-_\. ]', '_', title)
        final_path = os.path.join(save_path, title, filename)
        final_path = xbmc.makeLegalFilename(final_path)
        if not xbmcvfs.exists(os.path.dirname(final_path)):
            try:
                try: xbmcvfs.mkdirs(os.path.dirname(final_path))
                except: os.path.mkdir(os.path.dirname(final_path))
            except Exception, e:
                try: _1CH.log('Failed to create directory %s' % final_path)
                except: pass
                # if not xbmcvfs.exists(final_path):
                #temp disabled bc of change in .strm format. Reenable in next version
        try:
            file_desc = xbmcvfs.File(final_path, 'w')
            file_desc.write(strm_string)
            file_desc.close()
        except Exception, e:
            try: _1CH.log('Failed to create .strm file: %s\n%s' % (final_path, e))
            except: pass


def add_subscription(url, title, img, year, imdbnum, day=''):
    try:
        if len(day)==0: day=datetime.date.today().strftime('%A')
        elif day==' ': day=''
        sql = 'INSERT INTO subscriptions (url, title, img, year, imdbnum, day) VALUES (?,?,?,?,?,?)' #sql = 'INSERT INTO subscriptions (url, title, img, year, imdbnum) VALUES (?,?,?,?,?)'
        if DB == 'mysql':
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
            sql = sql.replace('?', '%s')
        else:
            db = orm.connect(DB_DIR)
        cur = db.cursor()
        try: 
        	cur.execute(sql, (url, title, img, year, imdbnum, day)) #cur.execute(sql, (url, title, img, year, imdbnum))
        except: ## Note: Temp-Fix for Adding the Extra COLUMN to the SQL TABLE ##
        	try: 
        		cur.execute('ALTER TABLE subscriptions ADD day TEXT')
        		cur.execute(sql, (url, title, img, year, imdbnum, day)) #cur.execute(sql, (url, title, img, year, imdbnum))
        	except:
        		builtin = "XBMC.Notification(Subscribe,Already subscribed to '%s',2000)" % title
        		xbmc.executebuiltin(builtin)
        		xbmc.executebuiltin('Container.Update')
        		return
        db.commit()
        db.close()
        add_to_library('tvshow', url, title, img, year, imdbnum)
        builtin = "XBMC.Notification(Subscribe,Subscribed to '%s',2000)" % title
        xbmc.executebuiltin(builtin)
    except orm.IntegrityError:
        builtin = "XBMC.Notification(Subscribe,Already subscribed to '%s',2000)" % title
        xbmc.executebuiltin(builtin)
    xbmc.executebuiltin('Container.Update')


def cancel_subscription(url, title, img, year, imdbnum):
    sql_delete = 'DELETE FROM subscriptions WHERE url=? AND title=? AND year=?'
    if DB == 'mysql':
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        sql_delete = sql_delete.replace('?', '%s')
    else: db = orm.connect(DB_DIR)
    db_cur = db.cursor()
    title = unicode(title, 'utf-8')
    db_cur.execute(sql_delete, (url, title, year))
    db.commit()
    db.close()
    xbmc.executebuiltin('Container.Refresh')


def update_subscriptions():
    if DB == 'mysql':
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
    else: db = orm.connect(DB_DIR)
    cur = db.cursor()
    cur.execute('SELECT * FROM subscriptions')
    subs = cur.fetchall()
    for sub in subs:
        add_to_library('tvshow', sub[0], sub[1], sub[2], sub[3], sub[4])
    db.close()
    if _1CH.get_setting('library-update') == 'true':
        xbmc.executebuiltin('UpdateLibrary(video)')


def clean_up_subscriptions():
    try: _1CH.log('Cleaning up dead subscriptions')
    except: pass
    sql_delete = 'DELETE FROM subscriptions WHERE url=?'
    if DB == 'mysql':
        db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        sql_delete = sql_delete.replace('?', '%s')
    else: db = orm.connect(DB_DIR)
    cur = db.cursor()
    cur.execute('SELECT * FROM subscriptions')
    subs = cur.fetchall()
    to_clean = []
    for sub in subs:
        meta = __metaget__.get_meta('tvshow', sub[1], year=sub[3])
        if meta['status'] == 'Ended':
            to_clean.append(sub[0])
            try: _1CH.log('Selecting %s  for removal' % sub[1])
            except: pass
    if to_clean:
        to_clean = zip(to_clean)
        cur.executemany(sql_delete, to_clean)
        db.commit()
    db.close()


def manage_subscriptions(day=''):
    _1CH.add_item({'mode': 'update_subscriptions'}, {'title': 'Update Subscriptions'})
    _1CH.add_item({'mode': 'clean_up_subscriptions'}, {'title': 'Clean Up Subscriptions'})
    D1Code=_1CH.get_setting('format-subscription-day')
    D2Code=_1CH.get_setting('format-subscription-day-tag')
    fanart = art('fanart.png')
    _1CH.add_directory({'day':'','mode':'manage_subscriptions'},{'title':D1Code % 'ALL'},is_folder=True,fanart=fanart,img=art('subscriptions.png'))
    if day=='':
    	d='Monday'; _1CH.add_directory({'day':d,'mode':'manage_subscriptions'},{'title':D1Code % d},is_folder=True,fanart=fanart,img=art(d+'.png'))
    	d='Tuesday'; _1CH.add_directory({'day':d,'mode':'manage_subscriptions'},{'title':D1Code % d},is_folder=True,fanart=fanart,img=art(d+'.png'))
    	d='Wednesday'; _1CH.add_directory({'day':d,'mode':'manage_subscriptions'},{'title':D1Code % d},is_folder=True,fanart=fanart,img=art(d+'.png'))
    	d='Thursday'; _1CH.add_directory({'day':d,'mode':'manage_subscriptions'},{'title':D1Code % d},is_folder=True,fanart=fanart,img=art(d+'.png'))
    	d='Friday'; _1CH.add_directory({'day':d,'mode':'manage_subscriptions'},{'title':D1Code % d},is_folder=True,fanart=fanart,img=art(d+'.png'))
    	d='Saturday'; _1CH.add_directory({'day':d,'mode':'manage_subscriptions'},{'title':D1Code % d},is_folder=True,fanart=fanart,img=art(d+'.png'))
    	d='Sunday'; _1CH.add_directory({'day':d,'mode':'manage_subscriptions'},{'title':D1Code % d},is_folder=True,fanart=fanart,img=art(d+'.png'))
    set_view('tvshows', 'tvshows-view')
    if DB == 'mysql': db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
    else: db = orm.connect(DB_DIR)
    cur = db.cursor()
    S='SELECT * FROM subscriptions'
    if len(day) > 0: S+=' WHERE day = "%s"' % (day)
    cur.execute(S)
    subs = cur.fetchall()
    for sub in subs:
        meta = create_meta('tvshow', sub[1], sub[3], '')
        meta['title'] = format_label_sub(meta)

        menu_items = add_contextsearchmenu(meta['title'], 'tv')
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(
            {'mode': 'cancel_subscription', 'url': sub[0], 'title': sub[1], 'img': sub[2], 'year': sub[3], 'imdbnum': sub[4]})
        menu_items.append(('Cancel subscription', runstring,))
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(
            {'mode': 'subscriptions_day', 'url': sub[0], 'title': sub[1], 'img': sub[2], 'year': sub[3], 'imdbnum': sub[4], 'day': ' '})
        menu_items.append(('Remove Day', runstring,))
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(
            {'mode': 'subscriptions_day', 'url': sub[0], 'title': sub[1], 'img': sub[2], 'year': sub[3], 'imdbnum': sub[4], 'day': str(datetime.date.today().strftime('%A'))})
        menu_items.append(('Subscription Day', runstring,))
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(
            {'mode': 'SaveFav', 'section': 'tv', 'title': sub[1], 'url': sub[0], 'year': sub[3]})
        menu_items.append(('Add to Favorites', runstring,))
        menu_items.append(('Show Information', 'XBMC.Action(Info)',))

        if META_ON:
            try: fanart = meta['backdrop_url']
            except: fanart = art('fanart.png')
            try: img = meta['cover_url']
            except: img = ''
        else: fanart = art('fanart.png'); img = ''

        # _1CH.add_item({'mode':'manage_subscriptions'},meta,menu_items,True,img,fanart,is_folder=True)
        try: 
        	if len(sub[5]) > 0: meta['title']=(D2Code % (D1Code % (sub[5])))+' '+meta['title']
        except: pass
        listitem = xbmcgui.ListItem(meta['title'], iconImage=img, thumbnailImage=img)
        listitem.setInfo('video', meta)
        listitem.setProperty('fanart_image', fanart)
        listitem.addContextMenuItems(menu_items, replaceItems=True)
        queries = {'mode': 'TVShowSeasonList', 'title': sub[1], 'url': sub[0], 'img': img, 'imdbnum': meta['imdb_id'], 'video_type': 'tvshow', 'year': sub[3]}
        li_url = _1CH.build_plugin_url(queries)
        try: xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem, isFolder=True, totalItems=len(subs))
        except: pass
    db.close()
    _1CH.end_of_directory()


def clean_filename(filename):
    # filename = _1CH.unescape(filename)
    return re.sub('[/:"*?<>|]+', ' ', filename)


def multikeysort(items, columns, functions=None, getter=itemgetter):
    """Sort a list of dictionary objects or objects by multiple keys bidirectionally.

    Keyword Arguments:
    items -- A list of dictionary objects or objects
    columns -- A list of column names to sort by. Use -column to sort in descending order
    functions -- A Dictionary of Column Name -> Functions to normalize or process each column value
    getter -- Default "getter" if column function does not exist
              operator.itemgetter for Dictionaries
              operator.attrgetter for Objects
    """
    if not functions: functions = {}
    comparers = []
    for col in columns:
        column = col[1:] if col.startswith('-') else col
        if not column in functions:
            functions[column] = getter(column)
        comparers.append((functions[column], 1 if column == col else -1))

    def comparer(left, right):
        for func, polarity in comparers:
            result = cmp(func(left), func(right))
            if result:
                return polarity * result
        else:
            return 0

    return sorted(items, cmp=comparer)


def compose(inner_func, *outer_funcs):
    """Compose multiple unary functions together into a single unary function"""
    if not outer_funcs:
        return inner_func
    outer_func = compose(*outer_funcs)
    return lambda *args, **kwargs: outer_func(inner_func(*args, **kwargs))


def rank_host(source):
    host = source['host']
    ranking = _1CH.get_setting('host-rank').split(',')
    host = host.lower()
    for tier in ranking:
        tier = tier.lower()
        if host in tier.split('|'):
            return ranking.index(tier) + 1
    return 1000


def refresh_meta(video_type, old_title, imdb, alt_id, year, new_title=''):
    __metaget__ = metahandlers.MetaData()
    if new_title:
        search_title = new_title
    else:
        search_title = old_title

    if video_type == 'tvshow':
        api = metahandlers.TheTVDB()
        results = api.get_matching_shows(search_title)
        search_meta = []
        for item in results:
            option = {'tvdb_id': item[0], 'title': item[1], 'imdb_id': item[2], 'year': year}
            search_meta.append(option)

    else:
        search_meta = __metaget__.search_movies(search_title)
    print 'search_meta: %s' % search_meta

    option_list = ['Manual Search...']
    for option in search_meta:
        if 'year' in option:
            disptitle = '%s (%s)' % (option['title'], option['year'])
        else:
            disptitle = option['title']
        option_list.append(disptitle)
    dialog = xbmcgui.Dialog()
    index = dialog.select('Choose', option_list)

    if index == 0:
        refresh_meta_manual(video_type, old_title, imdb, alt_id, year)
    elif index > -1:
        new_imdb_id = search_meta[index - 1]['imdb_id']

        #Temporary workaround for metahandlers problem:
        #Error attempting to delete from cache table: no such column: year
        if video_type == 'tvshow': year = ''

        try: _1CH.log(search_meta[index - 1])
        except: pass
        __metaget__.update_meta(video_type, old_title, imdb, year=year)
        xbmc.executebuiltin('Container.Refresh')


def refresh_meta_manual(video_type, old_title, imdb, alt_id, year):
    keyboard = xbmc.Keyboard()
    if year:
        disptitle = '%s (%s)' % (old_title, year)
    else:
        disptitle = old_title
    keyboard.setHeading('Enter a title')
    keyboard.setDefault(disptitle)
    keyboard.doModal()
    if keyboard.isConfirmed():
        search_string = keyboard.getText()
        refresh_meta(video_type, old_title, imdb, alt_id, year, search_string)


def migrate_to_mysql():
    try:
        from sqlite3 import dbapi2 as sqlite

        try: _1CH.log('Loading sqlite3 for migration')
        except: pass
    except:
        from pysqlite2 import dbapi2 as sqlite

        try: _1CH.log('pysqlite2 for migration')
        except: pass

    DB_NAME = _1CH.get_setting('db_name')
    DB_USER = _1CH.get_setting('db_user')
    DB_PASS = _1CH.get_setting('db_pass')
    DB_ADDR = _1CH.get_setting('db_address')

    DB_DIR = os.path.join(xbmc.translatePath("special://database"), 'onechannelcache.db')
    sqlite_db = sqlite.connect(DB_DIR)
    mysql_db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
    table_count = 1
    record_count = 1
    all_tables = ['favorites', 'subscriptions', 'bookmarks']
    prog_ln1 = 'Migrating table %s of %s' % (table_count, 3)
    progress = xbmcgui.DialogProgress()
    progress.create('DB Migration', prog_ln1)
    while not progress.iscanceled() and table_count < 3:
        for table in all_tables:
            mig_prog = int((table_count * 100) / 3)
            prog_ln1 = 'Migrating table %s of %s' % (table_count, 3)
            progress.update(mig_prog, prog_ln1)
            record_sql = 'SELECT * FROM %s' % table
            print record_sql
            cur = mysql_db.cursor()
            all_records = sqlite_db.execute(record_sql).fetchall()
            for record in all_records:
                prog_ln1 = 'Migrating table %s of %s' % (table_count, 3)
                prog_ln2 = 'Record %s of %s' % (record_count, len(all_records))
                progress.update(mig_prog, prog_ln1, prog_ln2)
                args = ','.join('?' * len(record))
                args = args.replace('?', '%s')
                insert_sql = 'REPLACE INTO %s VALUES(%s)' % (table, args)
                print insert_sql
                cur.execute(insert_sql, record)
                record_count += 1
            table_count += 1
            record_count = 1
            mysql_db.commit()
    sqlite_db.close()
    mysql_db.close()
    progress.close()
    dlg = xbmcgui.Dialog()
    ln1 = 'Do you want to permanantly delete'
    ln2 = 'the old database?'
    ln3 = 'THIS CANNOT BE UNDONE'
    yes = 'Keep'
    no = 'Delete'
    ret = dlg.yesno('Migration Complete', ln1, ln2, ln3, yes, no)
    if ret:
        os.remove(DB_DIR)


def login_and_retry(redirect):
    try: _1CH.log('Logging in for url %s' % redirect)
    except: pass
    user = _1CH.get_setting('username')
    passwd = _1CH.get_setting('passwd')
    url = BASE_URL + '/login.php'
    net = Net()
    cookiejar = _1CH.get_profile()
    cookiejar = os.path.join(cookiejar, 'cookies')
    host = re.sub('http://', '', BASE_URL)
    headers = {'Referer': redirect, 'Origin': BASE_URL, 'Host': host, 'User-Agent': USER_AGENT}
    form_data = {'username': user, 'password': passwd, 'remember': 'on', 'login_submit': 'Login'}
    html = net.http_POST(url, headers=headers, form_data=form_data).content
    if '<a href="/logout.php">[ Logout ]</a>' in html:
        net.save_cookies(cookiejar)
        return html
    else:
        try: _1CH.log('Failed to login')
        except: pass
        print html


def website_is_integrated():
    enabled = _1CH.get_setting('site_enabled') == 'true'
    user = _1CH.get_setting('usename') is not None
    passwd = _1CH.get_setting('passwd') is not None
    if enabled and user and passwd:
        return True
    else:
        return False


def build_listitem(video_type, title, year, img, resurl, imdbnum='', season='', episode='', extra_cms=None, subs=None):
    if not subs: subs = []
    if not extra_cms: extra_cms = []
    menu_items = add_contextsearchmenu(title, section, resurl)
    menu_items = menu_items + extra_cms

    queries = {'mode': 'SaveFav', 'section': section, 'title': title, 'url': resurl, 'year': year}
    runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(queries)
    menu_items.append(('Add to Favorites', runstring), )

    queries = {'mode': 'add_to_library', 'video_type': video_type, 'title': title, 'img': img, 'year': year,
               'url': resurl}
    runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(queries)
    menu_items.append(('Add to Library', runstring), )
    if video_type in ('tv', 'tvshow', 'episode'):
        queries = {'mode': 'add_subscription', 'video_type': video_type, 'url': resurl, 'title': title,
                   'img': img, 'year': year}
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(queries)
        menu_items.append(('Subscribe', runstring), )
    else:
        plugin_str = 'plugin://plugin.video.couchpotato_manager'
        plugin_str += '/movies/add?title=%s' % title
        runstring = 'XBMC.RunPlugin(%s)' % plugin_str
        menu_items.append(('Add to CouchPotato', runstring), )

    if META_ON:
        if video_type == 'episode':
            meta = __metaget__.get_episode_meta(title, imdbnum, season, episode)
            meta['TVShowTitle'] = title
        else:
            meta = create_meta(video_type, title, year, img)

        if 'cover_url' in meta:
            img = meta['cover_url']

        menu_items.append(('Show Information', 'XBMC.Action(Info)'), )

        queries = {'mode': 'refresh_meta', 'video_type': video_type, 'title': meta['title'], 'imdb': meta['imdb_id'],
                   'alt_id': 'imdbnum', 'year': year}
        runstring = _1CH.build_plugin_url(queries)
        runstring = 'RunPlugin(%s)' % runstring
        menu_items.append(('Refresh Metadata', runstring,))

        if 'trailer_url' in meta:
            try:
            	url = meta['trailer_url']
            	url = url.encode('base-64').strip()
            	runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': 'PlayTrailer', 'url': url})
            	menu_items.append(('Watch Trailer', runstring,))
            except: pass

        if meta['overlay'] == 6:
            label = 'Mark as watched'
            new_status = 7
        else:
            label = 'Mark as unwatched'
            new_status = 6

        queries = {'mode': 'ChangeWatched', 'title': title, 'imdbnum': meta['imdb_id'], 'video_type': video_type, 'year': year, 'watched': new_status}
        if video_type in ('tv', 'tvshow', 'episode'):
            queries['season'] = season
            queries['episode'] = episode
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(queries)
        menu_items.append((label, runstring,))

        fanart = ''
        if FANART_ON:
            try:
                fanart = meta['backdrop_url']
            except:
                fanart = ''

        if video_type == 'tvshow':
            if resurl in subs:
                meta['title'] = format_label_sub(meta)
            else:
                meta['title'] = format_label_tvshow(meta)
        elif video_type == 'episode':
            meta['title'] = format_tvshow_episode(meta)
        else:
            meta['title'] = format_label_movie(meta)

        listitem = xbmcgui.ListItem(meta['title'], iconImage=img,
                                    thumbnailImage=img)
        listitem.setInfo('video', meta)
        listitem.setProperty('fanart_image', fanart)
        listitem.setProperty('imdb', meta['imdb_id'])
        listitem.setProperty('img', img)
        listitem.addContextMenuItems(menu_items, replaceItems=True)
    else:  # Metadata off
        if video_type == 'episode':
            disp_title = '%sx%s' % (season, episode)
            listitem = xbmcgui.ListItem(disp_title, iconImage=img,
                                        thumbnailImage=img)
        else:
            if year:
                disp_title = '%s (%s)' % (title, year)
            else:
                disp_title = title
            listitem = xbmcgui.ListItem(disp_title, iconImage=img,
                                        thumbnailImage=img)
            listitem.addContextMenuItems(menu_items, replaceItems=True)
    return listitem


def upgrade_db():
    try: _1CH.log('Upgrading db...')
    except: pass
    for table in ('subscriptions', 'favorites'):
        sql = "UPDATE %s SET url = replace(url, 'http://www.1channel.ch', '')" % table
        if DB == 'mysql':
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        else:
            db = orm.connect(DB_DIR)
        cur = db.cursor()
        cur.execute(sql)
        db.commit()
        db.close()


def fix_existing_strms():
    for folder in ('tvshow-folder', 'movie-folder'):
        save_path = _1CH.get_setting(folder)
        save_path = xbmc.translatePath(save_path)
        for root, dirs, files in os.walk(save_path):
            for current_file in files:
                if current_file.endswith('.strm'):
                    try: _1CH.log("processing file: %s" % current_file)
                    except: pass
                    full_path = os.path.join(root, current_file)
                    with open(full_path, 'r+') as target:
                        content = target.read()
                        target.seek(0)
                        new_content = content.replace('&url=http%3A%2F%2Fwww.1channel.ch', '&url=')
                        if not '&video_type=' in new_content:
                            if folder == 'tvshow-folder':
                                new_content += '&video_type=episode'
                            elif folder == 'movie-folder':
                                new_content += '&video_type=movie'
                        try: _1CH.log('Writing new content: %s' % new_content)
                        except: pass
                        target.write(new_content)


def flush_cache():
    dlg = xbmcgui.Dialog()
    ln1 = 'Are you sure you want to '
    ln2 = 'delete the url cache?'
    ln3 = 'This will slow things down until rebuilt'
    yes = 'Keep'
    no = 'Delete'
    ret = dlg.yesno('Flush web cache', ln1, ln2, ln3, yes, no)
    if ret:
        if DB == 'mysql':
            sql = 'TRUNCATE TABLE url_cache'
            db = orm.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDR, buffered=True)
        else:
            sql = 'DELETE FROM url_cache'
            db = orm.connect(DB_DIR)
        cur = db.cursor()
        cur.execute(sql)
        db.commit()
        db.close()    

mode = _1CH.queries.get('mode', None)
section = _1CH.queries.get('section', '')
genre = _1CH.queries.get('genre', '')
letter = _1CH.queries.get('letter', '')
sort = _1CH.queries.get('sort', '')
url = _1CH.queries.get('url', '')
title = _1CH.queries.get('title', '')
img = _1CH.queries.get('img', '')
season = _1CH.queries.get('season', '')
query = _1CH.queries.get('query', '')
page = _1CH.queries.get('page', '')
imdbnum = _1CH.queries.get('imdbnum', '')
year = _1CH.queries.get('year', '')
video_type = _1CH.queries.get('video_type', '')
episode = _1CH.queries.get('episode', '')
season = _1CH.queries.get('season', '')
tvdbnum = _1CH.queries.get('tvdbnum', '')
alt_id = _1CH.queries.get('alt_id', '')
dialog = _1CH.queries.get('dialog', '')
day = _1CH.queries.get('day', '')

try: _1CH.log(_1CH.queries)
except: pass
try: _1CH.log(sys.argv)
except: pass

if mode == 'main':
    AddonMenu()
elif mode == 'GetSources':
    import urlresolver

    get_sources(url, title, img, year, imdbnum, dialog)
elif mode == 'PlaySource':
    import urlresolver

    PlaySource(url, title, img, year, imdbnum, video_type, season, episode)
elif mode == 'PlayTrailer':
    import urlresolver

    PlayTrailer(url)
elif mode == 'BrowseListMenu':
    BrowseListMenu(section)
elif mode == 'BrowseAlphabetMenu':
    BrowseAlphabetMenu(section)
elif mode == 'get_by_letter':
    get_by_letter(letter, section)
elif mode == 'BrowseByGenreMenu':
    BrowseByGenreMenu(section)
elif mode == 'GetFilteredResults':
    GetFilteredResults(section, genre, letter, sort, page)
elif mode == 'TVShowSeasonList':
    TVShowSeasonList(url, title, year, tvdbnum)
elif mode == 'TVShowEpisodeList':
    TVShowEpisodeList(title, season, imdbnum, tvdbnum)
elif mode == 'GetSearchQuery':
    GetSearchQuery(section)
elif mode == 'GetSearchQueryTag':
    GetSearchQueryTag(section)
elif mode == 'GetSearchQueryAdvanced':
    GetSearchQueryAdvanced(section)
elif mode == 'GetSearchQueryDesc':
    GetSearchQueryDesc(section)
elif mode == '7000':  # Enables Remote Search
    Search(section, query)
elif mode == 'browse_favorites':
    browse_favorites(section)
elif mode == 'browse_favorites_website':
    browse_favorites_website(section)
elif mode == 'SaveFav':
    save_favorite(section, title, url, img, year)
elif mode == 'DeleteFav':
    delete_favorite(section, title, url)
    xbmc.executebuiltin('Container.Refresh')
elif mode == 'ChangeWatched':
    ChangeWatched(imdb_id=imdbnum, video_type=video_type, name=title, season=season, episode=episode, year=year)
    xbmc.executebuiltin('Container.Refresh')
elif mode == '9988':  # Metahandler Settings
    print "Metahandler Settings"
    import metahandler

    metahandler.display_settings()
elif mode == 'ResolverSettings':
    import urlresolver

    urlresolver.display_settings()
elif mode == 'install_metapack':
    install_metapack(title)
elif mode == 'install_local_metapack':
    dialog = xbmcgui.Dialog()
    source = dialog.browse(1, 'Metapack', 'files', '.zip', False, False)
    install_local_zip(source)
elif mode == 'add_to_library':
    add_to_library(video_type, url, title, img, year, imdbnum)
    builtin = "XBMC.Notification(Add to Library,Added '%s' to library,2000)" % title
    xbmc.executebuiltin(builtin)
elif mode == 'update_subscriptions':
    update_subscriptions()
    if _1CH.get_setting('cleanup-subscriptions') == 'true':
        clean_up_subscriptions()
elif mode == 'add_subscription':
    add_subscription(url, title, img, year, imdbnum)
elif mode == 'manage_subscriptions':
    manage_subscriptions(day)
elif mode == 'cancel_subscription':
    cancel_subscription(url, title, img, year, imdbnum)
elif mode == 'clean_up_subscriptions':
    clean_up_subscriptions()
elif mode == 'subscriptions_day':
    cancel_subscription(url, title, img, year, imdbnum)
    add_subscription(url, title, img, year, imdbnum, day)
    xbmc.executebuiltin('Container.Refresh')
elif mode == 'PageSelect':
    pages = int(_1CH.queries['pages'])
    dialog = xbmcgui.Dialog()
    options = []
    for page in range(pages):
        label = 'Page %s' % str(page + 1)
        options.append(label)
    index = dialog.select('Skip to page', options)
    index += 1
    queries = {'mode': 'GetFilteredResults', 'section': section, 'genre': genre, 'letter': letter, 'sort': sort,
               'page': index}
    url = _1CH.build_plugin_url(queries)
    builtin = 'Container.Update(%s)' % url
    xbmc.executebuiltin(builtin)
elif mode == 'refresh_meta':
    refresh_meta(video_type, title, imdbnum, alt_id, year)
elif mode == 'flush_cache':
    flush_cache()
elif mode == 'migrateDB':
    migrate_to_mysql()
elif mode == 'migrateFavs':
    migrate_favs_to_web()
elif mode == 'Help':
    try: _1CH.log('Showing help popup')
    except: pass
    try: TextBox()
    except: pass
