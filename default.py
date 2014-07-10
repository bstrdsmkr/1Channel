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
import re
import os
import sys
import json
import string
import urllib
import datetime
import metapacks
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import xbmcplugin
from addon.common.addon import Addon
try: from metahandler import metahandlers
except: xbmc.executebuiltin("XBMC.Notification(%s,%s,2000)" % ('Import Failed','metahandler')); pass
import utils
from pw_scraper import PW_Scraper
from db_utils import DB_Connection

_1CH = Addon('plugin.video.1channel', sys.argv)

META_ON = _1CH.get_setting('use-meta') == 'true'
FANART_ON = _1CH.get_setting('enable-fanart') == 'true'
USE_POSTERS = _1CH.get_setting('use-posters') == 'true'
POSTERS_FALLBACK = _1CH.get_setting('posters-fallback') == 'true'
THEME_LIST = ['Classic', 'Glossy_Black', 'PrimeWire']
THEME = THEME_LIST[int(_1CH.get_setting('theme'))]
THEME_PATH = os.path.join(_1CH.get_path(), 'art', 'themes', THEME)
AUTO_WATCH = _1CH.get_setting('auto-watch') == 'true'
ADDON_PATH = _1CH.get_path()
ICON_PATH = os.path.join(ADDON_PATH, 'icon.png')

AZ_DIRECTORIES = (ltr for ltr in string.ascii_uppercase)

GENRES = ['Action', 'Adventure', 'Animation', 'Biography', 'Comedy',
          'Crime', 'Documentary', 'Drama', 'Family', 'Fantasy', 'Game-Show',
          'History', 'Horror', 'Japanese', 'Korean', 'Music', 'Musical',
          'Mystery', 'Reality-TV', 'Romance', 'Sci-Fi', 'Short', 'Sport',
          'Talk-Show', 'Thriller', 'War', 'Western', 'Zombies']

pw_scraper = PW_Scraper(_1CH.get_setting("username"),_1CH.get_setting("passwd"))

db_connection = DB_Connection()

PREPARE_ZIP = False
__metaget__ = metahandlers.MetaData(preparezip=PREPARE_ZIP)

if not xbmcvfs.exists(_1CH.get_profile()): 
    try: xbmcvfs.mkdirs(_1CH.get_profile())
    except: os.mkdir(_1CH.get_profile())

def art(name): 
    return os.path.join(THEME_PATH, name)

def save_favorite(fav_type, name, url, img, year):
    if fav_type != 'tv': fav_type = 'movie'
    _1CH.log('Saving Favorite type: %s name: %s url: %s img: %s year: %s' % (fav_type, name, url, img, year))
    
    try:
        if utils.website_is_integrated():
            pw_scraper.add_favorite(url)
        else:
            db_connection.save_favorite(fav_type, name, url, year)
        builtin = 'XBMC.Notification(Save Favorite,Added to Favorites,2000, %s)'
        xbmc.executebuiltin(builtin % ICON_PATH)
    except:
            builtin = 'XBMC.Notification(Save Favorite,Item already in Favorites,2000, %s)'
            xbmc.executebuiltin(builtin % ICON_PATH)

def delete_favorite(url):
    _1CH.log('Deleting Favorite: %s' % (url))
    
    if utils.website_is_integrated():
        pw_scraper.delete_favorite(url)
    else:
        db_connection.delete_favorite(url)

def get_sources(url, title, img, year, imdbnum, dialog):
    url = urllib.unquote(url)
    _1CH.log('Getting sources from: %s' % url)
    primewire_url = url
    
    dbid=xbmc.getInfoLabel('ListItem.DBID')
    
    resume = False
    if db_connection.bookmark_exists(url):
        resume = utils.get_resume_choice(url)

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

    if META_ON and video_type == 'movie' and not imdbnum:
        imdbnum=pw_scraper.get_last_imdbnum()
        __metaget__.update_meta('movie', title, imdb_id='',new_imdb_id=imdbnum, year=year)

    _img = xbmc.getInfoImage('ListItem.Thumb')
    if _img != "":
        img = _img

    hosters=pw_scraper.get_sources(url)
    
    if not hosters:
        _1CH.show_ok_dialog(['No sources were found for this item'], title='PrimeWire')

    # auto play is on
    if _1CH.get_setting('auto-play')=='true':
        auto_try_sources(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid)
        
    else: # autoplay is off
        if dialog or _1CH.get_setting('source-win') == 'Dialog': #dialog is needed (playing from strm or dialogs are turned on)
            if _1CH.get_setting('filter-source') == 'true':
                play_filtered_dialog(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid)
                
            else:
                play_unfiltered_dialog(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid)
                
        else: # not from a strm (i.e. in the addon) and dialogs are off
            if _1CH.get_setting('filter-source') == 'true':
                play_filtered_dir(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume)
                
            else:
                play_unfiltered_dir(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume)

def play_filtered_dialog(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid):
    sources=[]
    for item in hosters:
        try:
            label = utils.format_label_source(item)
            hosted_media = urlresolver.HostedMediaFile(url=item['url'], title=label)
            sources.append(hosted_media)
            if item['multi-part']:
                partnum = 2
                for part in item['parts']:
                    label = utils.format_label_source_parts(item, partnum)
                    hosted_media = urlresolver.HostedMediaFile(url=item['parts'][partnum - 2], title=label)
                    sources.append(hosted_media)
                    partnum += 1
        except:
            _1CH.log('Error while trying to resolve %s' % url)
    
    source = urlresolver.choose_source(sources)
    if source:
        source=source.get_url()
    else:
        return
    
    PlaySource(source, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid, strm=True)

def play_unfiltered_dialog(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid):
    sources=[]
    for item in hosters:
        label = utils.format_label_source(item)
        sources.append(label)

    dialog = xbmcgui.Dialog()       
    index = dialog.select('Choose your stream', sources)
    if index > -1:
        PlaySource(hosters[index]['url'], title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid, strm=True)
    else:
        return 

def play_filtered_dir(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume):        
    for item in hosters:
        #_1CH.log(item)
        hosted_media = urlresolver.HostedMediaFile(url=item['url'])
        if hosted_media:
            label = utils.format_label_source(item)
            _1CH.add_directory({'mode': 'PlaySource', 'url': item['url'], 'title': title,
                                'img': img, 'year': year, 'imdbnum': imdbnum,
                                'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                               infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img, fanart=art('fanart.png'))
            if item['multi-part']:
                partnum = 2
                for part in item['parts']:
                    label = utils.format_label_source_parts(item, partnum)
                    partnum += 1
                    _1CH.add_directory({'mode': 'PlaySource', 'url': part, 'title': title,
                                        'img': img, 'year': year, 'imdbnum': imdbnum,
                                        'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                                       infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img,
                                       fanart=art('fanart.png'))
        else:
            _1CH.log('Skipping unresolvable source: %s' % (item['url']))
     
    _1CH.end_of_directory()

def play_unfiltered_dir(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume):
    for item in hosters:
        #_1CH.log(item)
        label = utils.format_label_source(item)
        _1CH.add_directory({'mode': 'PlaySource', 'url': item['url'], 'title': title,
                            'img': img, 'year': year, 'imdbnum': imdbnum,
                            'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                           infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img, fanart=art('fanart.png'))
        if item['multi-part']:
            partnum = 2
            for part in item['parts']:
                label = utils.format_label_source_parts(item, partnum)
                partnum += 1
                _1CH.add_directory({'mode': 'PlaySource', 'url': part, 'title': title,
                                    'img': img, 'year': year, 'imdbnum': imdbnum,
                                    'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                                   infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img,
                                   fanart=art('fanart.png'))
    
    _1CH.end_of_directory()

def auto_try_sources(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid):
    dlg = xbmcgui.DialogProgress()
    line1 = 'Trying Source:    '
    dlg.create('PrimeWire')
    total = len(hosters)
    count = 1
    success = False
    while not (success or dlg.iscanceled() or xbmc.abortRequested):
        for source in hosters:
            if dlg.iscanceled(): return
            percent = int((count * 100) / total)
            label = utils.format_label_source(source)
            dlg.update(percent, '', line1 + label)
            _1CH.log('Trying Source: %s' % (source['host']))
            if not PlaySource(source['url'], title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid): 
                dlg.update(percent, 'Playback Failed: %s' % (label), line1 + label)
                _1CH.log('Source Failed: %s' % (source['host']))
                count += 1
            else:
                success = True
                break  # Playback was successful, break out of the loop
        else:
            _1CH.log('All sources failed to play')
            dlg.close()
            _1CH.show_ok_dialog(['All Sources Failed to Play'], title='PrimeWire')
            break
    
def PlaySource(url, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid=None, strm=False):
    _1CH.log('Attempting to play url: %s' % url)
    stream_url = urlresolver.HostedMediaFile(url=url).resolve()

    #If urlresolver returns false then the video url was not resolved.
    if not stream_url or not isinstance(stream_url, basestring):
        return False

    win = xbmcgui.Window(10000)
    win.setProperty('1ch.playing.title', title)
    win.setProperty('1ch.playing.year', year)
    win.setProperty('1ch.playing.imdb', imdbnum)
    win.setProperty('1ch.playing.season', str(season))
    win.setProperty('1ch.playing.episode', str(episode))
    win.setProperty('1ch.playing.url',primewire_url)

    #metadata is enabled
    if META_ON:
        if not dbid or int(dbid) <= 0:
            #we're not playing from a library item
            if video_type == 'episode':
                meta = __metaget__.get_episode_meta(title, imdbnum, season, episode)
                meta['TVShowTitle'] = title
                meta['title'] = utils.format_tvshow_episode(meta)
                poster = meta['cover_url']
            elif video_type == 'movie':
                meta = __metaget__.get_meta('movie', title, year=year)
                meta['title'] = utils.format_label_movie(meta)
                poster = meta['cover_url']
    else: #metadata is not enabled
        meta = {'label' : title, 'title' : title}
        poster = ''

    if dbid and int(dbid) > 0:
        #we're playing from a library item
        if video_type == 'episode':
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodeDetails", "params": {"episodeid" : %s, "properties" : ["title", "plot", "votes", "rating", "writer", "firstaired", "playcount", "runtime", "director", "productioncode", "season", "episode", "originaltitle", "showtitle", "lastplayed", "fanart", "thumbnail", "dateadded"]}, "id": 1}'
            cmd = cmd %(dbid)
            meta = xbmc.executeJSONRPC(cmd)
            meta = json.loads(meta)
            meta = meta['result']['episodedetails']
            meta['TVShowTitle'] = meta['showtitle']
            meta['duration'] = meta['runtime']
            meta['premiered'] = meta['firstaired']
            poster = meta['thumbnail']
            meta['DBID']=dbid
            
        if video_type == 'movie':
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovieDetails", "params": {"movieid" : %s, "properties" : ["title", "plot", "votes", "rating", "writer", "playcount", "runtime", "director", "originaltitle", "lastplayed", "fanart", "thumbnail", "file", "year", "dateadded"]}, "id": 1}'
            cmd = cmd %(dbid)
            meta = xbmc.executeJSONRPC(cmd)
            meta = json.loads(meta)
            meta = meta['result']['moviedetails']
            meta['duration'] = meta['runtime']
            poster = meta['thumbnail']
            meta['DBID']=dbid
    
    win = xbmcgui.Window(10000)
    win.setProperty('1ch.playing', json.dumps(meta))
    
    listitem = xbmcgui.ListItem(path=url, iconImage="DefaultVideo.png", thumbnailImage=poster)
    
    resume_point=0
    if resume: 
        resume_point = db_connection.get_bookmark(primewire_url)
        
    _1CH.log("Playing Video from: %s secs"  % (resume_point))
    listitem.setProperty('ResumeTime', str(resume_point))
    listitem.setProperty('Totaltime', str(99999)) # dummy value to force resume to work

    listitem.setProperty('IsPlayable', 'true')
    listitem.setInfo(type = "Video", infoLabels = meta)
    listitem.setPath(stream_url)
    xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, listitem)

    return True

def ChangeWatched(imdb_id, video_type, name, season, episode, year='', watched='', refresh=False):
    __metaget__.change_watched(video_type, name, imdb_id, season=season, episode=episode, year=year, watched=watched)
    if refresh:
        xbmc.executebuiltin("XBMC.Container.Refresh")


def PlayTrailer(url):
    url = url.decode('base-64')
    _1CH.log('Attempting to resolve and play trailer at %s' % url)
    sources = []
    hosted_media = urlresolver.HostedMediaFile(url=url)
    sources.append(hosted_media)
    source = urlresolver.choose_source(sources)
    stream_url = source.resolve() if source else ''
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
            if search_text == '!#create metapacks': metapacks.create_meta_packs()
            if search_text == '!#repair meta': repair_missing_images()
            if search_text == '!#install all meta': metapacks.install_all_meta()
            if search_text.startswith('!#sql:'):
                _1CH.log('Running SQL: |%s|' % (search_text[6:]))
                db_connection.execute_sql(search_text[6:])
        else:
            queries = {'mode': 'Search', 'section': section, 'query': keyboard.getText()}
            pluginurl = _1CH.build_plugin_url(queries)
            builtin = 'Container.Update(%s)' %(pluginurl)
            xbmc.executebuiltin(builtin)
    else:
        BrowseListMenu(section)

def GetSearchQueryAdvanced(section):
    try:
        query=utils.get_adv_search_query(section)
        js_query=json.dumps(query)
        queries = {'mode': 'SearchAdvanced', 'section': section, 'query': js_query}
        pluginurl = _1CH.build_plugin_url(queries)
        builtin = 'Container.Update(%s)' %(pluginurl)
        xbmc.executebuiltin(builtin)
    except:
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
            if search_text == '!#create metapacks': metapacks.create_meta_packs()
            if search_text == '!#repair meta': repair_missing_images()
            if search_text == '!#install all meta': metapacks.install_all_meta()
            if search_text.startswith('!#sql:'):
                _1CH.log('Running SQL: %s' % (search_text[6:]))
                db_connection.execute_sql(search_text[6:])
        else:
            queries = {'mode': 'SearchDesc', 'section': section, 'query': keyboard.getText()}
            pluginurl = _1CH.build_plugin_url(queries)
            builtin = 'Container.Update(%s)' %(pluginurl)
            xbmc.executebuiltin(builtin)
    else:
        BrowseListMenu(section)


def Search(section, query):
    section_params = get_section_params(section)
    
    results=pw_scraper.search(section,query)
    total=pw_scraper.get_last_res_total()
    
    resurls = []
    for result in results:
        if result['url'] not in resurls:
            resurls.append(result['url'])                
            create_item(section_params,result['title'],result['year'],result['img'],result['url'],totalItems=total)
    _1CH.end_of_directory()


def SearchAdvanced(section, query='', tag='', description=False, country='', genre='', actor='', director='', year='0', month='0', decade='0', host='', rating='', advanced='1'):
    section_params = get_section_params(section)
    
    results=pw_scraper.search_advanced(section, query, tag, description, country, genre, actor, director, year, month, decade, host, rating, advanced)
    total=pw_scraper.get_last_res_total()
    
    resurls = []
    for result in results:
        if result['url'] not in resurls:
            resurls.append(result['url'])                
            create_item(section_params,result['title'],result['year'],result['img'],result['url'],totalItems=total)
    _1CH.end_of_directory()


def SearchDesc(section, query):
    section_params = get_section_params(section)
    results=pw_scraper.search_desc(section,query)
    total=pw_scraper.get_last_res_total()

    resurls = []
    for result in results:
        if result['url'] not in resurls:
            resurls.append(result['url'])
            create_item(section_params, result['title'], result['year'], result['img'], result['url'], totalItems=total)
    _1CH.end_of_directory()

def AddonMenu():  # homescreen
    _1CH.log('Main Menu')
    db_connection.init_database()
    if utils.has_upgraded():
        _1CH.log('Showing update popup')
        utils.TextBox()
        adn = xbmcaddon.Addon('plugin.video.1channel')
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

def BrowseListMenu(section):
    _1CH.log('Browse Options')
    _1CH.add_directory({'mode': 'BrowseAlphabetMenu', 'section': section}, {'title': 'A-Z'}, img=art('atoz.png'),
                       fanart=art('fanart.png'))
    add_search_item({'mode': 'GetSearchQuery', 'section': section}, 'Search')
    if utils.website_is_integrated():
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
    
    add_search_item({'mode': 'GetSearchQueryDesc', 'section': section}, 'Search (+Description)')
    add_search_item({'mode': 'GetSearchQueryAdvanced', 'section': section}, 'Search (Advanced Search)')
    
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

# add searches as an items so they don't get added to the path history
# _1CH.add_item doesn't work because it insists on adding non-folder items as playable
def add_search_item(queries, label):
    liz = xbmcgui.ListItem(label=label, iconImage=art('search.png'), thumbnailImage=art('search.png'))
    liz.setProperty('fanart_image', art('fanart.png'))
    liz_url = _1CH.build_plugin_url(queries)
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

def BrowseAlphabetMenu(section=None):
    _1CH.log('Browse by alphabet screen')
    _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'alphabet', 'letter': '123'},
                       {'title': '#123'}, img=art('123.png'), fanart=art('fanart.png'))
    for character in AZ_DIRECTORIES:
        _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'alphabet', 'letter': character},
                           {'title': character}, img=art(character.lower() + '.png'), fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def BrowseByGenreMenu(section=None, letter=None): #2000
    print 'Browse by genres screen'
    for genre in GENRES:
        _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': '', 'genre': genre},
                           {'title': genre}, img=art(genre.lower() + '.png'))
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
    #    contextmenuitems.append(('Search KissAnime', 'XBMC.Container.Update(%s?mode=%s&pageno=1&pagecount=1&title=%s)' % ('plugin://plugin.video.kissanime/','Search',nameonly)))
    #if os.path.exists(xbmc.translatePath("special://home/addons/") + 'plugin.video.merdb'):
    #    if video_type == 'tv': section = 'tvshows'; surl='http://merdb.ru/tvshow/'
    #    else: section = 'movies'; surl='http://merdb.ru/'
    #    contextmenuitems.append(('Search MerDB', 'XBMC.Container.Update(%s?mode=%s&section=%s&url=%s&title=%s)' % ('plugin://plugin.video.merdb/','Search',section,urllib.quote_plus(surl),nameonly)))
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

def create_item(section_params,title,year,img,url, imdbnum='', season='', episode = '', totalItems=0, menu_items=None):
    #_1CH.log('Create Item: %s, %s, %s, %s, %s, %s, %s, %s, %s' % (section_params, title, year, img, url, imdbnum, season, episode, totalItems))
    # fix episode url being added to subs
    if section_params['video_type']=='episode':
        temp_url=re.match('(/.*/).*',url).groups()[0]
    else:
        temp_url=url
    liz = build_listitem(section_params['video_type'], title, year, img, temp_url, imdbnum, season, episode, extra_cms=menu_items, subs=section_params['subs'])
    img = liz.getProperty('img')
    imdbnum = liz.getProperty('imdb')
    if not section_params['folder']: # should only be when it's a movie and dialog are off and autoplay is off
        liz.setProperty('isPlayable','true')
    queries = {'mode': section_params['nextmode'], 'title': title, 'url': url, 'img': img, 'imdbnum': imdbnum, 'video_type': section_params['video_type']}
    liz_url = _1CH.build_plugin_url(queries)
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz,section_params['folder'],totalItems)

def GetFilteredResults(section=None, genre=None, letter=None, sort='alphabet', page=None):
    _1CH.log('Filtered results for Section: %s Genre: %s Letter: %s Sort: %s Page: %s' % (section, genre, letter, sort, page))

    section_params = get_section_params(section)
    results = pw_scraper.get_filtered_results(section, genre, letter, sort, page)
    total_pages = pw_scraper.get_last_res_pages()

    resurls = []
    count = 0
    win = xbmcgui.Window(10000)
    for result in results:
        #resurl, title, year, thumb = s.groups()
        if result['url'] not in resurls:
            resurls.append(result['url'])
            create_item(section_params,result['title'],result['year'],result['img'],result['url'])

            # expose to skin
            if sort == update_movie_cat():
                win.setProperty('1ch.movie.%d.title' % count, result['title'])
                win.setProperty('1ch.movie.%d.thumb' % count, result['img'])
                # Needs dialog=1 to show dialog instead of going to window
                queries = {'mode': section_params['nextmode'], 'url': result['url'], 'title': result['title'], 
                            'img': result['img'], 'dialog': 1, 'video_type': section_params['video_type']}
                win.setProperty('1ch.movie.%d.path' % count, _1CH.build_plugin_url(queries))
                count = count + 1

    # more
    if sort == update_movie_cat():
        # goto page 1 since it may take some time to download page 2 
        # since users may be inpatient because xbmc does not show progress 
        command = _1CH.build_plugin_url( {'mode': 'GetFilteredResults', 'section': section, 'sort': sort, 'title': _1CH.get_setting('auto-update-movies-cat'), 'page':'1'})
        win.setProperty('1ch.movie.more.title', "More")
        win.setProperty('1ch.movie.more.path', command)

    if not page: page = 1
    next_page = int(page)+1

    if int(page) < int(total_pages):
        label = 'Skip to Page...'
        command = _1CH.build_plugin_url(
            {'mode': 'PageSelect', 'pages': total_pages, 'section': section, 'genre': genre, 'letter': letter,
             'sort': sort})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': 'Next Page >>'}
        _1CH.add_directory(
            {'mode': 'GetFilteredResults', 'section': section, 'genre': genre, 'letter': letter, 'sort': sort,
             'page': next_page},
            meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)

    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache')=='true')


def TVShowSeasonList(url, title, year, old_imdb, old_tvdb=''):
    _1CH.log('Seasons for TV Show %s' % url)
    season_gen=pw_scraper.get_season_list(url)
    seasons = list(season_gen) # copy the generator into a list so that we can iterate over it multiple times
    new_imdbnum = pw_scraper.get_last_imdbnum()
    
    imdbnum = old_imdb
    if META_ON:
        if not old_imdb and new_imdbnum:
            try: _1CH.log('Imdb ID not recieved from title search, updating with new id of %s' % new_imdbnum)
            except: pass
            try:
                try: _1CH.log('Title: %s Old IMDB: %s Old TVDB: %s New IMDB %s Year: %s' % (title, old_imdb, old_tvdb, new_imdbnum, year))
                except: pass
                __metaget__.update_meta('tvshow', title, old_imdb, old_tvdb, new_imdbnum)
            except:
                try: _1CH.log('Error while trying to update metadata with: %s, %s, %s, %s, %s' % (title, old_imdb, old_tvdb, new_imdbnum, year))
                except: pass
            imdbnum = new_imdbnum

        season_nums = [season[0] for season in seasons]
        season_meta = __metaget__.get_seasons(title, imdbnum, season_nums)
        
    fanart = ''
    num = 0
    seasons_found=False
    for season in seasons:
        seasons_found=True
        season_num,season_html = season
        temp = {'cover_url': ''}

        if META_ON:
            temp = season_meta[num]
            if FANART_ON:
                try:
                    fanart = temp['backdrop_url']
                except:
                    pass

        label = 'Season %s' % season_num
        db_connection.cache_season(season_num, season_html)
        listitem = xbmcgui.ListItem(label, iconImage=temp['cover_url'],
                                    thumbnailImage=temp['cover_url'])
        listitem.setInfo('video', temp)
        listitem.setProperty('fanart_image', fanart)
        queries = {'mode': 'TVShowEpisodeList', 'season': season_num,
                   'imdbnum': imdbnum, 'title': title}
        li_url = _1CH.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem,
                                    isFolder=True,
                                    totalItems=len(seasons))

        num += 1

    if not seasons_found:
        _1CH.log_error("No Seasons Found for %s at %s" % (title, url))
        _1CH.show_small_popup('PrimeWire','No Seasons Found for %s' % (title), 3000, ICON_PATH)
        return
    
    xbmcplugin.endOfDirectory(int(sys.argv[1]))
    utils.set_view('seasons', 'seasons-view')

def TVShowEpisodeList(ShowTitle, season, imdbnum, tvdbnum):
    season_html = db_connection.get_cached_season(season)
    r = '"tv_episode_item".+?href="(.+?)">(.*?)</a>'
    episodes = re.finditer(r, season_html, re.DOTALL)
    
    section_params = get_section_params('episode')

    for ep in episodes:
        epurl, eptitle = ep.groups()
        eptitle = re.sub(r'<[^<]+?>', '', eptitle.strip())
        eptitle = re.sub(r'\s\s+', ' ', eptitle)

        season = int(re.search('/season-([0-9]{1,4})-', epurl).group(1))
        epnum = int(re.search('-episode-([0-9]{1,3})', epurl).group(1))

        create_item(section_params, ShowTitle, year, img, epurl, imdbnum, season, epnum)

    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache')=='true')

def get_section_params(section):
    section_params={}
    if section == 'tv':
        utils.set_view('tvshows', 'tvshows-view')
        section_params['nextmode'] = 'TVShowSeasonList'
        section_params['video_type'] = 'tvshow'
        section_params['folder'] = True
        subscriptions = db_connection.get_subscriptions()
        section_params['subs'] = [row[0] for row in subscriptions]
    elif section=='episode':
        section_params['nextmode'] = 'GetSources'
        section_params['video_type']='episode'
        utils.set_view('episodes', 'episodes-view')
        section_params['folder'] = (_1CH.get_setting('source-win') == 'Directory' and _1CH.get_setting('auto-play') == 'false')
        section_params['subs'] = []
    else:
        utils.set_view('movies', 'movies-view')
        section_params['nextmode'] = 'GetSources'
        section_params['video_type'] = 'movie'
        section_params['folder'] = (_1CH.get_setting('source-win') == 'Directory' and _1CH.get_setting('auto-play') == 'false')
        section_params['subs'] = []
    return section_params

def browse_favorites(section):
    if not section: section='movie'
    favs=db_connection.get_favorites(section)
    
    section_params = get_section_params(section)
    if section=='tv':
        label='Add Favorite TV Shows to Library'
    else:
        label='Add Favorite Movies to Library'
        
    liz = xbmcgui.ListItem(label=label)
    liz_url = _1CH.build_plugin_url({'mode': 'fav2Library', 'section': section})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

    for row in favs:
        _, title,favurl,year = row
        
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': 'DeleteFav', 'section': section, 'title': title, 'url': favurl, 'year': year})
        menu_items = [('Remove from Favorites', runstring)]

        create_item(section_params,title,year,'',favurl,menu_items=menu_items)
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache')=='true')

def browse_favorites_website(section, page=None):
    if not section: section='movies'
    local_favs=db_connection.get_favorites_count()
    
    if local_favs:
        liz = xbmcgui.ListItem(label='Upload Local Favorites')
        liz_url = _1CH.build_plugin_url({'mode': 'migrateFavs'})
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)
        
    if section=='tv':
        label='Add Favorite TV Shows to Library'
    else:
        label='Add Favorite Movies to Library'

    liz = xbmcgui.ListItem(label=label)
    liz_url = _1CH.build_plugin_url({'mode': 'fav2Library', 'section': section})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

    section_params = get_section_params(section)
    
    for fav in pw_scraper.get_favorities(section, page, paginate=True):
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': 'DeleteFav', 'section': section, 'title': fav['title'], 'url': fav['url'], 'year': fav['year']})
        menu_items = [('Delete Favorite', runstring)]
        create_item(section_params,fav['title'],fav['year'],fav['img'],fav['url'],menu_items=menu_items)
    
    total_pages=pw_scraper.get_last_res_pages()
    if not page: page = 1
    next_page = int(page)+1

    if int(page) < int(total_pages):
        label = 'Skip to Page...'
        command = _1CH.build_plugin_url({'mode': 'FavPageSelect', 'section': section, 'pages': total_pages})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': 'Next Page >>'}
        _1CH.add_directory({'mode': 'browse_favorites_website', 'section': section, 'page': next_page}, meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)
        
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache')=='true')

def migrate_favs_to_web():
    progress = xbmcgui.DialogProgress()
    ln1 = 'Uploading your favorites to www.primewire.ag...'
    progress.create('Uploading Favorites', ln1)
    successes = []
    all_favs= db_connection.get_favorites()
    fav_len = len(all_favs)
    count=0
    for fav in all_favs:
        if progress.iscanceled(): return
        title = fav[1]
        favurl = fav[2]
        try:
            pw_scraper.add_favorite(favurl)
            ln3 = "Success"
            _1CH.log('%s added successfully' % title)
            successes.append((title, favurl))
        except Exception as e:
            ln3= "Already Exists"
            _1CH.log(e)
        count += 1
        progress.update(count*100/fav_len, ln1, 'Processed %s' % title, ln3)
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
        db_connection.delete_favorites([fav[1] for fav in successes])
    xbmc.executebuiltin("XBMC.Container.Refresh")

def add_favs_to_library(section):    
    if not section: section='movie'
    section_params=get_section_params(section)
    if utils.website_is_integrated():
        for fav in pw_scraper.get_favorities(section, paginate=False):
            add_to_library(section_params['video_type'], fav['url'], fav['title'], fav['img'], fav['year'], '')
    else:
        favs=db_connection.get_favorites(section)
        
        for fav in favs:
            _, title, url, year = fav
            add_to_library(section_params['video_type'], url, title, '', year, '')
        
    if section=='tv':
        message='Favorite TV Shows Added to Library'
    else:
        message='Favorite Movies Added to Library'
        
    builtin = 'XBMC.Notification(Primewire,%s,4000, %s)'
    xbmc.executebuiltin(builtin % (message,ICON_PATH))

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
                _ = meta['tmdb_id']

            if video_type == 'tvshow' and not USE_POSTERS:
                meta['cover_url'] = meta['banner_url']
            if POSTERS_FALLBACK and meta['cover_url'] in ('/images/noposter.jpg', ''):
                meta['cover_url'] = thumb
        except:
            try: _1CH.log('Error assigning meta data for %s %s %s' % (video_type, title, year))
            except: pass
    return meta

def repair_missing_images():
    _1CH.log("Repairing Metadata Images")
    db_connection.repair_meta_images()

def add_to_library(video_type, url, title, img, year, imdbnum):
    try: _1CH.log('Creating .strm for %s %s %s %s %s %s' % (video_type, title, imdbnum, url, img, year))
    except: pass
    if video_type == 'tvshow':
        save_path = _1CH.get_setting('tvshow-folder')
        save_path = xbmc.translatePath(save_path)
        show_title = title.strip()
        seasons = pw_scraper.get_season_list(url, cached=False)

        found_seasons=False
        for season in seasons:
            found_seasons=True
            season_num= season[0]
            season_html = season[1]
            r = '"tv_episode_item".+?href="(.+?)">(.*?)</a>'
            episodes = re.finditer(r, season_html, re.DOTALL)
            for ep_line in episodes:
                epurl, eptitle = ep_line.groups()
                eptitle = re.sub('<[^<]+?>', '', eptitle.strip())
                eptitle = re.sub(r'\s\s+', ' ', eptitle)

                pattern = r'tv-\d{1,10}-.*/season-\d+-episode-(\d+)'
                match = re.search(pattern, epurl, re.I | re.DOTALL)
                epnum = match.group(1)

                filename = utils.filename_from_title(show_title, video_type)
                filename = filename % (season_num, epnum)
                show_title = re.sub(r'[^\w\-_\. ]', '_', show_title)
                final_path = os.path.join(save_path, show_title, 'Season '+season_num, filename)
                final_path = xbmc.makeLegalFilename(final_path)
                if not xbmcvfs.exists(os.path.dirname(final_path)):
                    try:
                        try: xbmcvfs.mkdirs(os.path.dirname(final_path))
                        except: os.mkdir(os.path.dirname(final_path))
                    except:
                        _1CH.log('Failed to create directory %s' % final_path)

                queries = {'mode': 'GetSources', 'url': epurl, 'imdbnum': '', 'title': show_title, 'img': '',
                           'dialog': 1, 'video_type': 'episode'}
                strm_string = _1CH.build_plugin_url(queries)

                old_strm_string=''
                try:
                    f = xbmcvfs.File(final_path, 'r')
                    old_strm_string = f.read()
                    f.close()
                except:  pass

                #print "Old String: %s; New String %s" %(old_strm_string,strm_string)
                # string will be blank if file doesn't exist or is blank
                if strm_string != old_strm_string:
                    try:
                        _1CH.log('Writing strm: %s' % strm_string)
                        file_desc = xbmcvfs.File(final_path, 'w')
                        file_desc.write(strm_string)
                        file_desc.close()
                    except Exception, e:
                        _1CH.log('Failed to create .strm file: %s\n%s' % (final_path, e))
        if not found_seasons:
            _1CH.log_error('No Seasons found for %s at %s' % (show_title, url))
                
    elif video_type == 'movie':
        save_path = _1CH.get_setting('movie-folder')
        save_path = xbmc.translatePath(save_path)
        strm_string = _1CH.build_plugin_url(
            {'mode': 'GetSources', 'url': url, 'imdbnum': imdbnum, 'title': title, 'img': img, 'year': year,
             'dialog': 1, 'video_type': 'movie'})
        if year: title = '%s (%s)' % (title, year)
        filename = utils.filename_from_title(title, 'movie')
        title = re.sub(r'[^\w\-_\. ]', '_', title)
        final_path = os.path.join(save_path, title, filename)
        final_path = xbmc.makeLegalFilename(final_path)
        if not xbmcvfs.exists(os.path.dirname(final_path)):
            try:
                try: xbmcvfs.mkdirs(os.path.dirname(final_path))
                except: os.mkdir(os.path.dirname(final_path))
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
            _1CH.log('Failed to create .strm file: %s\n%s' % (final_path, e))


def add_subscription(url, title, img, year, imdbnum, day=''):
    try:
        if len(day)==0: day=datetime.date.today().strftime('%A')
        elif day==' ': day=''
        db_connection.add_subscription(url, title, img, year, imdbnum, day)
        add_to_library('tvshow', url, title, img, year, imdbnum)
        builtin = "XBMC.Notification(Subscribe,Subscribed to '%s',2000, %s)" % (title, ICON_PATH)
        xbmc.executebuiltin(builtin)
    except:
        builtin = "XBMC.Notification(Subscribe,Already subscribed to '%s',2000, %s)" % (title, ICON_PATH)
        xbmc.executebuiltin(builtin)
    xbmc.executebuiltin('Container.Update')


def cancel_subscription(url, title, img, year, imdbnum):
    db_connection.delete_subscription(url)
    xbmc.executebuiltin('Container.Refresh')

def update_subscriptions():
    subs=db_connection.get_subscriptions()
    for sub in subs:
        add_to_library('tvshow', sub[0], sub[1], sub[2], sub[3], sub[4])
    if _1CH.get_setting('library-update') == 'true':
        xbmc.executebuiltin('UpdateLibrary(video)')


def clean_up_subscriptions():
    _1CH.log('Cleaning up dead subscriptions')
    subs=db_connection.get_subscriptions()
    for sub in subs:
        meta = __metaget__.get_meta('tvshow', sub[1], year=sub[3])
        if meta['status'] == 'Ended':
            try: _1CH.log('Selecting %s  for removal' % sub[1])
            except: pass
            db_connection.delete_subscription(sub[0])

def manage_subscriptions(day=''):
    liz = xbmcgui.ListItem(label='Update Subscriptions')
    liz_url = _1CH.build_plugin_url({'mode': 'update_subscriptions'})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)
    
    liz = xbmcgui.ListItem(label='Clean Up Subscriptions')
    liz_url = _1CH.build_plugin_url({'mode': 'clean_up_subscriptions'})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

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
    utils.set_view('tvshows', 'tvshows-view')

    subs=db_connection.get_subscriptions(day)
    for sub in subs:
        meta = create_meta('tvshow', sub[1], sub[3], '')
        meta['title'] = utils.format_label_sub(meta)

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
    _1CH.end_of_directory()

def compose(inner_func, *outer_funcs):
    """Compose multiple unary functions together into a single unary function"""
    if not outer_funcs:
        return inner_func
    outer_func = compose(*outer_funcs)
    return lambda *args, **kwargs: outer_func(inner_func(*args, **kwargs))


def build_listitem(video_type, title, year, img, resurl, imdbnum='', season='', episode='', extra_cms=None, subs=None):
    if not subs: subs = []
    if not extra_cms: extra_cms = []
    menu_items = add_contextsearchmenu(title, section, resurl)
    menu_items = menu_items + extra_cms

    if video_type != 'episode' and 'Delete Favorite' not in [item[0] for item in menu_items]:
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
                meta['title'] = utils.format_label_sub(meta)
            else:
                meta['title'] = utils.format_label_tvshow(meta)
        elif video_type == 'episode':
            meta['title'] = utils.format_tvshow_episode(meta)
        else:
            meta['title'] = utils.format_label_movie(meta)

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

    # Hack resumetime & totaltime to prevent XBMC from popping up a resume dialog if a native bookmark is set. UGH! 
    listitem.setProperty('resumetime',str(0))
    listitem.setProperty('totaltime',str(1))
    return listitem

def unpack_query(query):
    expected_keys = ('title','tag','country','genre','actor','director','year','month','decade')
    criteria=json.loads(query)
    for key in expected_keys:
        if key not in criteria: criteria[key]= ''

    return criteria

def update_movie_cat():
    if _1CH.get_setting('auto-update-movies-cat') == "Featured":
        return str("featured")
    elif _1CH.get_setting('auto-update-movies-cat') == "Most Popular":
        return str("views")
    elif _1CH.get_setting('auto-update-movies-cat') == "Highly Rated":
        return str("ratings")
    elif _1CH.get_setting('auto-update-movies-cat') == "Date Released":
        return str("release")
    elif _1CH.get_setting('auto-update-movies-cat') == "Date Added":
        return str("date")

    return str("featured") # default

def jump_to_page(queries={}):
    pages = int(_1CH.queries['pages'])
    dialog = xbmcgui.Dialog()
    options = []
    for page in range(pages):
        label = 'Page %s' % str(page + 1)
        options.append(label)
    index = dialog.select('Skip to page', options)
    if index>-1:
        queries['page']=index+1
        url = _1CH.build_plugin_url(queries)
        builtin = 'Container.Update(%s)' % url
        xbmc.executebuiltin(builtin)

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
resume = _1CH.queries.get('resume', False)
primewire_url = _1CH.queries.get('primewire_url', '')

_1CH.log(_1CH.queries)
_1CH.log(sys.argv)

if mode == 'main':
    AddonMenu()
elif mode == "MovieAutoUpdate":
    builtin = "XBMC.Notification(Updating,Please wait...,5000,%s)" % xbmcaddon.Addon().getAddonInfo('icon')
    xbmc.executebuiltin(builtin)
    sort = update_movie_cat()
    section = 'movies'
    GetFilteredResults(section, genre, letter, sort, page)
elif mode == 'GetSources':
    import urlresolver

    get_sources(url, title, img, year, imdbnum, dialog)
elif mode == 'PlaySource':
    import urlresolver

    PlaySource(url, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume)
elif mode == 'PlayTrailer':
    import urlresolver

    PlayTrailer(url)
elif mode == 'BrowseListMenu':
    BrowseListMenu(section)
elif mode == 'BrowseAlphabetMenu':
    BrowseAlphabetMenu(section)
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
elif mode == 'GetSearchQueryAdvanced':
    GetSearchQueryAdvanced(section)
elif mode == 'GetSearchQueryDesc':
    GetSearchQueryDesc(section)
elif mode == 'Search':
    Search(section,query)
elif mode == 'SearchAdvanced':
    criteria = unpack_query(query)
    SearchAdvanced(section, criteria['title'], criteria['tag'], False, criteria['country'], criteria['genre'], criteria['actor'], criteria['director'], criteria['year'], criteria['month'], criteria['decade'])
elif mode == 'SearchDesc':
    SearchDesc(section,query)
elif mode == '7000':  # Enables Remote Search
    Search(section, query)
elif mode == 'browse_favorites':
    browse_favorites(section)
elif mode == 'browse_favorites_website':
    browse_favorites_website(section, page)
elif mode == 'SaveFav':
    save_favorite(section, title, url, img, year)
elif mode == 'DeleteFav':
    delete_favorite(url)
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
    metapacks.install_metapack(title)
elif mode == 'install_local_metapack':
    dialog = xbmcgui.Dialog()
    source = dialog.browse(1, 'Metapack', 'files', '.zip', False, False)
    metapacks.install_local_zip(source)
elif mode == 'add_to_library':
    add_to_library(video_type, url, title, img, year, imdbnum)
    builtin = "XBMC.Notification(Add to Library,Added '%s' to library,2000, %s)" % (title, ICON_PATH)
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
    jump_to_page({'mode': 'GetFilteredResults', 'section': section, 'genre': genre, 'letter': letter, 'sort': sort})
elif mode=='FavPageSelect':
    jump_to_page({'mode': 'browse_favorites_website', 'section': section})
elif mode == 'refresh_meta':
    utils.refresh_meta(video_type, title, imdbnum, alt_id, year)
elif mode == 'flush_cache':
    utils.flush_cache()
elif mode == 'migrateDB':
    utils.migrate_to_mysql()
elif mode == 'migrateFavs':
    migrate_favs_to_web()
elif mode == 'fav2Library':
    add_favs_to_library(section)
elif mode == 'Help':
    _1CH.log('Showing help popup')
    try: utils.TextBox()
    except: pass
    