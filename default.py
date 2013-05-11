'''
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
'''
import re
import os
import string
import sys
import urllib2
import urllib
import zipfile
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmc, xbmcvfs
import HTMLParser
import time

from t0mm0.common.addon import Addon
from t0mm0.common.net import Net
from metahandler import metahandlers
from metahandler import metacontainers
from operator import itemgetter, methodcaller

import metapacks
from utils import *

addon = Addon('plugin.video.1channel', sys.argv)
try:
    DB_NAME =      addon.get_setting('db_name')
    DB_USER =      addon.get_setting('db_user')
    DB_PASS =      addon.get_setting('db_pass')
    DB_ADDRESS = addon.get_setting('db_address')

    if  addon.get_setting('use_remote_db')=='true' and \
        DB_ADDRESS is not None and \
        DB_USER       is not None and \
        DB_PASS    is not None and \
        DB_NAME    is not None:
        import mysql.connector as database
        addon.log('Loading MySQL as DB engine')
        DB = 'mysql'
    else:
        addon.log('MySQL not enabled or not setup correctly')
        raise ValueError('MySQL not enabled or not setup correctly')
except:
    try: 
        from sqlite3 import dbapi2 as database
        addon.log('Loading sqlite3 as DB engine')
    except: 
        from pysqlite2 import dbapi2 as database
        addon.log('pysqlite2 as DB engine')
    DB = 'sqlite'
    db_dir = os.path.join(xbmc.translatePath("special://database"), 'onechannelcache.db')

META_ON = addon.get_setting('use-meta') == 'true'
FANART_ON = addon.get_setting('enable-fanart') == 'true'
USE_POSTERS = addon.get_setting('use-posters') == 'true'
POSTERS_FALLBACK = addon.get_setting('posters-fallback') == 'true'
THEME_LIST = ['mikey1234','Glossy_Black']
THEME = THEME_LIST[int(addon.get_setting('theme'))]
THEME_PATH = os.path.join(addon.get_path(), 'art', 'themes', THEME)
AUTO_WATCH = addon.get_setting('auto-watch') == 'true'

AZ_DIRECTORIES = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y', 'Z']
BASE_URL = addon.get_setting('domain')
USER_AGENT = 'User-Agent:Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.56'
GENRES = ['Action', 'Adventure', 'Animation', 'Biography', 'Comedy', 
          'Crime', 'Documentary', 'Drama', 'Family', 'Fantasy', 'Game-Show', 
          'History', 'Horror', 'Japanese', 'Korean', 'Music', 'Musical', 
          'Mystery', 'Reality-TV', 'Romance', 'Sci-Fi', 'Short', 'Sport', 
          'Talk-Show', 'Thriller', 'War', 'Western', 'Zombies']

prepare_zip = False
metaget=metahandlers.MetaData(preparezip=prepare_zip)

if not xbmcvfs.exists(addon.get_profile()):
     xbmcvfs.mkdirs(addon.get_profile())


def art(file):
    img = os.path.join(THEME_PATH, file)
    return img


def initDatabase():
    addon.log('Building 1channel Database')
    if DB == 'mysql':
        db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        cur = db.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS seasons (season INTEGER UNIQUE, contents TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS favorites (type VARCHAR(10), name TEXT, url VARCHAR(255) UNIQUE, year VARCHAR(10))')
        cur.execute('CREATE TABLE IF NOT EXISTS subscriptions (url VARCHAR(255) UNIQUE, title TEXT, img TEXT, year TEXT, imdbnum TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS bookmarks (video_type VARCHAR(10), title VARCHAR(255), season INTEGER, episode INTEGER, year VARCHAR(10), bookmark VARCHAR(10))')
        cur.execute('CREATE TABLE IF NOT EXISTS url_cache (url VARCHAR(255), response TEXT, timestamp TEXT)')

        try: cur.execute('CREATE UNIQUE INDEX unique_bmk ON bookmarks (video_type, title, season, episode, year)')
        except: pass

    else:
        if not xbmcvfs.exists(os.path.dirname(db_dir)):
            xbmcvfs.mkdirs(os.path.dirname(db_dir))
        db = database.connect(db_dir)
        db.execute('CREATE TABLE IF NOT EXISTS seasons (season UNIQUE, contents)')
        db.execute('CREATE TABLE IF NOT EXISTS favorites (type, name, url, year)')
        db.execute('CREATE TABLE IF NOT EXISTS subscriptions (url, title, img, year, imdbnum)')
        db.execute('CREATE TABLE IF NOT EXISTS bookmarks (video_type, title, season, episode, year, bookmark)')
        db.execute('CREATE TABLE IF NOT EXISTS url_cache (url UNIQUE, response, timestamp)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_fav ON favorites (name, url)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_sub ON subscriptions (url, title, year)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_bmk ON bookmarks (video_type, title, season, episode, year)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_url ON url_cache (url)')
    db.commit()
    db.close()


def SaveFav(fav_type, name, url, img, year):
    addon.log('Saving Favorite type: %s name: %s url: %s img: %s year: %s' %(fav_type, name, url, img, year))
    if fav_type != 'tv': fav_type = 'movie'
    if website_is_integrated():
        addon.log('Saving favorite to website')
        id = re.search('.+(?:watch|tv)-([\d]+)-', url)
        if id:
            save_url = "%s/addtofavs.php?id=%s&whattodo=add"
            save_url = save_url %(BASE_URL, id.group(1))
            print save_url
            net = Net()
            cookiejar = addon.get_profile()
            cookiejar = os.path.join(cookiejar,'cookies')
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
                addon.log('Unable to confirm success')
                addon.log(html)
    else:
        statement  = 'INSERT INTO favorites (type, name, url, year) VALUES (%s,%s,%s,%s)'
        if DB == 'mysql':
            db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        else:
            db = database.connect( db_dir )
            statement = statement.replace("%s","?")
        cursor = db.cursor()
        try: 
            cursor.execute(statement, (fav_type, urllib.unquote_plus(unicode(name,'latin1')), url, year))
            builtin = 'XBMC.Notification(Save Favorite,Added to Favorites,2000)'
            xbmc.executebuiltin(builtin)
        except database.IntegrityError: 
            builtin = 'XBMC.Notification(Save Favorite,Item already in Favorites,2000)'
            xbmc.executebuiltin(builtin)
        db.commit()
        db.close()


def DeleteFav(fav_type, name, url): #7777
    if fav_type != 'tv': fav_type = 'movie'
    addon.log( 'Deleting Fav: %s\n %s\n %s\n' % (fav_type,name,url))
    if website_is_integrated():
        addon.log('Deleting favorite from website')
        id = re.search('.+(?:watch|tv)-([\d]+)-', url)
        if id:
            del_url = "%s/addtofavs.php?id=%s&whattodo=delete"
            del_url = del_url %(BASE_URL, id.group(1))
            print del_url
            net = Net()
            cookiejar = addon.get_profile()
            cookiejar = os.path.join(cookiejar,'cookies')
            net.set_cookies(cookiejar)
            html = net.http_GET(del_url).content
            net.save_cookies(cookiejar)

    else:
        sql_del = 'DELETE FROM favorites WHERE type=%s AND name=%s AND url=%s'
        if DB == 'mysql':
            db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        else:
            db = database.connect( db_dir )
            sql_del = sql_del.replace('%s','?')
        cursor = db.cursor()
        cursor.execute(sql_del, (fav_type, name, url))
        db.commit()
        db.close()


def GetURL(url, params=None, referrer=BASE_URL, silent=False, cache_limit=8):
    addon.log('Fetching URL: %s' % url)
    if DB == 'mysql': db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
    else: db = database.connect( db_dir )
    cur = db.cursor()
    now = time.time()
    limit = 60*60*cache_limit
    cur.execute('SELECT * FROM url_cache WHERE url = "%s"' %url)
    cached = cur.fetchone()
    if cached:
        created = float(cached[2])
        age = now - created
        if age < limit:
            addon.log('Returning cached result for %s' %url)
            db.close()
            return cached[1].encode('utf-8')
        else: addon.log('Cache too old. Requesting from internet')
    else: addon.log('No cached response. Requesting from internet')

    if params: req = urllib2.Request(url, params)
    else: req = urllib2.Request(url)

    host = re.sub('http://', '', BASE_URL)
    req.add_header('User-Agent', USER_AGENT)
    req.add_header('Host', host)
    if referrer: req.add_header('Referer', referrer)
    
    try:
        response = urllib2.urlopen(req, timeout=10)
        body = response.read()
        body = unicode(body,'iso-8859-1')
        h = HTMLParser.HTMLParser()
        body = h.unescape(body)
    except:
        if not silent:
            dialog = xbmcgui.Dialog()
            dialog.ok("Connection failed", "Failed to connect to url", url)
            print "1Channel: Failed to connect to URL %s" % url
        return ''

    response.close()

    sql = "REPLACE INTO url_cache (url,response,timestamp) VALUES(%s,%s,%s)"
    if DB == 'sqlite':
        sql = 'INSERT OR ' + sql.replace('%s','?')
    cur.execute(sql, (url, body, now))
    db.commit()
    db.close()
    return body.encode('utf-8')


def GetSources(url, title, img, year, imdbnum, dialog): #10
    url      = urllib.unquote(url)
    addon.log('Getting sources from: %s' % url)

    match = re.search('tv-\d{1,10}-(.*)/season-(\d{1,4})-episode-(\d{1,4})', url, re.IGNORECASE | re.DOTALL)
    if match:
        video_type = 'episode'
        season  = int(match.group(2))
        episode = int(match.group(3))
    else:
        video_type = 'movie'
        season  = ''
        episode = ''

    net = Net()
    cookiejar = addon.get_profile()
    cookiejar = os.path.join(cookiejar,'cookies')
    net.set_cookies(cookiejar)
    html = net.http_GET(BASE_URL + url).content
    net.save_cookies(cookiejar)
    adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
    r = re.search(adultregex, html, re.DOTALL)
    if r:
        addon.log('Adult content url detected')
        adulturl = BASE_URL + r.group(1)
        headers = {'Referer': url}
        net.set_cookies(cookiejar)
        html = net.http_GET(adulturl, headers=headers).content
        net.save_cookies(cookiejar)

    sources = []
    list = []
    if META_ON and video_type=='movie' and not imdbnum:
        imdbregex = 'mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7})"'
        r = re.search(imdbregex, html)
        if r:
            imdbnum = r.group(1)
            metaget.update_meta('movie',title,imdb_id='',
                                new_imdb_id=imdbnum,year=year)

    if addon.get_setting('sorting-enabled')=='true':
        sorts = [None,'host','verified','quality','views','multi-part']
        if int(addon.get_setting('first-sort')) > 0:
            this_sort = sorts[int(addon.get_setting('first-sort'))]
            if addon.get_setting('first-sort-reversed')=='true':
                this_sort = '-%s' %this_sort
            sorting = [this_sort]
            if int(addon.get_setting('second-sort')) > 0:
                this_sort = sorts[int(addon.get_setting('second-sort'))]
                if addon.get_setting('second-sort-reversed')=='true':
                    this_sort = '-%s' %this_sort
                sorting.append(this_sort)
                if int(addon.get_setting('third-sort')) > 0:
                    this_sort = sorts[int(addon.get_setting('third-sort'))]
                    if addon.get_setting('third-sort-reversed')=='true':
                        this_sort = '-%s' %this_sort
                    sorting.append(this_sort)
                    if int(addon.get_setting('fourth-sort')) > 0:
                        this_sort = sorts[int(addon.get_setting('fourth-sort'))]
                        if addon.get_setting('fourth-sort-reversed')=='true':
                            this_sort = '-%s' %this_sort
                        sorting.append(this_sort)
                        if int(addon.get_setting('fifth-sort')) > 0:
                            this_sort = sorts[int(addon.get_setting('fifth-sort'))]
                            if addon.get_setting('fifth-sort-reversed')=='true':
                                this_sort = '-%s' %this_sort
                            sorting.append(this_sort)
    else: sorting = []

    for version in re.finditer('<table[^\n]+?class="movie_version(?: movie_version_alt)?">(.*?)</table>',
                                html, re.DOTALL|re.IGNORECASE):
        for s in re.finditer('quality_(?!sponsored|unknown)(.*?)></span>.*?'+
                              'url=(.*?)&(?:amp;)?domain=(.*?)&(?:amp;)?(.*?)'+
                             '"version_veiws"> ([\d]+) views</',
                             version.group(1), re.DOTALL):
            q, url, host, parts, views = s.groups()
            
            item = {}
            item['host'] = host.decode('base-64')
            item['url'] = url.decode('base-64')
            if urlresolver.HostedMediaFile(item['url']).valid_url():
                item['verified'] = s.group(0).find('star.gif') > -1
                item['quality'] = q.upper()
                item['views'] = int(views)
                r = '\[<a href=".*?url=(.*?)&(?:amp;)?.*?".*?>(part [0-9]*)</a>\]'
                additional_parts = re.findall(r, parts, re.DOTALL|re.IGNORECASE)
                if additional_parts:
                    item['multi-part'] = True
                    item['parts'] = [part[0].decode('base-64') for part in additional_parts]
                else: item['multi-part'] = False
                list.append(item)

            if sorting: list = multikeysort(list, sorting, functions={'host':rank_host})
    if not list: addon.show_ok_dialog(['No sources were found for this item'], title='1Channel')
    if dialog and addon.get_setting('auto-play')=='false': #we're comming from a .strm file and can't create a directory so we have to pop a 
        sources = []                                       #dialog if auto-play isn't on
        img = xbmc.getInfoImage('ListItem.Thumb')
        for item in list:
            try:
                label = format_label_source(item)
                hosted_media = urlresolver.HostedMediaFile(url=item['url'], title=label)
                sources.append(hosted_media)
                if item['multi-part']:
                    partnum = 2
                    for part in item['parts']:
                        label = format_label_source_parts(item, partnum)
                        hosted_media = urlresolver.HostedMediaFile(url=item['parts'][partnum-2], title=label)
                        sources.append(hosted_media)
                        partnum += 1
            except: addon.log('Error while trying to resolve %s' % url)
        source = urlresolver.choose_source(sources).get_url()
        PlaySource(source, title, img, year, imdbnum, video_type, season, episode, strm=True)
    else:
        try:
            if addon.get_setting('auto-play')=='false': raise #skips the next line and goes into the else clause
            dlg = xbmcgui.DialogProgress()
            line1 = 'Trying Sources...'
            dlg.create('1Channel', line1)
            total = len(list)
            count = 1
            success = False
            while not (success or dlg.iscanceled() or xbmc.abortRequested):
                for source in list:
                    if dlg.iscanceled(): return
                    percent = int((count*100)/total)
                    label = format_label_source(source)
                    dlg.update(percent, line1, label)
                    try:
                        PlaySource(source['url'], title, img, year, imdbnum, video_type, season, episode)
                        dlg.close()
                        success = True
                        break #Playback was successful, break out of the loop
                    except Exception, e:  #Playback failed, try the next one
                        dlg.update(percent, line1, label, str(e))
                        addon.log('%s source failed. Trying next source...' %source['host']) 
                        addon.log(str(e))
                        count += 1
        except:
            for item in list:
                addon.log(item)
                label = format_label_source(item)
                addon.add_directory({'mode':'PlaySource', 'url':item['url'], 'title':title,
                                     'img':img, 'year':year, 'imdbnum':imdbnum,
                                     'video_type':video_type, 'season':season, 'episode':episode},
                infolabels={'title':label}, is_folder=False, img=img, fanart=art('fanart.png'))
                if item['multi-part']:
                    partnum = 2
                    for part in item['parts']:
                        label = format_label_source_parts(item, partnum)
                        partnum += 1
                        addon.add_directory({'mode':'PlaySource', 'url':part, 'title':title,
                                             'img':img, 'year':year, 'imdbnum':imdbnum,
                                             'video_type':video_type, 'season':season, 'episode':episode},
                        infolabels={'title':label}, is_folder=False, img=img, fanart=art('fanart.png'))
                
            addon.end_of_directory()


def PlaySource(url, title, img, year, imdbnum, video_type, season, episode, strm=False):
    addon.log('Attempting to play url: %s' % url)
    stream_url = urlresolver.HostedMediaFile(url=url).resolve()
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
                meta = metaget.get_episode_meta(title,imdbnum,season,episode)
                meta['TVShowTitle'] = title
                meta['title'] = format_tvshow_episode(meta)
                if not strm:
                    try: img = meta['cover_url']
                    except: img = ''
                listitem = xbmcgui.ListItem(title, iconImage=img, thumbnailImage=img)
                listitem.setInfo(type="Video", infoLabels=meta)
                listitem.setProperty('IsPlayable', 'true')
            except: addon.log('Failed to get metadata for Title: %s IMDB: %s Season: %s Episode %s' %(title,imdbnum,season,episode))
        elif video_type == 'movie':
            try:
                meta = metaget.get_meta('movie', title, year=year)
                meta['title'] = format_label_movie(meta)
                if not strm:
                    try: img = meta['cover_url']
                    except: img = ''
                listitem.setInfo(type="Video", infoLabels=meta)
                listitem.setProperty('IsPlayable', 'true')
            except: addon.log('Failed to get metadata for Title: %s IMDB: %s Season: %s Episode %s' %(title,imdbnum,season,episode))

    listitem.setPath(stream_url)
    xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, listitem)

def TrackProgress(player):
    while player._playbackLock:
        if player.isPlayingVideo():
            player._trackPosition()
            xbmc.sleep(250)

def ChangeWatched(imdb_id, video_type, name, season, episode, year='', watched='', refresh=False):
    metaget=metahandlers.MetaData(preparezip=prepare_zip)
    metaget.change_watched(video_type, name, imdb_id, season=season, episode=episode, year=year, watched=watched)
    if refresh:
        xbmc.executebuiltin("XBMC.Container.Refresh")

def PlayTrailer(url): #250
    url = url.decode('base-64')
    addon.log('Attempting to resolve and play trailer at %s' % url)
    sources = []
    hosted_media = urlresolver.HostedMediaFile(url=url)
    sources.append(hosted_media)
    source = urlresolver.choose_source(sources)
    if source: stream_url = source.resolve()
    else: stream_url = ''
    xbmc.Player().play(stream_url)


def GetSearchQuery(section):
    last_search = addon.load_data('search')
    if not last_search: last_search = ''
    keyboard = xbmc.Keyboard()
    if section == 'tv': keyboard.setHeading('Search TV Shows')
    else: keyboard.setHeading('Search Movies')
    keyboard.setDefault(last_search)
    keyboard.doModal()
    if (keyboard.isConfirmed()):
        search_text = keyboard.getText()
        addon.save_data('search',search_text)
        if search_text.startswith('!#'):
            if search_text == '!#create metapacks': create_meta_packs()
            if search_text == '!#repair meta'      : repair_missing_images()
            if search_text == '!#install all meta': install_all_meta()
            if search_text.startswith('!#sql'):
                if DB == 'mysql': db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
                else: db = database.connect( db_dir )
                db.execute(search_text[5:])
                db.commit()
                db.close()
        else:
            Search(section, keyboard.getText())
    else:
        BrowseListMenu(section)


def Search(section, query):
    html = GetURL(BASE_URL, cache_limit=0)
    r = re.search('input type="hidden" name="key" value="([0-9a-f]*)"', html).group(1)
    search_url = BASE_URL + '/index.php?search_keywords='
    search_url += urllib.quote_plus(query)
    search_url += '&key=' + r
    if section == 'tv':
        setView('tvshows', 'tvshows-view')
        search_url += '&search_section=2'
        nextmode = 'TVShowSeasonList'
        video_type = 'tvshow'
        folder = True
        if DB == 'mysql': db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        else: db = database.connect( db_dir )
        cur = db.cursor()
        cur.execute('SELECT url FROM subscriptions')
        subscriptions = cur.fetchall()
        db.close()
        subs = [row[0] for row in subscriptions]

    else:
        setView('movies', 'movies-view')
        nextmode = 'GetSources'
        video_type = 'movie'
        folder = addon.get_setting('auto-play')=='false'
        subs = []

    html = '> >> <'
    page = 0

    while html.find('> >> <') > -1 and page < 10:
        page += 1
        if page > 1: pageurl = '%s&page=%s' %(search_url,page)
        else: pageurl = search_url
        html = GetURL(pageurl, cache_limit=0)

        r = re.search('number_movies_result">([0-9,]+)', html)
        if r: total = int(r.group(1).replace(',', ''))
        else: total = 0

        r = 'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
        regex = re.finditer(r, html, re.DOTALL)
        resurls = []
        for s in regex:
            resurl,title,year,thumb = s.groups()
            if resurl not in resurls:
                resurls.append(resurl)

                li = build_listitem(video_type, title, year, img, resurl, subs=subs)
                imdb = li.getProperty('imdb')
                thumb = li.getProperty('img')

                queries = {'mode':nextmode, 'title':title, 'url':resurl,
                           'img':thumb, 'imdbnum':imdb,
                           'video_type':video_type, 'year':year}
                li_url = addon.build_plugin_url(queries)
                xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, li, 
                                            isFolder=folder, totalItems=total)    
                # addon.add_directory({'mode':nextmode, 'title':title, 'url':BASE_URL + resurl, 'img':thumb, 'imdbnum':meta['imdb_id'], 'video_type':video_type, 'year':year},
                                    # meta, cm, True, img, fanart, total_items=total, is_folder=folder)            
    addon.end_of_directory()


def AddonMenu():  #homescreen
    addon.log('Main Menu')
    if has_upgraded():
        addon.log('Showing update popup')
        popup = TextBox()
        adn = xbmcaddon.Addon('plugin.video.1channel')
        upgrade_subs_db()
        fix_existing_strms()
        adn.setSetting('old_version', addon.get_version())
    initDatabase()
    addon.add_directory({'mode': 'BrowseListMenu', 'section': ''},   {'title':  'Movies'}, img=art('movies.png'), fanart=art('fanart.png'))
    addon.add_directory({'mode': 'BrowseListMenu', 'section': 'tv'}, {'title':  'TV shows'}, img=art('television.png'), fanart=art('fanart.png'))
    addon.add_directory({'mode': 'ResolverSettings'},   {'title':  'Resolver Settings'}, img=art('settings.png'), fanart=art('fanart.png'))
    addon.add_directory({'mode': 'Help'},   {'title': 'Help'}, img=art('help.png'), fanart=art('fanart.png'))
    # addon.add_directory({'mode': 'test'},   {'title':  'Test'}, img=art('settings.png'), fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def BrowseListMenu(section=None): #500
    addon.log('Browse Options')
    print 'section: %s' %section
    addon.add_directory({'mode': 'BrowseAlphabetMenu', 'section': section},   {'title':  'A-Z'}, img=art('atoz.png'), fanart=art('fanart.png'))
    addon.add_directory({'mode': 'GetSearchQuery', 'section': section},   {'title':  'Search'}, img=art('search.png'), fanart=art('fanart.png'))
    if website_is_integrated():
        addon.add_directory({'mode': 'BrowseFavorites_Website', 'section': section},   {'title':  'Website Favourites'}, img=art('favourites.png'), fanart=art('fanart.png'))
    else:
        addon.add_directory({'mode': 'BrowseFavorites', 'section': section},   {'title':  'Favourites'}, img=art('favourites.png'), fanart=art('fanart.png'))
    if section=='tv':
        addon.add_directory({'mode': 'ManageSubscriptions'}, {'title':  'Subscriptions'}, img=art('subscriptions.png'), fanart=art('fanart.png'))
    addon.add_directory({'mode': 'BrowseByGenreMenu', 'section': section},   {'title':  'Genres'}, img=art('genres.png'), fanart=art('fanart.png'))
    addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'featured'},   {'title':  'Featured'}, img=art('featured.png'), fanart=art('fanart.png'))
    addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'views'},   {'title':  'Most Popular'}, img=art('most_popular.png'), fanart=art('fanart.png'))
    addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'ratings'},   {'title':  'Highly rated'}, img=art('highly_rated.png'), fanart=art('fanart.png'))
    addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'release'},   {'title':  'Date released'}, img=art('date_released.png'), fanart=art('fanart.png'))
    addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'date'},   {'title':  'Date added'}, img=art('date_added.png'), fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def BrowseAlphabetMenu(section=None): #1000
    addon.log('Browse by alphabet screen')
    addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort':'alphabet', 'letter':'123'},   {'title':  '#123'}, img=art('123.png'), fanart=art('fanart.png'))
    # queries = {'mode': 'GetByLetter', 'video_type': section, 'letter': '#'}
    # addon.add_directory(queries, {'title':  '#123'}, img=art('#.png'), fanart=art('fanart.png'))
    for character in AZ_DIRECTORIES:
        addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort':'alphabet', 'letter': character},   {'title':  character}, img=art(character+'.png'), fanart=art('fanart.png'))
        # queries = {'mode': 'GetByLetter', 'section': section, 'letter': character}
        # addon.add_directory(queries, {'title':  character}, img=art(character+'.png'), fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def BrowseByGenreMenu(section=None, letter=None): #2000
    print 'Browse by genres screen'
    for genre in GENRES:
        addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort':'', 'genre': genre},   {'title':  genre})
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def add_contextsearchmenu(title, type):
    contextmenuitems = []
    if os.path.exists(xbmc.translatePath("special://home/addons/")+'plugin.video.icefilms'):
        contextmenuitems.append(('Search Icefilms', 'XBMC.Container.Update(%s?mode=555&url=%s&search=%s&nextPage=%s)' %('plugin://plugin.video.icefilms/','http://www.icefilms.info/',title,'1')))
    if os.path.exists(xbmc.translatePath("special://home/addons/")+'plugin.video.tubeplus'):
        if type == 'tv':
            section = 'tv-shows'
        else:
            section = 'movies'
        contextmenuitems.append(('Search tubeplus', 'XBMC.Container.Update(%s?mode=Search&section=%s&query=%s)' %('plugin://plugin.video.tubeplus/',section,title)))
    if os.path.exists(xbmc.translatePath("special://home/addons/")+'plugin.video.tvlinks'):
        if type == 'tv':
            contextmenuitems.append(('Search tvlinks', 'XBMC.Container.Update(%s?mode=Search&query=%s)' %('plugin://plugin.video.tvlinks/',title)))
    if os.path.exists(xbmc.translatePath("special://home/addons/")+'plugin.video.solarmovie'):
        if type == 'tv':
            section = 'tv-shows'
        else:
            section = 'movies'
        contextmenuitems.append(('Search solarmovie', 'XBMC.Container.Update(%s?mode=Search&section=%s&query=%s)' %('plugin://plugin.video.solarmovie/',section,title)))

    return contextmenuitems


def GetFilteredResults(section=None, genre=None, letter=None, sort='alphabet', page=None): #3000
    addon.log('Filtered results for Section: %s Genre: %s Letter: %s Sort: %s Page: %s' %(section, genre, letter, sort, page))

    pageurl = BASE_URL + '/?'
    if section == 'tv': pageurl += 'tv'
    if genre  :    pageurl += '&genre='  + genre
    if letter :    pageurl += '&letter=' + letter
    if sort   :    pageurl += '&sort='   + sort
    if page      : pageurl += '&page=%s' % page

    if page: page = int(page) + 1
    else: page = 2

    if section == 'tv':
        nextmode = 'TVShowSeasonList'
        video_type = 'tvshow'
        folder = True
        if DB == 'mysql': db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        else: db = database.connect( db_dir )
        cur = db.cursor()
        cur.execute('SELECT url FROM subscriptions')
        subscriptions = cur.fetchall()
        db.close()
        subs = [row[0] for row in subscriptions]

    else:
        nextmode = 'GetSources'
        section = 'movie'
        video_type = 'movie'
        folder = addon.get_setting('auto-play')=='false'
        subs = []

    html = GetURL(pageurl)

    r = re.search('number_movies_result">([0-9,]+)', html)
    if r: total = int(r.group(1).replace(',', ''))
    else: total = 0
    total_pages = total/24
    total = min(total,24)

    r = 'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
    regex = re.finditer(r, html, re.DOTALL)
    resurls = []
    for s in regex:
        resurl,title,year,thumb = s.groups()
        if resurl not in resurls:
            resurls.append(resurl)
            li = build_listitem(video_type, title, year, img, resurl, subs=subs)
            imdb = li.getProperty('imdb')
            imdb = li.getProperty('img')
            li.setProperty('IsPlayable', 'true')
            queries = {'mode':nextmode, 'title':title, 'url':resurl,
                       'img':thumb, 'imdbnum':imdb,
                       'video_type':video_type, 'year':year}
            li_url = addon.build_plugin_url(queries)
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, li, 
                                        isFolder=folder, totalItems=total)    

    if html.find('> >> <') > -1:
        label = 'Skip to Page...'
        command = addon.build_plugin_url({'mode':'PageSelect', 'pages':total_pages, 'section':section, 'genre':genre, 'letter':letter, 'sort':sort})
        command = 'RunPlugin(%s)' %command
        cm = [(label, command)]
        meta = {'title':'Next Page >>'}
        addon.add_directory({'mode':'GetFilteredResults', 'section':section, 'genre':genre, 'letter':letter, 'sort':sort, 'page':page},
                            meta, cm, True, art('nextpage.png'), art('fanart.png'), is_folder=True)

    if   video_type == 'tvshow': setView('tvshows', 'tvshows-view')
    elif video_type == 'movie' : setView('movies', 'movies-view')
    addon.end_of_directory()


def TVShowSeasonList(url, title, year, old_imdb, old_tvdb=''): #4000
    addon.log('Seasons for TV Show %s' % url)
    net = Net()
    cookiejar = addon.get_profile()
    cookiejar = os.path.join(cookiejar,'cookies')
    net.set_cookies(cookiejar)
    html = net.http_GET(BASE_URL + url).content
    net.save_cookies(cookiejar)
    adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
    r = re.search(adultregex, html, re.DOTALL)
    if r:
        addon.log('Adult content url detected')
        adulturl = BASE_URL + r.group(1)
        headers = {'Referer': url}
        net.set_cookies(cookiejar)
        html = net.http_GET(adulturl, headers=headers).content
        net.save_cookies(cookiejar)


    if DB == 'mysql':
        sql = 'INSERT INTO seasons(season,contents) VALUES(%s,%s) ON DUPLICATE KEY UPDATE contents = VALUES(contents)'
        db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True, autocommit=True)
    else:
        sql = 'INSERT or REPLACE into seasons (season,contents) VALUES(?,?)'
        db = database.connect( db_dir )

    try:
        new_imdb = re.search('mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7})"', html).group(1)
    except: new_imdb = ''
    seasons = re.search('tv_container(.+?)<div class="clearer', html, re.DOTALL)
    if not seasons: addon.log_error('couldn\'t find seasons')
    else:
        season_container = seasons.group(1)
        season_nums = re.compile('<a href=".+?">Season ([0-9]{1,2})').findall(season_container)
        fanart = ''
        imdbnum = old_imdb
        if META_ON: 
            if not old_imdb and new_imdb:
                addon.log('Imdb ID not recieved from title search, updating with new id of %s' % new_imdb)
                try:
                    addon.log('Title: %s Old IMDB: %s Old TVDB: %s New IMDB %s Year: %s'%(title,old_imdb,old_tvdb,new_imdb, year))
                    metaget.update_meta('tvshow', title, old_imdb, old_tvdb, new_imdb)
                except: 
                    addon.log('Error while trying to update metadata with:')
                    addon.log('Title: %s Old IMDB: %s Old TVDB: %s New IMDB %s Year: %s'%(title,old_imdb,old_tvdb,new_imdb, year))
                imdbnum = new_imdb

            season_meta = metaget.get_seasons(title, imdbnum, season_nums)

        seasonList = season_container.split('<h2>')
        num = 0
        cur = db.cursor()
        for eplist in seasonList:
            temp = {}
            temp['cover_url'] = ''
            r = re.search('<a.+?>Season (\d+)</a>', eplist)
            if r:
                number = r.group(1)

                if META_ON:
                    temp = season_meta[num]
                    if FANART_ON:
                        try: fanart = temp['backdrop_url']
                        except: pass

                label = 'Season %s' %number
                temp['title'] = label
                cur.execute(sql, (number,eplist))
                
                listitem = xbmcgui.ListItem(label, iconImage=temp['cover_url'],
                                            thumbnailImage=temp['cover_url'])
                listitem.setInfo('video', temp)
                listitem.setProperty('fanart_image', fanart)
                queries = {'mode':'TVShowEpisodeList', 'season':number,
                           'imdbnum':imdbnum, 'title':title}
                li_url = addon.build_plugin_url(queries)
                xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem,
                                        isFolder=True, 
                                        totalItems=len(seasonList))

                num += 1
        cur.close()
        db.commit()
        xbmcplugin.endOfDirectory(int(sys.argv[1]))
        setView('seasons', 'seasons-view')
        db.close()


def TVShowEpisodeList(ShowTitle, season, imdbnum, tvdbnum): #5000
    sql = 'SELECT contents FROM seasons WHERE season=?'
    if DB == 'mysql':
        sql = sql.replace('?','%s')
        db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
    else: db = database.connect( db_dir )
    cur = db.cursor()
    cur.execute(sql, (season,))
    eplist = cur.fetchone()[0]
    db.close()
    r = '"tv_episode_item".+?href="(.+?)">(.*?)</a>'
    episodes = re.finditer(r, eplist, re.DOTALL)
    folder = addon.get_setting('auto-play')=='false'
    for ep in episodes:
        epurl, eptitle = ep.groups()
        meta = {}
        eptitle = re.sub('<[^<]+?>', '', eptitle.strip())
        eptitle = re.sub('\s\s+' , ' ', eptitle)

        season = int(re.search('/season-([0-9]{1,4})-', epurl).group(1))
        epnum = int(re.search('-episode-([0-9]{1,3})', epurl).group(1))

        queries = {'mode':'GetSources', 'url':epurl, 'imdbnum':imdbnum,
                   'title':ShowTitle, 'img':img}
        li_url = addon.build_plugin_url(queries)
        listitem =  build_listitem('episode', ShowTitle, year, img, epurl, imdbnum, season, epnum)
        listitem.setProperty('IsPlayable', 'true')

        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem,
                                        isFolder=folder)

    setView('episodes', 'episodes-view')
    addon.end_of_directory()


def BrowseFavorites(section):
    sql = 'SELECT type, name, url, year FROM favorites WHERE type = ? ORDER BY name'
    if DB == 'mysql':
        db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        sql = sql.replace('?','%s')
    else: db = database.connect( db_dir )
    cur = db.cursor()
    if section == 'tv':  setView('tvshows', 'tvshows-view')
    else: setView('movies', 'movies-view')
    if section == 'tv':
        nextmode = 'TVShowSeasonList'
        video_type = 'tvshow'
        folder = True
        cur.execute('SELECT url FROM subscriptions')
        subscriptions = cur.fetchall()
        subs = [row[0] for row in subscriptions]
    else: 
        nextmode = 'GetSources'
        video_type      = 'movie'
        section = 'movie'
        subs = []
        folder   = addon.get_setting('auto-play')=='false'

    cur.execute(sql, (section,))
    favs = cur.fetchall()
    for row in favs:
        title      = row[1]
        favurl      = row[2]
        year      = row[3]
        img = ''
        fanart = ''

        remfavstring = 'RunScript(plugin.video.1channel,%s,?mode=DeleteFav&section=%s&title=%s&year=%s&url=%s)' %(sys.argv[1],video_type,title,year,favurl)
        cm = [('Remove from Favorites', remfavstring)]

        li = build_listitem(video_type, title, year, img, favurl, extra_cms=cm, subs=subs)
        img = li.getProperty('img')
        queries = {'mode':nextmode, 'title':title, 'url':favurl,
                   'img':img, 'video_type':video_type}
        li_url = addon.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, li, 
                                    isFolder=folder)  

    xbmcplugin.endOfDirectory(int(sys.argv[1]))
    db.close()

def BrowseFavorites_Website(section):
    sql = 'SELECT count(*) FROM favorites'
    if DB == 'mysql':
        db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        sql = sql.replace('?','%s')
    else: db = database.connect( db_dir )
    cur = db.cursor()
    local_favs = cur.execute(sql).fetchall()

    if local_favs:
        addon.add_item({'mode':'migrateFavs'}, {'title':'Upload Local Favorites'})
    
    user   = addon.get_setting('username')
    passwd = addon.get_setting('passwd')
    if not section: section = 'movies'
    url = '/profile.php?user=%s&fav&show=%s'
    url = BASE_URL + url %(user,section)
    cookiejar = addon.get_profile()
    cookiejar = os.path.join(cookiejar,'cookies')
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
            db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        else: db = database.connect( db_dir )
        cur = db.cursor()
        cur.execute('SELECT url FROM subscriptions')
        subs = cur.fetchall()
    else:
        video_type = 'movie'
        nextmode = 'GetSources'
        folder = addon.get_setting('auto-play')=='false'
        subs = []

    pattern = '''<div class="index_item"> <a href="(.+?)"><img src="(.+?(\d{4})\.jpg)" width="150" border="0">.+?<td align="center"><a href=".+?">(.+?)</a></td>.+?class="favs_deleted"><a href=["'](.+?)["'] ref=["']delete_fav["']'''
    regex = re.compile(pattern, re.IGNORECASE|re.DOTALL)
    for item in regex.finditer(html):
        link, img, year, title, delete = item.groups()
        
        runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'DeleteFav', 'section':section, 'title':title, 'url':link, 'year':year})
        cm = [('Delete Favorite', runstring)]

        li = build_listitem(video_type, title, year, img, link, extra_cms=cm, subs=subs)
        img = li.getProperty('img')
        queries = {'mode':nextmode, 'title':title, 'url':link,
                   'img':img, 'video_type':video_type}
        li_url = addon.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, li, 
                                    isFolder=folder)
    addon.end_of_directory()

def migrate_favs_to_web():
    sql = 'SELECT type, name, url, year FROM favorites ORDER BY name'
    if DB == 'mysql':
        db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        sql = sql.replace('?','%s')
    else: db = database.connect( db_dir )
    cur = db.cursor()
    cur.execute(sql)
    all_favs = cur.fetchall()
    progress = xbmcgui.DialogProgress()
    ln1 = 'Uploading your favorites to www.1channel.ch...'
    ret = progress.create('Uploading Favorites', ln1)
    net = Net()
    cookiejar = addon.get_profile()
    cookiejar = os.path.join(cookiejar,'cookies')
    failures = []
    for fav in all_favs:
        if progress.iscanceled(): return
        title = fav[1]
        favurl = fav[2]
        progress.update(0, ln1, 'Adding %s' %title)
        try:
            id = re.search('.+(?:watch|tv)-([\d]+)-', favurl)
            if id:
                save_url = "%s/addtofavs.php?id=%s&whattodo=add" %BASE_URL
                save_url = save_url % id.group(1)
                addon.log(save_url)
                net.set_cookies(cookiejar)
                html = net.http_GET(save_url).content
                net.save_cookies(cookiejar)
                progress.update(0, ln1, 'Adding %s' %title, 'Success')
                addon.log('%s added successfully' %title)
        except Exception, e:
            addon.log(e)
            failures.append((title, favurl))
    progress.close()
    dialog = xbmcgui.Dialog()
    ln1 = 'Do you want to remove the successful'
    ln2 = 'uploads from local favorites?'
    ln3 = 'THIS CANNOT BE UNDONE'
    yes = 'Keep'
    no  = 'Delete'
    ret = dialog.yesno('Migration Complete', ln1, ln2, ln3, yes, no)
    # failures = [('title1','url1'), ('title2','url2'), ('title3','url3'), ('title4','url4'), ('title5','url5'), ('title6','url6'), ('title7','url7')]
    if ret:
        if failures:
            params = ', '.join('%s' if DB=='mysql' else '?' for item in failures)
            sql_delete = 'DELETE FROM favorites WHERE url NOT IN (SELECT url FROM favorites WHERE url IN (%s))'
            sql_delete = sql_delete % params
            addon.log(sql_delete)
            urls = [item[1] for item in failures]
            addon.log(urls)
            # cur.execute(sql_delete, failures)
        else:
            cur.execute('DELETE FROM favorites')
            
        
def GetByLetter(letter, section):
    addon.log('Showing results for letter: %s' %letter)
    if section == 'tv':
        url = '%s/alltvshows.php' %BASE_URL
        video_type = 'tvshow'
        nextmode = 'TVShowSeasonList'
        folder = True
        if DB == 'mysql': db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        else: db = database.connect( db_dir )
        cur = db.cursor()
        cur.execute('SELECT url FROM subscriptions')
        subs = cur.fetchall()
    else:
        url = '%s/allmovies.php' %BASE_URL
        video_type = 'movie'
        nextmode = 'GetSources'
        folder = addon.get_setting('auto-play')=='false'

    html = GetURL(url)
    regex =  '<div class="regular_page">\s+<h1 class="titles">(.+)'
    regex += '<div class="clearer"></div>\s+</div>'
    container = re.search(regex, html, re.DOTALL|re.IGNORECASE).group(1)
    ltr_regex = '[%s]</h2>(.+?)<h2>' %letter
    ltr_container = re.search(ltr_regex, container, re.DOTALL|re.IGNORECASE).group(1)
    item_regex =  '<div class="all_movies_item">'
    item_regex += '<a href="(.+?)"> ?(.+?)</a> \[ (.+?) \]</div>'
    listings = re.finditer(item_regex, ltr_container)
    for item in listings:
        resurl,title,year = item.groups()

        listitem = build_listitem(video_type, title, year, img, resurl, subs=subs)
        url = '%s/%s' %(BASE_URL,resurl)
        queries = {'mode':nextmode, 'title':title, 'url':url,
                   'img':meta['cover_url'], 'imdbnum':meta['imdb_id'],
                   'video_type':video_type, 'year':year}
        li_url = addon.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem, 
                                    isFolder=folder)
    addon.end_of_directory()

def create_meta(video_type, title, year, thumb):
    try:    year = int(year)
    except: year = 0
    year = str(year)
    meta = {'title':title, 'year':year, 'imdb_id':'', 'overlay':''}
    meta['imdb_id'] = ''
    if META_ON:
        try:
            if video_type == 'tvshow':
                meta = metaget.get_meta(video_type, title)
                if not (meta['imdb_id'] or meta['tvdb_id']):
                    meta = metaget.get_meta(video_type, title, year=year)
                alt_id = meta['tvdb_id']

            else: #movie
                meta = metaget.get_meta(video_type, title, year=year)
                alt_id = meta['tmdb_id']

            if video_type == 'tvshow' and not USE_POSTERS:
                meta['cover_url'] = meta['banner_url']
            if POSTERS_FALLBACK and meta['cover_url'] in ('/images/noposter.jpg',''):
                meta['cover_url'] = thumb
            img = meta['cover_url']
        except: addon.log('Error assigning meta data for %s %s %s' %(video_type, title, year))
    return meta

def scan_by_letter(section, letter):
    import traceback
    addon.log('Building meta for %s letter %s' % (section,letter))
    pDialog = xbmcgui.DialogProgress()
    ret = pDialog.create('Scanning %s Letter %s' %(section,letter))
    if section == 'tvshow': url = BASE_URL + '/alltvshows.php'
    else: url = BASE_URL + '/allmovies.php'
    html = GetURL(url)

    pattern = '%s</h2>(.+?)(?:<h2>|<div class="clearer">)' %letter
    container = re.search(pattern, html, re.S).group(1)
    item_pattern = re.compile('<a.+?>(.+?)</a> \[ (\d{4}) \]</div>')
    for item in item_pattern.finditer(container):
        title,year = item.groups()
        success = False
        attempts_remaining = 4
        while attempts_remaining and not success:
            pDialog.update(0,'%s (%s)' %(title,year))
            try:
                meta = metaget.get_meta(section, title, year=year)
                success = True
            except Exception, e:
                attempts_remaining -= 1
                line1 = '%s (%s)' %(title,year)
                line2 = 'Failed: %s  attempts remaining' %attempts_remaining
                line3 = str(e)
                pDialog.update(0, line1, line2, line3)
                traceback.print_exc()
            if pDialog.iscanceled(): break
        if pDialog.iscanceled(): break
    return


def zipdir(basedir, archivename):
    from contextlib import closing
    from zipfile import ZipFile, ZIP_DEFLATED
    assert os.path.isdir(basedir)
    with closing(ZipFile(archivename, "w", ZIP_DEFLATED)) as z:
        for root, dirs, files in os.walk(basedir):
            #NOTE: ignore empty directories
            for fn in files:
                absfn = os.path.join(root, fn)
                zfn = absfn[len(basedir)+len(os.sep):] #XXX: relative path
                z.write(absfn, zfn)

def extract_zip(src, dest):
        try:
            print 'Extracting '+str(src)+' to '+str(dest)
            #make sure there are no double slashes in paths
            src=os.path.normpath(src)
            dest=os.path.normpath(dest) 

            #Unzip - Only if file size is > 1KB
            if os.path.getsize(src) > 10000:
                xbmc.executebuiltin("XBMC.Extract("+src+","+dest+")")
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
    global metaget
    container = metacontainers.MetaContainer()
    savpath = container.path
    AZ_DIRECTORIES.append('#')
    letters_completed = 0
    letters_per_zip = 27
    start_letter = ''
    end_letter = ''

    for type in ('tvshow','movie'):
        for letter in AZ_DIRECTORIES:
            if letters_completed == 0:
                start_letter = letter
                metaget.__del__()
                shutil.rmtree(container.cache_path)
                metaget=metahandlers.MetaData(preparezip=prepare_zip)

            if letters_completed <= letters_per_zip:
                scan_by_letter(type, letter)
                letters_completed += 1

            if (letters_completed == letters_per_zip
                or letter == '123' or get_dir_size(container.cache_path) > (500*1024*1024)):
                end_letter = letter
                arcname = 'MetaPack-%s-%s-%s.zip' % (type, start_letter, end_letter)
                arcname = os.path.join(savpath, arcname)
                metaget.__del__()
                zipdir(container.cache_path, arcname)
                metaget=metahandlers.MetaData(preparezip=prepare_zip)
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
        for f in files:
            if not f.endswith('.db') and not f.endswith('.zip'):
                #compute current (old) & new file locations
                oldLoc = os.path.join(root, f)

                newLoc = os.path.join(dest, f)
                if not os.path.isfile(newLoc):
                    try:
                        shutil.copy2(oldLoc, newLoc)
                        print 'File ' + f + ' copied.'
                    except IOError:
                        print 'file "' + f + '" already exists'
            else: print 'Skipping file ' + f

def install_metapack(pack):
    packs = metapacks.list()
    pack_details = packs[pack]
    mc = metacontainers.MetaContainer()
    work_path  = mc.work_path
    cache_path = mc.cache_path
    zip = os.path.join(work_path, pack)

    net = Net()
    cookiejar = addon.get_profile()
    cookiejar = os.path.join(cookiejar,'cookies')

    html = net.http_GET(pack_details[0]).content
    net.save_cookies(cookiejar)
    name = re.sub('-', r'\\\\u002D', pack)

    r = '"id": "([^\s]*?)", "modal_image_width": 0, "thumbnails": "", "caption_html": "", "has_hdvideo": false, "orig_mlist_name": "", "name": "%s".*?"secure_prefix": "(.+?)",' % name
    r = re.search(r,html)
    pack_url  = 'http://i.minus.com'
    pack_url += r.group(2)
    pack_url += '/d' + r.group(1) + '.zip'

    complete = download_metapack(pack_url, zip, displayname=pack)
    install_local_zip(zip)

def install_local_zip(zip):
    mc = metacontainers.MetaContainer()
    work_path  = mc.work_path
    cache_path = mc.cache_path

    extract_zip(zip, work_path)
    xbmc.sleep(5000)
    copy_meta_contents(work_path, cache_path)
    for table in mc.table_list:
        install = mc._insert_metadata(table)

def install_all_meta():
    all_packs = metapacks.list()
    skip = []
    skip.append('MetaPack-tvshow-A-G.zip')
    skip.append('MetaPack-tvshow-H-N.zip')
    skip.append('MetaPack-tvshow-O-U.zip')
    skip.append('MetaPack-tvshow-V-123.zip')
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
    if displayname == False:
        displayname=url
    dp = xbmcgui.DialogProgress()
    dp.create('Downloading', '', displayname)
    start_time = time.time()
    if os.path.isfile(dest): 
        print 'File to be downloaded already esists'
        return True
    try: 
        urllib.urlretrieve(url, dest, lambda nb, bs, fs: _pbhook(nb, bs, fs, dp, start_time)) 
    except:
        #only handle StopDownloading (from cancel), ContentTooShort (from urlretrieve), and OS (from the race condition); let other exceptions bubble 
        if sys.exc_info()[0] in (urllib.ContentTooShortError, StopDownloading, OSError): 
            return False 
        else: 
            raise 
        return False
    return True

def is_metapack_installed(pack):
    pass

def format_eta(seconds):
    print 'Format ETA starting with %s seconds' % seconds
    minutes,seconds = divmod(seconds, 60)
    print 'Minutes/Seconds: %s %s' %(minutes,seconds)
    if minutes > 60:
        hours,minutes = divmod(minutes, 60)
        print 'Hours/Minutes: %s %s' %(hours,minutes)
        return "ETA: %02d:%02d:%02d " % (hours, minutes, seconds)
    else:
        return "ETA: %02d:%02d " % (minutes, seconds)
    print 'Format ETA: hours: %s minutes: %s seconds: %s' %(hours,minutes,seconds)

def repair_missing_images():
    mc = metacontainers.MetaContainer()
    if DB == 'mysql': db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
    else: db = database.connect( mc.videocache )
    dbcur = db.cursor()
    dp = xbmcgui.DialogProgress()
    dp.create('Repairing Images', '', '', '')
    for type in ('tvshow','movie'):
        total  = 'SELECT count(*) from %s_meta WHERE ' % type
        total += 'imgs_prepacked = "true"'
        total = dbcur.execute(total).fetchone()[0]
        statement =  'SELECT title,cover_url,backdrop_url'
        if type   == 'tvshow': statement += ',banner_url'
        statement += ' FROM %s_meta WHERE imgs_prepacked = "true"' % type
        complete = 1.0
        start_time = time.time()
        already_existing = 0

        for row in dbcur.execute(statement):
            title     = row[0]
            cover      = row[1]
            backdrop = row[2]
            if type == 'tvshow': banner = row[3]
            else: banner = False
            percent = int((complete*100)/total)
            entries_per_sec = (complete - already_existing)
            entries_per_sec /=  max(float((time.time() - start_time)),1)
            total_est_time = total / max(entries_per_sec,1)
            eta = total_est_time - (time.time() - start_time)

            eta = format_eta(eta) 
            dp.update(percent, eta + title, '')
            if cover:
                dp.update(percent, eta + title, cover)
                img_name = metaget._picname(cover)
                img_path = os.path.join(metaget.mvcovers, img_name[0].lower())
                file = os.path.join(img_path,img_name)
                if not os.path.isfile(file):
                    retries = 4
                    while retries:
                        try: 
                            metaget._downloadimages(cover, img_path, img_name)
                            break
                        except: retries -= 1
                else: already_existing -= 1
            if backdrop:
                dp.update(percent, eta + title, backdrop)
                img_name = metaget._picname(backdrop)
                img_path = os.path.join(metaget.mvbackdrops, img_name[0].lower())
                file = os.path.join(img_path,img_name)
                if not os.path.isfile(file):
                    retries = 4
                    while retries:
                        try: 
                            metaget._downloadimages(backdrop, img_path, img_name)
                            break
                        except: retries -= 1
                else: already_existing -= 1
            if banner:
                dp.update(percent, eta + title, banner)
                img_name = metaget._picname(banner)
                img_path = os.path.join(metaget.tvbanners, img_name[0].lower())
                file = os.path.join(img_path,img_name)
                if not os.path.isfile(file):
                    retries = 4
                    while retries:
                        try: 
                            metaget._downloadimages(banner, img_path, img_name)
                            break
                        except: retries -= 1
                else: already_existing -= 1
            if dp.iscanceled(): return False
            complete += 1

def _pbhook(numblocks, blocksize, filesize, dp, start_time):
        try: 
            percent = min(numblocks * blocksize * 100 / filesize, 100) 
            currently_downloaded = float(numblocks) * blocksize / (1024 * 1024) 
            kbps_speed = numblocks * blocksize / (time.time() - start_time) 
            if kbps_speed > 0: 
                eta = (filesize - numblocks * blocksize) / kbps_speed 
            else: 
                eta = 0 
            kbps_speed = kbps_speed / 1024 
            total = float(filesize) / (1024 * 1024) 
            # print ( 
                # percent, 
                # numblocks, 
                # blocksize, 
                # filesize, 
                # currently_downloaded, 
                # kbps_speed, 
                # eta, 
                # ) 
            mbs = '%.02f MB of %.02f MB' % (currently_downloaded, total) 
            e = 'Speed: %.02f Kb/s ' % kbps_speed 
            e += 'ETA: %02d:%02d' % divmod(eta, 60) 
            dp.update(percent, mbs, e)
            #print percent, mbs, e 
        except: 
            percent = 100 
            dp.update(percent) 
        if dp.iscanceled(): 
            dp.close() 
            raise StopDownloading('Stopped Downloading')

def get_dir_size(start_path):
    print 'Calculating size of %s' % start_path
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    print 'Calculated: %s' % total_size
    return total_size

def setView(content, viewType):
    # set content type so library shows more views and info
    if content:
        xbmcplugin.setContent(int(sys.argv[1]), content)
    if addon.get_setting('auto-view') == 'true':
        xbmc.executebuiltin("Container.SetViewMode(%s)" % addon.get_setting(viewType) )

    # set sort methods - probably we don't need all of them
    xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_UNSORTED )
    xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_LABEL )
    xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RATING )
    xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_DATE )
    xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_PROGRAM_COUNT )
    xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RUNTIME )
    xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_GENRE )


def AddToLibrary(video_type, url, title, img, year, imdbnum):
    addon.log('Creating .strm for %s %s %s %s %s %s' %(video_type, title, imdbnum, url, img, year))
    if video_type == 'tvshow': 
        save_path = addon.get_setting('tvshow-folder')
        save_path = xbmc.translatePath(save_path)
        ShowTitle = title.strip()
        net = Net()
        cookiejar = addon.get_profile()
        cookiejar = os.path.join(cookiejar,'cookies')
        net.set_cookies(cookiejar)
        html = net.http_GET(BASE_URL + url).content
        net.save_cookies(cookiejar)
        adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
        r = re.search(adultregex, html, re.DOTALL)
        if r:
            addon.log('Adult content url detected')
            adulturl = BASE_URL + r.group(1)
            headers = {'Referer': url}
            net.set_cookies(cookiejar)
            html = net.http_GET(adulturl, headers=headers).content
            net.save_cookies(cookiejar)
        seasons = re.search('tv_container(.+?)<div class="clearer', html, re.DOTALL)
        if not seasons: addon.log_error('No Seasons found for %s at %s' %(ShowTitle,url))
        else:
            season_container = seasons.group(1)
            seasonList = season_container.split('<h2>')
            for eplist in seasonList:
                r = re.search('<a.+?>(.+?)</a>', eplist)
                if r:
                    season = r.group(1)
                    r = '"tv_episode_item".+?href="(.+?)">(.*?)</a>'
                    episodes = re.finditer(r, eplist, re.DOTALL)
                    for ep in episodes:
                        epurl, eptitle = ep.groups()
                        eptitle = re.sub('<[^<]+?>', '', eptitle.strip())
                        eptitle = re.sub('\s\s+' , ' ', eptitle)

                        match = re.search('tv-\d{1,10}-.*/season-(\d{1,4})-episode-(\d{1,4})', epurl, re.IGNORECASE | re.DOTALL)
                        seasonnum = match.group(1)
                        epnum = match.group(2)

                        filename = '%s S%sE%s.strm' %(ShowTitle,seasonnum,epnum)
                        filename = re.sub('[^\w\-_\. ]', '_', filename)
                        final_path = os.path.join(save_path, ShowTitle, season, filename)
                        final_path = xbmc.makeLegalFilename(final_path)
                        if not xbmcvfs.exists(os.path.dirname(final_path)):
                            try: xbmcvfs.mkdirs(os.path.dirname(final_path))
                            except: addon.log('Failed to create directory %s' %final_path)

                        playurl = BASE_URL + epurl
                        queries = {'mode':'GetSources', 'url':epurl, 'imdbnum':'', 'title':ShowTitle, 'img':'', 'dialog':1, 'video_type':'episode'}
                        strm_string = addon.build_plugin_url(queries)
                        addon.log('Writing strm: %s' %strm_string)
                        # if not xbmcvfs.exists(final_path):
                        #temp disabled bc of change in .strm format. Reenable in next version
                        try:
                            file = xbmcvfs.File(final_path,'w')
                            file.write(strm_string)
                            file.close()
                        except Exception, e:
                            addon.log('Failed to create .strm file: %s\n%s' %(final_path, e))

    elif video_type == 'movie' :
        save_path = addon.get_setting('movie-folder')
        save_path = xbmc.translatePath(save_path)
        strm_string = addon.build_plugin_url({'mode':'GetSources', 'url':url, 'imdbnum':imdbnum, 'title':title, 'img':img, 'year':year, 'dialog':1, 'video_type':'movie'})
        if year: title = '%s (%s)'% (title,year)
        filename = '%s.strm' %title
        filename = re.sub('[^\w\-_\. ]', '_', filename)
        final_path = os.path.join(save_path,title,filename)
        final_path = xbmc.makeLegalFilename(final_path)
        if not xbmcvfs.exists(os.path.dirname(final_path)):
            try:    xbmcvfs.mkdirs(os.path.dirname(final_path))
            except: addon.log('Failed to create directory %s' %final_path)
        # if not xbmcvfs.exists(final_path):
        #temp disabled bc of change in .strm format. Reenable in next version
        try:
            file = xbmcvfs.File(final_path,'w')
            file.write(strm_string)
            file.close()
        except: addon.log('Failed to create .strm file: %s\n%s' %(final_path, e))


def AddSubscription(url, title, img, year, imdbnum):
    try:
        sql = 'INSERT INTO subscriptions (url, title, img, year, imdbnum) VALUES (?,?,?,?,?)'
        if DB == 'mysql':
            db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
            sql = sql.replace('?','%s')
        else: db = database.connect( db_dir )
        cur = db.cursor()
        cur.execute(sql, (url, title, img, year, imdbnum))
        db.commit()
        db.close()
        AddToLibrary('tvshow', url, title, img, year, imdbnum)
        builtin = "XBMC.Notification(Subscribe,Subscribed to '%s',2000)" %title
        xbmc.executebuiltin(builtin)
    except database.IntegrityError:
        builtin = "XBMC.Notification(Subscribe,Already subscribed to '%s',2000)" %title
        xbmc.executebuiltin(builtin)
    xbmc.executebuiltin('Container.Update')


def CancelSubscription(url, title, img, year, imdbnum):
    sql_delete = 'DELETE FROM subscriptions WHERE url=? AND title=? AND year=?'
    if DB == 'mysql':
        db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        sql_delete = sql_delete.replace('?','%s')
    else: db = database.connect( db_dir )
    db_cur = db.cursor()
    db_cur.execute(sql_delete, (url,unicode(title,'utf-8'),year))
    db.commit()
    db.close()
    xbmc.executebuiltin('Container.Refresh')


def UpdateSubscriptions():
    if DB == 'mysql': db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
    else: db = database.connect( db_dir )
    cur = db.cursor()
    cur.execute('SELECT * FROM subscriptions')
    subs = cur.fetchall()
    for sub in subs:
        AddToLibrary('tvshow',sub[0],sub[1],sub[2],sub[3],sub[4])
    db.close()
    if addon.get_setting('library-update') == 'true':
        xbmc.executebuiltin('UpdateLibrary(video)')

def CleanupSubscriptions():
    addon.log('Cleaning up dead subscriptions')
    sql_delete = 'DELETE FROM subscriptions WHERE url=?'
    if DB == 'mysql':
        db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
        sql_delete = sql_delete.replace('?','%s')
    else: db = database.connect( db_dir )
    cur = db.cursor()
    cur.execute('SELECT * FROM subscriptions')
    subs = cur.fetchall()
    to_clean = []
    for sub in subs:
        meta = metaget.get_meta('tvshow', sub[1], year=sub[3])
        if meta['status'] == 'Ended':
            to_clean.append(sub[0])
            addon.log('Selecting %s  for removal' %sub[1])
    if to_clean:
        to_clean = zip(to_clean)
        cur.executemany(sql_delete, to_clean)
        db.commit()
    db.close()

def ManageSubscriptions():
    addon.add_item({'mode':'UpdateSubscriptions'}, {'title':'Update Subscriptions'})
    addon.add_item({'mode':'CleanupSubscriptions'}, {'title':'Clean Up Subscriptions'})
    setView('tvshows', 'tvshows-view')
    if DB == 'mysql': db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
    else: db = database.connect( db_dir )
    cur = db.cursor()
    cur.execute('SELECT * FROM subscriptions')
    subs = cur.fetchall()
    for sub in subs:
        meta = create_meta('tvshow', sub[1], sub[3], '')
        meta['title'] = format_label_sub(meta)

        cm = add_contextsearchmenu(meta['title'], 'tv')
        runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'CancelSubscription', 'url':sub[0], 'title':sub[1], 'img':sub[2], 'year':sub[3], 'imdbnum':sub[4]})
        cm.append(('Cancel subscription', runstring,))
        runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'SaveFav', 'section':'tv', 'title':sub[1], 'url':sub[0], 'year':sub[3]})
        cm.append(('Add to Favorites', runstring,))
        cm.append(('Show Information', 'XBMC.Action(Info)',))

        if META_ON:
            try:
                fanart = meta['backdrop_url']
                img = meta['cover_url']
            except:
                fanart = art('fanart.png')
                img = ''
        else:
            fanart = art('fanart.png')
            img = ''

        # addon.add_item({'mode':'ManageSubscriptions'},meta,cm,True,img,fanart,is_folder=True)
        listitem = xbmcgui.ListItem(meta['title'], iconImage=img, 
                thumbnailImage=img)
        listitem.setInfo('video', meta)
        listitem.setProperty('fanart_image', fanart)
        listitem.addContextMenuItems(cm, replaceItems=True)
        queries = {'mode':'TVShowSeasonList', 'title':sub[1], 'url':sub[0],
                   'img':img, 'imdbnum':meta['imdb_id'],
                   'video_type':'tvshow', 'year':sub[3]}
        li_url = addon.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem, 
                                    isFolder=True, totalItems=len(subs))    
    db.close()
    addon.end_of_directory()

def clean_filename(filename):
    # filename = addon.unescape(filename)
    return re.sub('[\\/:"*?<>|]+',' ',filename)


def multikeysort(items, columns, functions={}, getter=itemgetter):
    """Sort a list of dictionary objects or objects by multiple keys bidirectionally.

    Keyword Arguments:
    items -- A list of dictionary objects or objects
    columns -- A list of column names to sort by. Use -column to sort in descending order
    functions -- A Dictionary of Column Name -> Functions to normalize or process each column value
    getter -- Default "getter" if column function does not exist
              operator.itemgetter for Dictionaries
              operator.attrgetter for Objects
    """
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
    ranking = addon.get_setting('host-rank').split(',')
    host = host.lower()
    for tier in ranking:
        tier = tier.lower()
        if host in tier.split('|'):
            return ranking.index(tier) + 1
    return 1000

def RefreshMetadata(video_type, old_title, imdb, alt_id, year, new_title=''):
    metaget=metahandlers.MetaData()
    if new_title: search_title = new_title
    else: search_title = old_title
    # try:
    if video_type =='tvshow':
        api = metahandlers.TheTVDB()
        results = api.get_matching_shows(search_title)
        search_meta = []
        for item in results:
            option = {}
            option['tvdb_id'] = item[0]
            option['title']   = item[1]
            option['imdb_id'] = item[2]
            option['year']      = year
            search_meta.append(option)

    else: search_meta = metaget.search_movies(search_title)
    print 'search_meta: %s' %search_meta

    option_list = ['Manual Search...']
    for option in search_meta:
        if 'year' in option: disptitle = '%s (%s)' %(option['title'],option['year'])
        else: disptitle = option['title']
        option_list.append(disptitle)
    dialog = xbmcgui.Dialog()
    index = dialog.select('Choose', option_list)

    if index == 0:
        RefreshMetadata_manual(video_type, old_title, imdb, alt_id, year)
    elif index > -1:
        new_imdb_id = search_meta[index-1]['imdb_id']

        #Temporary workaround for metahandlers problem:
        #Error attempting to delete from cache table: no such column: year
        if video_type =='tvshow': year = ''

        addon.log(search_meta[index-1])
        meta = metaget.update_meta(video_type, old_title, imdb, year=year)
        xbmc.executebuiltin('Container.Refresh')
    # except: RefreshMetadata_manual(video_type, old_title, imdb, alt_id, year)

def RefreshMetadata_manual(video_type, old_title, imdb, alt_id, year):
    keyboard = xbmc.Keyboard()
    if year: disptitle = '%s (%s)' %(old_title,year)
    keyboard.setHeading('Enter a title')
    keyboard.setDefault(disptitle)
    keyboard.doModal()
    if (keyboard.isConfirmed()):
        search_string = keyboard.getText()
        RefreshMetadata(video_type, old_title, imdb, alt_id, year, search_string)

def migrate_to_mysql():
    try: 
        from sqlite3 import dbapi2 as sqlite
        addon.log('Loading sqlite3 for migration')
    except: 
        from pysqlite2 import dbapi2 as sqlite
        addon.log('pysqlite2 for migration')

    DB_NAME =      addon.get_setting('db_name')
    DB_USER =      addon.get_setting('db_user')
    DB_PASS =      addon.get_setting('db_pass')
    DB_ADDRESS = addon.get_setting('db_address')
    
    db_dir = os.path.join(xbmc.translatePath("special://database"), 'onechannelcache.db')
    sqlite_db = sqlite.connect(db_dir)
    mysql_db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
    table_count = 1
    record_count = 1
    all_tables = ['favorites', 'subscriptions', 'bookmarks']
    prog_ln1 = 'Migrating table %s of %s' %(table_count,3)
    progress = xbmcgui.DialogProgress()
    ret = progress.create('DB Migration', prog_ln1)
    while not progress.iscanceled() and table_count < 3:
        for table in all_tables:
            mig_prog = int((table_count*100)/3)
            prog_ln1 = 'Migrating table %s of %s' %(table_count,3)
            progress.update(mig_prog, prog_ln1)
            record_sql = 'SELECT * FROM %s' %table
            print record_sql
            cur = mysql_db.cursor()
            all_records = sqlite_db.execute(record_sql).fetchall()
            for record in all_records:
                prog_ln1 = 'Migrating table %s of %s' %(table_count,3)
                prog_ln2 = 'Record %s of %s' %(record_count,len(all_records))
                progress.update(mig_prog, prog_ln1, prog_ln2)
                args = ','.join('?'*len(record))
                args = args.replace('?','%s')
                insert_sql = 'REPLACE INTO %s VALUES(%s)' %(table,args)
                print insert_sql
                cur.execute(insert_sql,record)
                record_count += 1
            table_count += 1
            record_count = 1
            mysql_db.commit()
    sqlite_db.close()
    mysql_db.close()
    progress.close()
    dialog = xbmcgui.Dialog()
    ln1 = 'Do you want to permanantly delete'
    ln2 = 'the old database?'
    ln3 = 'THIS CANNOT BE UNDONE'
    yes = 'Keep'
    no  = 'Delete'
    ret = dialog.yesno('Migration Complete', ln1, ln2, ln3, yes, no)
    if ret:
        os.remove(db_dir)

def login_and_retry(redirect):
    addon.log('Logging in for url %s' %redirect)
    user   = addon.get_setting('username')
    passwd = addon.get_setting('passwd')
    url = BASE_URL + '/login.php'
    net = Net()
    cookiejar = addon.get_profile()
    cookiejar = os.path.join(cookiejar,'cookies')
    host = re.sub('http://', '', BASE_URL)
    headers = {'Referer': redirect, 'Origin': BASE_URL, 'Host': host}
    headers['User-Agent'] = USER_AGENT
    form_data = {'username':user, 'password':passwd, 'remember':'on', 'login_submit':'Login'}
    html = net.http_POST(url, headers=headers, form_data=form_data).content
    if '<a href="/logout.php">[ Logout ]</a>' in html:
        net.save_cookies(cookiejar)
        return html
    else:
        addon.log('Failed to login')
        print html

def website_is_integrated():
    enabled = addon.get_setting('site_enabled') == 'true'
    user = addon.get_setting('usename') is not None
    passwd = addon.get_setting('passwd') is not None
    if enabled and user and passwd: return True
    else: return False


def build_listitem(video_type, title, year, img, resurl, imdbnum='', season='', episode='', extra_cms=[], subs=[]):
    if META_ON:
        if video_type == 'episode':
            meta = metaget.get_episode_meta(title,imdbnum,season,episode)
            meta['TVShowTitle'] = title
        else:
            meta = create_meta(video_type, title, year, img)

        if 'cover_url' in meta: img = meta['cover_url']

        cm = add_contextsearchmenu(title, section)
        cm = cm + extra_cms
        
        runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'SaveFav', 'section':section, 'title':title, 'url':resurl, 'year':year})
        cm.append(('Add to Favorites', runstring),)
        
        runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'AddToLibrary', 'video_type':video_type, 'url':resurl, 'title':title, 'img':img, 'year':year})
        cm.append(('Add to Library', runstring),)
        
        if video_type in ('tvshow', 'episode'):
            runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'AddSubscription', 'video_type':video_type, 'url':resurl, 'title':title, 'img':img, 'year':year})
            cm.append(('Subscribe', runstring),)
        else:
            runstring = 'XBMC.RunPlugin(plugin://plugin.video.couchpotato_manager/movies/add?title=%s)' %title
            cm.append(('Add to CouchPotato', runstring),)
        
        cm.append(('Show Information', 'XBMC.Action(Info)'),)
        
        runstring = addon.build_plugin_url({'mode':'RefreshMetadata', 'video_type':video_type, 'title':meta['title'], 'imdb':meta['imdb_id'], 'alt_id':imdbnum, 'year':year})
        runstring = 'RunPlugin(%s)'%runstring
        cm.append(('Refresh Metadata', runstring,))

        if 'trailer_url' in meta:
            url = meta['trailer_url']
            url = url.encode('base-64').strip()
            runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'PlayTrailer', 'url':url})
            cm.append(('Watch Trailer', runstring,))

        if meta['overlay'] == 6: label = 'Mark as watched'
        else: label = 'Mark as unwatched'
        runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'ChangeWatched', 'title':title, 'imdbnum':meta['imdb_id'],  'video_type':video_type, 'year':year})
        cm.append((label, runstring,))

        fanart = ''
        if FANART_ON:
            try: fanart = meta['backdrop_url']
            except: fanart = ''

        if video_type == 'tvshow':
            if resurl in subs:
                meta['title'] = format_label_sub(meta)
            else:
                meta['title'] = format_label_tvshow(meta)
        elif video_type == 'episode':  meta['title'] = format_tvshow_episode(meta)
        else: meta['title'] = format_label_movie(meta)

        listitem = xbmcgui.ListItem(meta['title'], iconImage=img, 
                        thumbnailImage=img)
        listitem.setInfo('video', meta)
        listitem.setProperty('fanart_image', fanart)
        listitem.setProperty('imdb', meta['imdb_id'])
        listitem.setProperty('img', img)
        listitem.addContextMenuItems(cm, replaceItems=True)
    else: #Metadata off
        if video_type == 'episode':
            disp_title = '%sx%s' %(season, episode)
            listitem = xbmcgui.ListItem(disp_title, iconImage=img, 
                        thumbnailImage=img)
        else:
            if year: disp_title = '%s (%s)' %(title, year)
            else: disp_title = title
            listitem = xbmcgui.ListItem(disp_title, iconImage=img, 
                        thumbnailImage=img)
    return listitem


def upgrade_subs_db():
    addon.log('Upgrading subs db...')
    sql = "UPDATE subscriptions SET url = replace(url, 'http://www.1channel.ch', '')"
    if DB == 'mysql': db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
    else: db = database.connect( db_dir )
    cur = db.cursor()
    cur.execute(sql)
    db.commit()
    db.close()


def fix_existing_strms():
    for folder in ('tvshow-folder', 'movie-folder'):
        save_path = addon.get_setting(folder)
        save_path = xbmc.translatePath(save_path)
        for root, dirs, files in os.walk(save_path):
            for currentFile in files:
                if currentFile.endswith('.strm'):
                    addon.log( "processing file: %s" %currentFile)
                    full_path = os.path.join(root, currentFile)
                    with open(full_path, 'r+') as target:
                        content = target.read()
                        target.seek(0)
                        new_content = content.replace('&url=http%3A%2F%2Fwww.1channel.ch', '&url=')
                        if not '&video_type=' in new_content:
                            if folder == 'tvshow-folder':
                                new_content += '&video_type=episode'
                            elif folder == 'movie-folder':
                                new_content += '&video_type=movie'
                        addon.log('Writing new content: %s' %new_content)
                        target.write(new_content)
                    

mode        = addon.queries.get('mode',       None)
section      = addon.queries.get('section',    '')
genre        = addon.queries.get('genre',       '')
letter         = addon.queries.get('letter',       '')
sort           = addon.queries.get('sort',       '')
url             = addon.queries.get('url',           '')
title            = addon.queries.get('title',      '')
img            = addon.queries.get('img',           '')
season       = addon.queries.get('season',       '')
query         = addon.queries.get('query',       '')
page          = addon.queries.get('page',       '')
imdbnum    = addon.queries.get('imdbnum',      '')
year           = addon.queries.get('year',       '')
video_type  = addon.queries.get('video_type', '')
episode       = addon.queries.get('episode',    '')
season        = addon.queries.get('season',       '')
tvdbnum      = addon.queries.get('tvdbnum',       '')
alt_id           = addon.queries.get('alt_id',       '')
dialog          = addon.queries.get('dialog',       '')

addon.log(addon.queries)
addon.log(sys.argv)

if mode=='main':
    AddonMenu()
elif mode=='GetSources':
    import urlresolver
    GetSources(url,title,img,year,imdbnum,dialog)
elif mode=='PlaySource':
    import urlresolver
    PlaySource(url, title, img, year, imdbnum, video_type, season, episode)
elif mode=='PlayTrailer':
    import urlresolver
    PlayTrailer(url)
elif mode=='BrowseListMenu':
    BrowseListMenu(section)
elif mode=='BrowseAlphabetMenu':
    BrowseAlphabetMenu(section)
elif mode=='GetByLetter':
    GetByLetter(letter, section)
elif mode=='BrowseByGenreMenu':
    BrowseByGenreMenu(section)
elif mode=='GetFilteredResults':
    GetFilteredResults(section, genre, letter, sort, page)
elif mode=='TVShowSeasonList':
    TVShowSeasonList(url, title, year, tvdbnum)
elif mode=='TVShowEpisodeList':
    TVShowEpisodeList(title, season, imdbnum, tvdbnum)
elif mode=='GetSearchQuery':
    GetSearchQuery(section)
elif mode=='7000': # Enables Remote Search
    Search(section, query)
elif mode=='BrowseFavorites':
    BrowseFavorites(section)
elif mode=='BrowseFavorites_Website':
    BrowseFavorites_Website(section)
elif mode=='SaveFav':
    SaveFav(section, title, url, img, year)
elif mode=='DeleteFav':
    DeleteFav(section, title, url)
    xbmc.executebuiltin('Container.Refresh')
elif mode=='ChangeWatched':
    ChangeWatched(imdb_id=imdbnum, video_type=video_type, name=title, season=season, episode=episode, year=year)
    xbmc.executebuiltin('Container.Refresh')
elif mode=='9988': #Metahandler Settings
    print "Metahandler Settings"
    import metahandler
    metahandler.display_settings()
elif mode=='ResolverSettings':
    import urlresolver
    urlresolver.display_settings()
elif mode=='install_metapack':
    install_metapack(title)
elif mode=='install_local_metapack':
    dialog = xbmcgui.Dialog()
    zip = dialog.browse(1, 'Metapack', 'files', '.zip', False, False)
    install_local_zip(zip)
elif mode=='AddToLibrary':
    AddToLibrary(video_type, url, title, img, year, imdbnum)
    builtin = "XBMC.Notification(Add to Library,Added '%s' to library,2000)" %title
    xbmc.executebuiltin(builtin)
elif mode=='UpdateSubscriptions':
    UpdateSubscriptions()
    if addon.get_setting('cleanup-subscriptions')=='true':
        CleanupSubscriptions()
elif mode=='AddSubscription':
    AddSubscription(url, title, img, year, imdbnum)
elif mode=='ManageSubscriptions':
    ManageSubscriptions()
elif mode=='CancelSubscription':
    CancelSubscription(url, title, img, year, imdbnum)
elif mode=='CleanupSubscriptions':
    CleanupSubscriptions()
elif mode=='PageSelect':
    pages = int(addon.queries['pages'])
    dialog = xbmcgui.Dialog()
    options = []
    for page in range(pages):
        label = 'Page %s' % str(page+1)
        options.append(label)
    index = dialog.select('Skip to page', options)
    url = addon.build_plugin_url({'mode':'GetFilteredResults', 'section':section, 'genre':genre, 'letter':letter, 'sort':sort, 'page':index+1})
    builtin = 'Container.Update(%s)' %url
    xbmc.executebuiltin(builtin)
elif mode=='RefreshMetadata':
    RefreshMetadata(video_type, title, imdbnum, alt_id, year)
elif mode=='migrateDB':
    migrate_to_mysql()
elif mode=='migrateFavs':
    migrate_favs_to_web()
elif mode=='Help':
    addon.log('Showing help popup')
    popup = TextBox()