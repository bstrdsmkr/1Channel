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
from pw_dispatcher import PW_Dispatcher

global urlresolver

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
ITEMS_PER_PAGE=24

AZ_DIRECTORIES = (ltr for ltr in string.ascii_uppercase)

pw_scraper = PW_Scraper(_1CH.get_setting("username"),_1CH.get_setting("passwd"))
GENRES = pw_scraper.get_genres()

db_connection = DB_Connection()
pw_dispatcher = PW_Dispatcher()

PREPARE_ZIP = False
__metaget__ = metahandlers.MetaData(preparezip=PREPARE_ZIP)

if not xbmcvfs.exists(_1CH.get_profile()): 
    try: xbmcvfs.mkdirs(_1CH.get_profile())
    except: os.mkdir(_1CH.get_profile())

def art(name): 
    return os.path.join(THEME_PATH, name)

@pw_dispatcher.register('SaveFav:  (fav_type, title, url, year)')
def save_favorite(fav_type, title, url, year):
    if fav_type != 'tv': fav_type = 'movie'
    _1CH.log('Saving Favorite type: %s name: %s url: %s year: %s' % (fav_type, title, url, year))
    
    try:
        if utils.website_is_integrated():
            pw_scraper.add_favorite(url)
        else:
            db_connection.save_favorite(fav_type, title, url, year)
        builtin = 'XBMC.Notification(Save Favorite,Added to Favorites,2000, %s)'
        xbmc.executebuiltin(builtin % ICON_PATH)
    except:
            builtin = 'XBMC.Notification(Save Favorite,Item already in Favorites,2000, %s)'
            xbmc.executebuiltin(builtin % ICON_PATH)

@pw_dispatcher.register('DeleteFav: (url)')
def delete_favorite(url):
    _1CH.log('Deleting Favorite: %s' % (url))
    
    if utils.website_is_integrated():
        pw_scraper.delete_favorite(url)
    else:
        db_connection.delete_favorite(url)
    xbmc.executebuiltin('Container.Refresh')

@pw_dispatcher.register('GetSources: (url, title, img, year, imdbnum) {dialog}')
def get_sources(url, title, img, year, imdbnum, dialog=False, respect_auto=True):
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
    if respect_auto and _1CH.get_setting('auto-play')=='true':
        auto_try_sources(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid)
        
    else: # autoplay is off, or respect_auto is False
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
                for _ in item['parts']:
                    label = utils.format_label_source_parts(item, partnum)
                    hosted_media = urlresolver.HostedMediaFile(url=item['parts'][partnum - 2], title=label)
                    sources.append(hosted_media)
                    partnum += 1
        except:
            _1CH.log('Error while trying to resolve %s' % item['url'])
    
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
    hosters_len = len(hosters)        
    for item in hosters:
        #_1CH.log(item)
        hosted_media = urlresolver.HostedMediaFile(url=item['url'])
        if hosted_media:
            label = utils.format_label_source(item)
            _1CH.add_directory({'mode': 'PlaySource', 'url': item['url'], 'title': title,
                                'img': img, 'year': year, 'imdbnum': imdbnum,
                                'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                               infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img, fanart=art('fanart.png'), total_items=hosters_len)
            if item['multi-part']:
                partnum = 2
                for part in item['parts']:
                    label = utils.format_label_source_parts(item, partnum)
                    partnum += 1
                    _1CH.add_directory({'mode': 'PlaySource', 'url': part, 'title': title,
                                        'img': img, 'year': year, 'imdbnum': imdbnum,
                                        'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                                       infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img,
                                       fanart=art('fanart.png'), total_items=hosters_len)
        else:
            _1CH.log('Skipping unresolvable source: %s' % (item['url']))
     
    _1CH.end_of_directory()

def play_unfiltered_dir(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume):
    hosters_len=len(hosters)
    for item in hosters:
        #_1CH.log(item)
        label = utils.format_label_source(item)
        _1CH.add_directory({'mode': 'PlaySource', 'url': item['url'], 'title': title,
                            'img': img, 'year': year, 'imdbnum': imdbnum,
                            'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                           infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img, fanart=art('fanart.png'), total_items=hosters_len)
        if item['multi-part']:
            partnum = 2
            for part in item['parts']:
                label = utils.format_label_source_parts(item, partnum)
                partnum += 1
                _1CH.add_directory({'mode': 'PlaySource', 'url': part, 'title': title,
                                    'img': img, 'year': year, 'imdbnum': imdbnum,
                                    'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                                   infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img,
                                   fanart=art('fanart.png'), total_items=hosters_len)
    
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

@pw_dispatcher.register('PlaySource: (url, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume)')    
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

@pw_dispatcher.register('ChangeWatched: (imdbnum, video_type, title, season, epsiode, primewire_url) {year, watched, dbid}')
def ChangeWatched(imdbnum, video_type, title, season, episode, primewire_url , year='', watched='', dbid=None):

    # meta['dbid'] only gets set for strms
    if dbid and int(dbid) > 0:
        if video_type == 'episode':
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodeDetails", "params": {"episodeid": %s, "properties": ["playcount"]}, "id": 1}'
            cmd = cmd %(dbid)
            result = json.loads(xbmc.executeJSONRPC(cmd))
            print result
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid": %s, "playcount": %s}, "id": 1}'
            playcount = int(result['result']['episodedetails']['playcount']) + 1
            cmd = cmd %(dbid, playcount)
            result = xbmc.executeJSONRPC(cmd)
            xbmc.log('PrimeWire: Marking episode .strm as watched: %s' %result)
        if video_type == 'movie':
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovieDetails", "params": {"movieid": %s, "properties": ["playcount"]}, "id": 1}'
            cmd = cmd %(dbid)
            result = json.loads(xbmc.executeJSONRPC(cmd))
            print result
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid": %s, "playcount": %s}, "id": 1}'
            playcount = int(result['result']['moviedetails']['playcount']) + 1
            cmd = cmd %(dbid, playcount)
            result = xbmc.executeJSONRPC(cmd)
            xbmc.log('PrimeWire: Marking movie .strm as watched: %s' %result)
            
    __metaget__.change_watched(video_type, title, imdbnum, season=season, episode=episode, year=year, watched=watched)

    if utils.website_is_integrated() : pw_scraper.change_watched(primewire_url, watched)
    xbmc.executebuiltin("XBMC.Container.Refresh")

@pw_dispatcher.register('PlayTrailer: (url)')
def PlayTrailer(url):
    url = url.decode('base-64')
    _1CH.log('Attempting to resolve and play trailer at %s' % url)
    sources = []
    hosted_media = urlresolver.HostedMediaFile(url=url)
    sources.append(hosted_media)
    source = urlresolver.choose_source(sources)
    stream_url = source.resolve() if source else ''
    xbmc.Player().play(stream_url)

@pw_dispatcher.register('GetSearchQuery: (section, next_mode)')
@pw_dispatcher.register('GetSearchQueryDesc: (section, next_mode)')
def GetSearchQuery(section, next_mode):
    paginate=(_1CH.get_setting('paginate-search')=='true' and _1CH.get_setting('paginate')=='true')
    keyboard = xbmc.Keyboard()
    if section == 'tv':
        keyboard.setHeading('Search TV Shows')
    else:
        keyboard.setHeading('Search Movies')
    while True:
        keyboard.doModal()
        if keyboard.isConfirmed():
            search_text = keyboard.getText()
            if not paginate and not search_text:
                _1CH.show_ok_dialog(['Blank searches are not allowed unless [B]Paginate Search Results[/B] is enabled.'], title='PrimeWire')
                continue
            else:
                break
        else:
            break
            
    if keyboard.isConfirmed():
        if search_text.startswith('!#'):
            if search_text == '!#create metapacks': metapacks.create_meta_packs()
            if search_text == '!#repair meta': repair_missing_images()
            if search_text == '!#install all meta': metapacks.install_all_meta()
            if search_text.startswith('!#sql:'):
                _1CH.log('Running SQL: |%s|' % (search_text[6:]))
                db_connection.execute_sql(search_text[6:])
        else:
            queries = {'mode': next_mode, 'section': section, 'query': keyboard.getText()}
            pluginurl = _1CH.build_plugin_url(queries)
            builtin = 'Container.Update(%s)' %(pluginurl)
            xbmc.executebuiltin(builtin)
    else:
        BrowseListMenu(section)

@pw_dispatcher.register('GetSearchQueryAdvanced: (section)')
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

@pw_dispatcher.register('Search: (mode, section, query) {page}')
@pw_dispatcher.register('SearchDesc: (mode, section, query) {page}')
@pw_dispatcher.register('SearchAdvanced: (mode, section, query) {page}')
@pw_dispatcher.register('7000: (section, query)')
def Search(mode, section, query, page=None):
    section_params = get_section_params(section)
    paginate=(_1CH.get_setting('paginate-search')=='true' and _1CH.get_setting('paginate')=='true')
    
    if mode=='Search':
        results=pw_scraper.search(section,query, page, paginate)
    elif mode=='SearchDesc':
        results=pw_scraper.search_desc(section,query, page, paginate)
    elif mode=='SearchAdvanced':
        criteria = utils.unpack_query(query)
        results=pw_scraper.search_advanced(section, criteria['title'], criteria['tag'], False, criteria['country'], criteria['genre'],
                                           criteria['actor'], criteria['director'], criteria['year'], criteria['month'], criteria['decade'], page=page, paginate=paginate)
        
    total_pages = pw_scraper.get_last_res_pages()
    total=pw_scraper.get_last_res_total()
    if paginate:
        if page != total_pages:
            total=ITEMS_PER_PAGE
        else:
            total=total % ITEMS_PER_PAGE
    
    resurls = []
    for result in results:
        if result['url'] not in resurls:
            resurls.append(result['url'])                
            create_item(section_params,result['title'],result['year'],result['img'],result['url'],totalItems=total)
    
    if not page: page = 1
    next_page = int(page) + 1

    if int(page) < int(total_pages) and paginate:
        label = 'Skip to Page...'
        command = _1CH.build_plugin_url(
            {'mode': 'SearchPageSelect', 'pages': total_pages, 'query': query, 'search': mode, 'section': section})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': 'Next Page >>'}
        _1CH.add_directory(
            {'mode': mode, 'query': query, 'page': next_page, 'section': section},
            meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)

    _1CH.end_of_directory()

@pw_dispatcher.register('main')
def AddonMenu():  # homescreen
    _1CH.log('Main Menu')
    db_connection.init_database()
    if utils.has_upgraded():
        _1CH.log('Showing update popup')
        utils.TextBox()
        adn = xbmcaddon.Addon('plugin.video.1channel')
        adn.setSetting('domain', 'http://www.primewire.ag')
        adn.setSetting('old_version', _1CH.get_version())
    _1CH.add_directory({'mode': 'BrowseListMenu', 'section': 'movie'}, {'title': 'Movies'}, img=art('movies.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'BrowseListMenu', 'section': 'tv'}, {'title': 'TV shows'}, img=art('television.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'ResolverSettings'}, {'title': 'Resolver Settings'}, img=art('settings.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': 'Help'}, {'title': 'Help'}, img=art('help.png'), fanart=art('fanart.png'))
    # _1CH.add_directory({'mode': 'test'},   {'title':  'Test'}, img=art('settings.png'), fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

@pw_dispatcher.register('BrowseListMenu: (section)')
def BrowseListMenu(section):
    _1CH.log('Browse Options')
    _1CH.add_directory({'mode': 'BrowseAlphabetMenu', 'section': section}, {'title': 'A-Z'}, img=art('atoz.png'),
                       fanart=art('fanart.png'))
    add_search_item({'mode': 'GetSearchQuery', 'section': section, 'next_mode': 'Search'}, 'Search')
    if utils.website_is_integrated():
        _1CH.add_directory({'mode': 'browse_favorites_website', 'section': section}, {'title': 'Website Favourites'},
                           img=art('favourites.png'), fanart=art('fanart.png'))                          
        _1CH.add_directory({'mode': 'browse_watched_website', 'section': section}, {'title': 'Website Watched List'},
                           img=art('watched.png'), fanart=art('fanart.png'))
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
    
    add_search_item({'mode': 'GetSearchQueryDesc', 'section': section, 'next_mode': 'SearchDesc'}, 'Search (+Description)')
    add_search_item({'mode': 'GetSearchQueryAdvanced', 'section': section}, 'Search (Advanced Search)')
    
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

# add searches as an items so they don't get added to the path history
# _1CH.add_item doesn't work because it insists on adding non-folder items as playable
def add_search_item(queries, label):
    liz = xbmcgui.ListItem(label=label, iconImage=art('search.png'), thumbnailImage=art('search.png'))
    liz.setProperty('fanart_image', art('fanart.png'))
    liz_url = _1CH.build_plugin_url(queries)
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

@pw_dispatcher.register('BrowseAlphabetMenu: (section)')
def BrowseAlphabetMenu(section=None):
    _1CH.log('Browse by alphabet screen')
    _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'alphabet', 'letter': '123'},
                       {'title': '#123'}, img=art('123.png'), fanart=art('fanart.png'))
    for character in AZ_DIRECTORIES:
        _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'alphabet', 'letter': character},
                           {'title': character}, img=art(character.lower() + '.png'), fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


@pw_dispatcher.register('BrowseByGenreMenu: (section)')
def BrowseByGenreMenu(section=None, letter=None): #2000
    print 'Browse by genres screen'
    for genre in GENRES:
        _1CH.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': '', 'genre': genre},
                           {'title': genre}, img=art(genre.lower() + '.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def add_contextsearchmenu(title, video_type, resurl=''):
    contextmenuitems = []
    nameonly=utils.filename_filter_out_year(title); #print 'nameonly:  '+nameonly
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
    if menu_items is None: menu_items=[]
    if section_params['nextmode']=='GetSources' and _1CH.get_setting('auto-play')=='true':
        queries = {'mode': 'SelectSources', 'title': title, 'url': url, 'img': img, 'imdbnum': imdbnum, 'video_type': section_params['video_type']}
        if _1CH.get_setting('source-win')=='Dialog':
            runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(queries)
        else:
            runstring = 'Container.Update(%s)' % _1CH.build_plugin_url(queries)
            
        menu_items.insert(0,('Select Source', runstring),)

    # fix episode url being added to subs
    if section_params['video_type']=='episode':
        temp_url=re.match('(/.*/).*',url).groups()[0]
    else:
        temp_url=url
    liz = build_listitem(section_params['section'], section_params['video_type'], title, year, img, temp_url, imdbnum, season, episode, extra_cms=menu_items, subs=section_params['subs'])
    img = liz.getProperty('img')
    imdbnum = liz.getProperty('imdb')
    if not section_params['folder']: # should only be when it's a movie and dialog are off and autoplay is off
        liz.setProperty('isPlayable','true')
    queries = {'mode': section_params['nextmode'], 'title': title, 'url': url, 'img': img, 'imdbnum': imdbnum, 'video_type': section_params['video_type'], 'year': year}
    liz_url = _1CH.build_plugin_url(queries)
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz,section_params['folder'],totalItems)

@pw_dispatcher.register('GetFilteredResults: (section) {genre, letter, sort, page}')
def GetFilteredResults(section=None, genre=None, letter=None, sort='alphabet', page=None, paginate=None):
    _1CH.log('Filtered results for Section: %s Genre: %s Letter: %s Sort: %s Page: %s Paginate: %s' % (section, genre, letter, sort, page, paginate))
    if paginate is None: paginate=(_1CH.get_setting('paginate-lists')=='true' and _1CH.get_setting('paginate')=='true')
    section_params = get_section_params(section)
    results = pw_scraper.get_filtered_results(section, genre, letter, sort, page, paginate)
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

    if int(page) < int(total_pages) and paginate:
        label = 'Skip to Page...'
        command = _1CH.build_plugin_url(
            {'mode': 'PageSelect', 'pages': total_pages, 'section': section, 'genre': genre, 'letter': letter,'sort': sort})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': 'Next Page >>'}
        _1CH.add_directory(
            {'mode': 'GetFilteredResults', 'section': section, 'genre': genre, 'letter': letter, 'sort': sort,
             'page': next_page},
            meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)

    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache')=='true')

@pw_dispatcher.register('TVShowSeasonList: (url, title, year) {tvdbnum}')
def TVShowSeasonList(url, title, year, old_imdb='', tvdbnum=''):
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
                try: _1CH.log('Title: %s Old IMDB: %s Old TVDB: %s New IMDB %s Year: %s' % (title, old_imdb, tvdbnum, new_imdbnum, year))
                except: pass
                __metaget__.update_meta('tvshow', title, old_imdb, tvdbnum, new_imdbnum)
            except:
                try: _1CH.log('Error while trying to update metadata with: %s, %s, %s, %s, %s' % (title, old_imdb, tvdbnum, new_imdbnum, year))
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
    
@pw_dispatcher.register('TVShowEpisodeList: (title, season, imdbnum)') # TVShowEpisodeList(title, season, imdbnum, tvdbnum)
def TVShowEpisodeList(title, season, imdbnum):
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

        create_item(section_params, title, '', '', epurl, imdbnum, season, epnum)

    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache')=='true')

def get_section_params(section):
    section_params={}
    section_params['section']=section
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

@pw_dispatcher.register('browse_favorites: (section)')
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

@pw_dispatcher.register('browse_favorites_website: (section) {page}')
def browse_favorites_website(section, page=None):
    if section=='movie': section='movies'
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
    paginate=(_1CH.get_setting('paginate-favs')=='true' and _1CH.get_setting('paginate')=='true')
    
    for fav in pw_scraper.get_favorities(section, page, paginate):
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': 'DeleteFav', 'section': section, 'title': fav['title'], 'url': fav['url'], 'year': fav['year']})
        menu_items = [('Delete Favorite', runstring)]
        create_item(section_params,fav['title'],fav['year'],fav['img'],fav['url'],menu_items=menu_items)
    
    total_pages=pw_scraper.get_last_res_pages()
    if not page: page = 1
    next_page = int(page)+1

    if int(page) < int(total_pages) and paginate:
        label = 'Skip to Page...'
        command = _1CH.build_plugin_url({'mode': 'FavPageSelect', 'section': section, 'pages': total_pages})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': 'Next Page >>'}
        _1CH.add_directory({'mode': 'browse_favorites_website', 'section': section, 'page': next_page}, meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)
        
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache')=='true')

@pw_dispatcher.register('migrateFavs')
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

@pw_dispatcher.register('fav2Library: (section)')
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

@pw_dispatcher.register('browse_watched_website: (section) {page}')    
def browse_watched_website(section, page=None):
    if section=='movie': section='movies'

    # TODO: Extend fav2Library
    # if section=='tv':
        # label='Add Watched TV Shows to Library'
    # else:
        # label='Add Watched Movies to Library'

    # liz = xbmcgui.ListItem(label=label)
    # liz_url = _1CH.build_plugin_url({'mode': 'fav2Library', 'section': section})
    # xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)
        

    section_params = get_section_params(section)
    paginate=(_1CH.get_setting('paginate-watched')=='true' and _1CH.get_setting('paginate')=='true')
    
    for video in pw_scraper.get_watched(section, page, paginate):
        deletestring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': 'ChangeWatched', 'section': section, 'title': video['title'], 'primewire_url': video['url'], 'year': video['year'], 'watched':6})
        #TODO: rewatchstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': 'add_watch', 'section': section, 'title': video['title'], 'primewire_url': video['url'], 'year': video['year']})
        menu_items = [('Delete Watched', deletestring)]
        create_item(section_params,video['title'],video['year'],video['img'],video['url'],menu_items=menu_items)
        
    total_pages=pw_scraper.get_last_res_pages()
    if not page: page = 1
    next_page = int(page)+1

    if int(page) < int(total_pages) and paginate:
        label = 'Skip to Page...'
        command = _1CH.build_plugin_url({'mode': 'WatchedPageSelect', 'section': section, 'pages': total_pages})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': 'Next Page >>'}
        _1CH.add_directory({'mode': 'browse_watched_website', 'section': section, 'page': next_page}, meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)
        
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache')=='true')

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

@pw_dispatcher.register('add_to_library: (video_type, url, title, img, year, imdbnum)')
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

    builtin = "XBMC.Notification(Add to Library,Added '%s' to library,2000, %s)" % (title, ICON_PATH)
    xbmc.executebuiltin(builtin)

@pw_dispatcher.register('add_subscription: (url, title, img, year, imdbnum)')
def add_subscription(url, title, img, year, imdbnum):
    try:
        days=utils.get_default_days()
        db_connection.add_subscription(url, title, img, year, imdbnum, days)
        add_to_library('tvshow', url, title, img, year, imdbnum)
        builtin = "XBMC.Notification(Subscribe,Subscribed to '%s',2000, %s)" % (title, ICON_PATH)
        xbmc.executebuiltin(builtin)
    except:
        builtin = "XBMC.Notification(Subscribe,Already subscribed to '%s',2000, %s)" % (title, ICON_PATH)
        xbmc.executebuiltin(builtin)
    xbmc.executebuiltin('Container.Update')


@pw_dispatcher.register('cancel_subscription: (url, title, img, year, imdbnum)')
def cancel_subscription(url, title, img, year, imdbnum):
    db_connection.delete_subscription(url)
    xbmc.executebuiltin('Container.Refresh')

@pw_dispatcher.register('update_subscriptions')
def update_subscriptions():
    day=datetime.datetime.now().weekday()
    subs=db_connection.get_subscriptions(day)
    for sub in subs:
        add_to_library('tvshow', sub[0], sub[1], sub[2], sub[3], sub[4])
    if _1CH.get_setting('library-update') == 'true':
        xbmc.executebuiltin('UpdateLibrary(video)')
    if _1CH.get_setting('cleanup-subscriptions') == 'true':
        clean_up_subscriptions()

@pw_dispatcher.register('clean_up_subscriptions')
def clean_up_subscriptions():
    _1CH.log('Cleaning up dead subscriptions')
    subs=db_connection.get_subscriptions()
    for sub in subs:
        meta = __metaget__.get_meta('tvshow', sub[1], year=sub[3])
        if meta['status'] == 'Ended':
            try: _1CH.log('Selecting %s  for removal' % sub[1])
            except: pass
            db_connection.delete_subscription(sub[0])

@pw_dispatcher.register('manage_subscriptions')
def manage_subscriptions():
    utils.set_view('tvshows', 'tvshows-view')
    liz = xbmcgui.ListItem(label='Update Subscriptions')
    liz_url = _1CH.build_plugin_url({'mode': 'update_subscriptions'})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)
    
    liz = xbmcgui.ListItem(label='Clean Up Subscriptions')
    liz_url = _1CH.build_plugin_url({'mode': 'clean_up_subscriptions'})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

    subs=db_connection.get_subscriptions(order_matters=True)
    subs_len=len(subs)
    for sub in subs:
        days=sub[5]
        days_string = utils.get_days_string_from_days(days)
        if days_string=='': days_string='DISABLED'
        days_format = _1CH.get_setting('format-sub-days')

        if '%s' in days_format:
            days_string = days_format % (days_string)
        else:
            _1CH.log('Ignoring subscription days format because %s is missing')
            
        meta = create_meta('tvshow', sub[1], sub[3], '')
        meta['title'] = utils.format_label_sub(meta)

        menu_items = add_contextsearchmenu(meta['title'], 'tv')
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(
            {'mode': 'edit_days', 'url': sub[0], 'days': days})
        menu_items.append(('Edit days', runstring,))
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(
            {'mode': 'cancel_subscription', 'url': sub[0], 'title': sub[1], 'img': sub[2], 'year': sub[3], 'imdbnum': sub[4]})
        menu_items.append(('Cancel subscription', runstring,))
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(
            {'mode': 'SaveFav', 'fav_type': 'tv', 'title': sub[1], 'url': sub[0], 'year': sub[3]})
        menu_items.append(('Add to Favorites', runstring,))
        menu_items.append(('Show Information', 'XBMC.Action(Info)',))

        if META_ON:
            try: fanart = meta['backdrop_url']
            except: fanart = art('fanart.png')
            try: img = meta['cover_url']
            except: img = ''
        else: fanart = art('fanart.png'); img = ''
        label = '[%s] %s' % (days_string, meta['title'])
        listitem = xbmcgui.ListItem(label, iconImage=img, thumbnailImage=img)
        listitem.setInfo('video', meta)
        listitem.setProperty('fanart_image', fanart)
        listitem.addContextMenuItems(menu_items, replaceItems=True)
        queries = {'mode': 'TVShowSeasonList', 'title': sub[1], 'url': sub[0], 'img': img, 'imdbnum': meta['imdb_id'], 'video_type': 'tvshow', 'year': sub[3]}
        li_url = _1CH.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem, isFolder=True, totalItems=subs_len)
    _1CH.end_of_directory()

def compose(inner_func, *outer_funcs):
    """Compose multiple unary functions together into a single unary function"""
    if not outer_funcs:
        return inner_func
    outer_func = compose(*outer_funcs)
    return lambda *args, **kwargs: outer_func(inner_func(*args, **kwargs))

def build_listitem(section, video_type, title, year, img, resurl, imdbnum='', season='', episode='', extra_cms=None, subs=None):
    if not subs: subs = []
    if not extra_cms: extra_cms = []
    menu_items = add_contextsearchmenu(title, section, resurl)
    menu_items = menu_items + extra_cms

    if video_type != 'episode' and 'Delete Favorite' not in [item[0] for item in menu_items]:
        queries = {'mode': 'SaveFav', 'fav_type': section, 'title': title, 'url': resurl, 'year': year}
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

        queries = {'mode': 'ChangeWatched', 'title': title, 'imdbnum': meta['imdb_id'], 'video_type': video_type, 'year': year, 'primewire_url': resurl, 'watched': new_status}
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

@pw_dispatcher.register('PageSelect: (mode, section) {genre, letter, sort}')
@pw_dispatcher.register('FavPageSelect: (mode, section)')
@pw_dispatcher.register('WatchedPageSelect: (mode, section)')
@pw_dispatcher.register('SearchPageSelect: (mode, section) {search, query}')
def jump_to_page(mode, section='', genre='', letter='', sort='', search='', query=''):
    if mode == 'PageSelect':
        queries={'mode': 'GetFilteredResults', 'section': section, 'genre': genre, 'letter': letter, 'sort': sort}
    elif mode=='FavPageSelect':
        queries={'mode': 'browse_favorites_website', 'section': section}
    elif mode=='WatchedPageSelect':
        queries={'mode': 'browse_watched_website', 'section': section}
    elif mode=='SearchPageSelect':
        queries={'mode': search, 'query': query, 'section': section}

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

@pw_dispatcher.register('export_db')
def export_db():
    try:
        dialog = xbmcgui.Dialog()
        export_path = dialog.browse(0, 'Select Export Directory', 'files')
        if export_path:
            keyboard = xbmc.Keyboard('export.csv', 'Enter Export Filename')
            keyboard.doModal()
            if keyboard.isConfirmed():
                export_filename = keyboard.getText()
                export_file = export_path + export_filename
                db_connection.export_from_db(export_file)
                builtin = "XBMC.Notification(Export Successful,Exported to %s,2000, %s)" % (export_file, ICON_PATH)
                xbmc.executebuiltin(builtin)
    except Exception as e:
        _1CH.log('Export Failed: %s' % (e))
        builtin = "XBMC.Notification(Export,Export Failed,2000, %s)" % (ICON_PATH)
        xbmc.executebuiltin(builtin)

@pw_dispatcher.register('import_db')
def import_db():
    try:
        dialog = xbmcgui.Dialog()
        import_file = dialog.browse(1, 'Select Import File', 'files')
        if import_file:
            db_connection.import_into_db(import_file)
            builtin = "XBMC.Notification(Import Success,Imported from %s,5000, %s)" % (import_file, ICON_PATH)
            xbmc.executebuiltin(builtin)
    except Exception as e:
        _1CH.log('Import Failed: %s' % (e))
        builtin = "XBMC.Notification(Import,Import Failed,2000, %s)" % (ICON_PATH)
        xbmc.executebuiltin(builtin)
        raise

@pw_dispatcher.register('backup_db')
def backup_db():
    path = xbmc.translatePath("special://database")
    now_str = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    full_path = path + 'db_backup_' + now_str +'.csv'
    db_connection.export_from_db(full_path)

@pw_dispatcher.register('edit_days: (url, days)')
def edit_days(url, days):
    try:
        # use a keyboard if the hidden setting is true
        if _1CH.get_setting('use-days-keyboard')=='true':
            keyboard = xbmc.Keyboard(utils.get_days_string_from_days(days), 'Days to update Subscription (e.g. MTWHFSaSu)')
            keyboard.doModal()
            if keyboard.isConfirmed():
                days_string=keyboard.getText()
                new_days=utils.get_days_from_days_string(days_string)
            else:
                raise # jump back
        else:
            new_days=utils.days_select(days)
            
        db_connection.edit_days(url, new_days)
        xbmc.executebuiltin('Container.Refresh')
    except: pass # if clicked cancel just abort

@pw_dispatcher.register('Help')
def show_help():
    _1CH.log('Showing help popup')
    try: utils.TextBox()
    except: pass

@pw_dispatcher.register('flush_cache')
def flush_cache():
        return utils.flush_cache()

@pw_dispatcher.register('install_metapack: (title)')
def install_metapack(title):
    metapacks.install_metapack(title)

@pw_dispatcher.register('install_local_metapack')
def install_local_metapack():
    dialog = xbmcgui.Dialog()
    source = dialog.browse(1, 'Metapack', 'files', '.zip', False, False)
    metapacks.install_local_zip(source)
        
@pw_dispatcher.register('movie_update: (section, genre, letter, sort, page)')
def movie_update(section, genre, letter, sort, page):
    builtin = "XBMC.Notification(Updating,Please wait...,5000,%s)" % xbmcaddon.Addon().getAddonInfo('icon')
    xbmc.executebuiltin(builtin)
    sort = update_movie_cat()
    section = 'movies'
    GetFilteredResults(section, genre, letter, sort, page, paginate=True)

@pw_dispatcher.register('SelectSources: (url, title, img, year, imdbnum, dialog)')
def select_sources(url, title, img, year, imdbnum, dialog):
    get_sources(url, title, img, year, imdbnum, dialog, False)

@pw_dispatcher.register('refresh_meta: (video_type, title, imdbnum, alt_id, year)')
def refresh_meta(video_type, title, imdbnum, alt_id, year):
    utils.refresh_meta(video_type, title, imdbnum, alt_id, year)

@pw_dispatcher.register('9998')
def metahandler_settings():
    import metahandler  
    metahandler.display_settings()

@pw_dispatcher.register('ResolverSettings')
def resolver_settings():
    urlresolver.display_settings()
        
def main(argv=None):
    if sys.argv: argv=sys.argv

    _1CH.log(_1CH.queries)
    _1CH.log(argv)
    mode = _1CH.queries.get('mode', None)
    if mode in ['GetSources', 'PlaySource', 'PlayTrailer', 'ResolverSettings']:
        global urlresolver
        import urlresolver
        
    pw_dispatcher.dispatch(mode, _1CH.queries)

if __name__ == '__main__':
    sys.exit(main())
