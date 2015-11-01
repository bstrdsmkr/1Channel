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
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import xbmcplugin
from addon.common.addon import Addon
import utils
from utils import i18n
try: from metahandler import metahandlers
except: utils.notify(i18n('import_failed'), 'metahandler')
from urllib2 import HTTPError
from pw_scraper import PW_Scraper, PW_Error
from db_utils import DB_Connection
from pw_dispatcher import PW_Dispatcher
from utils import MODES
from utils import SUB_TYPES
import gui_utils

global urlresolver

_1CH = Addon('plugin.video.1channel', sys.argv)

META_ON = _1CH.get_setting('use-meta') == 'true'
FANART_ON = _1CH.get_setting('enable-fanart') == 'true'
USE_POSTERS = _1CH.get_setting('use-posters') == 'true'
POSTERS_FALLBACK = _1CH.get_setting('posters-fallback') == 'true'
THEME_LIST = ['Classic', 'Glossy_Black', 'PrimeWire', 'Firestorm']
THEME = THEME_LIST[int(_1CH.get_setting('theme'))]
if xbmc.getCondVisibility('System.HasAddon(script.1channel.themepak)'):
    themepak_path = xbmcaddon.Addon('script.1channel.themepak').getAddonInfo('path')
else:
    themepak_path = ''
THEME_PATH = os.path.join(themepak_path, 'art', 'themes', THEME)

FAV_ACTIONS = utils.enum(ADD='add', REMOVE='remove')
PL_SORT = ['added', 'alphabet', 'popularity']
REMOVE_TW_MENU = i18n('remove_tw_menu')
REMOVE_W_MENU = i18n('remove_w_menu')
REMOVE_FAV_MENU = i18n('remove_fav_menu')

pw_scraper = PW_Scraper(_1CH.get_setting("username"), _1CH.get_setting("passwd"))
db_connection = DB_Connection()
pw_dispatcher = PW_Dispatcher()

__metaget__ = metahandlers.MetaData()

if not xbmcvfs.exists(_1CH.get_profile()):
    try: xbmcvfs.mkdirs(_1CH.get_profile())
    except: os.mkdir(_1CH.get_profile())

def art(name):
    path = os.path.join(THEME_PATH, name)
    if not xbmcvfs.exists(path):
        path = path.replace('.png', '.jpg')
    return path

@pw_dispatcher.register(MODES.SAVE_FAV, ['fav_type', 'title', 'url'], ['year'])
def save_favorite(fav_type, title, url, year=''):
    if fav_type != 'tv': fav_type = 'movie'
    utils.log('Saving Favorite type: %s name: %s url: %s year: %s' % (fav_type, title, url, year))

    try:
        if utils.website_is_integrated():
            pw_scraper.add_favorite(url)
        else:
            db_connection.save_favorite(fav_type, title, url, year)
        msg = i18n('added_to_favs')
    except:
        msg = i18n('already_in_favs')
    utils.notify(msg=msg % (title), duration=5000)
    xbmc.executebuiltin('Container.Refresh')

@pw_dispatcher.register(MODES.DEL_FAV, ['url'])
def delete_favorite(url):
    utils.log('Deleting Favorite: %s' % (url))

    if utils.website_is_integrated():
        pw_scraper.delete_favorite(url)
    else:
        db_connection.delete_favorite(url)
    utils.notify(msg=i18n('fav_removed'), duration=3000)
    xbmc.executebuiltin('Container.Refresh')

# returns true if user chooses to resume, else false
def get_resume_choice(url):
    question = i18n('resume_from') % (utils.format_time(db_connection.get_bookmark(url)))
    return xbmcgui.Dialog().yesno(i18n('resume_question'), question, '', '', i18n('start_from_beginning'), i18n('resume')) == 1

@pw_dispatcher.register(MODES.GET_SOURCES, ['url', 'title'], ['year', 'img', 'imdbnum', 'dialog'])
def get_sources(url, title, year='', img='', imdbnum='', dialog=None, respect_auto=True):
    url = urllib.unquote(url)
    utils.log('Getting sources from: %s' % url)
    primewire_url = url

    resume = False
    if db_connection.bookmark_exists(url):
        resume = get_resume_choice(url)

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
        imdbnum = pw_scraper.get_last_imdbnum()
        __metaget__.update_meta('movie', title, imdb_id='', new_imdb_id=imdbnum, year=year)

    _img = xbmc.getInfoImage('ListItem.Thumb')
    if _img != "":
        img = _img

    hosters = pw_scraper.get_sources(url)

    if not hosters:
        _1CH.show_ok_dialog([i18n('no_sources')], title='PrimeWire')
        return

    dbid = get_dbid(video_type, title, season, episode, year)

    # auto play is on
    if respect_auto and _1CH.get_setting('auto-play') == 'true':
        auto_try_sources(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid)

    else:  # autoplay is off, or respect_auto is False
        # dialog is either True, False or None -- source-win is either Dialog or Directory
        # If dialog is forced, or there is no force and it's set to dialog use the dialog
        if dialog or (dialog is None and _1CH.get_setting('source-win') == 'Dialog'):
            if _1CH.get_setting('filter-source') == 'true':
                play_filtered_dialog(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid)

            else:
                play_unfiltered_dialog(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid)
        # if dialog is forced off (0), or it's None, but source-win is Directory, then use a directory
        else:
            if _1CH.get_setting('filter-source') == 'true':
                play_filtered_dir(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume)

            else:
                play_unfiltered_dir(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume)

def get_dbid(video_type, title, season='', episode='', year=''):
    dbid = 0
    filter = ''
    # variable used to match title with closest len, if there is more than one match, the one with the closest title length is the winner,
    # The Middle and Malcolm in the Middle in the same library would still match the corret title. Starts at high value and lowers
    max_title_len_diff = 1000
    titleComp2 = re.sub('[^a-zA-Z0-9]+', '', title).lower()
    # if it's a movie check if the titles match in the library, then pull the movieid
    if video_type == 'movie':
        if year: filter = '"filter": {"field": "year", "operator": "is", "value": "%s"},' % year
        json_string = '{"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetMovies", "params": {%s "properties": ["title"], "limits": {"end": 10000}}}' % filter
        result_key = "movies"
        id_key = "movieid"
        title_key = "title"
    # if it'a a tvshow episode filter out all tvshows which contain said season and episode, then match tvshow title
    if video_type == 'episode':
        filter = '"filter": {"and":['
        if year: filter += '{"field": "year", "operator": "is", "value": "%s"},' % year
        filter += '{"field": "season", "operator": "is", "value": "%s"},' % season
        filter += '{"field": "episode", "operator": "is", "value": "%s"}]},' % episode
        json_string = '{"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetEpisodes", "params": {%s "properties": ["showtitle"], "limits": {"end": 10000}}}' % (filter)
        result_key = "episodes"
        id_key = "episodeid"
        title_key = "showtitle"
    result = xbmc.executeJSONRPC(json_string)
    resultObj = json.loads(result)
    if not ('result' in resultObj and result_key in resultObj['result']): return None
    for item in resultObj['result'][result_key]:
        # converts titles to only alpha numeric, then compares smallest title to largest title, for example
        # 'Adventure Time' would match to 'Adventure tIME with FiNn and Jake_ (en) (4214)'
        titleComp1 = re.sub('[^a-zA-Z0-9]+', '', item[title_key]).lower()
        found_match = 0
        if len(titleComp1) > len(titleComp2):
            if titleComp2 in titleComp1: found_match = 1
        else:
            if titleComp1 in titleComp2: found_match = 1
        if found_match:
            title_len_diff = abs(len(titleComp1) - len(titleComp2))
            if title_len_diff <= max_title_len_diff:
                max_title_len_diff = title_len_diff
                if video_type == 'movie':
                    dbid = item[id_key]
                    utils.log('successfully matched dbid to movieid %s' % (dbid), xbmc.LOGDEBUG)
                if video_type == 'episode':
                    dbid = item[id_key]
                    utils.log('successfully matched dbid to episodeid %s' % (dbid), xbmc.LOGDEBUG)
    if dbid:
        return dbid
    else:
        utils.log('Failed to recover dbid, type: %s, title: %s, season: %s, episode: %s' % (video_type, title, season, episode), xbmc.LOGDEBUG)
        return None

def play_filtered_dialog(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid):
    sources = []
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
            utils.log('Error while trying to resolve %s' % item['url'], xbmc.LOGERROR)

    source = urlresolver.choose_source(sources)
    if source:
        source = source.get_url()
    else:
        return

    PlaySource(source, title, video_type, primewire_url, resume, imdbnum, year, season, episode, dbid)

def play_unfiltered_dialog(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid):
    sources = []
    for item in hosters:
        label = utils.format_label_source(item)
        sources.append(label)

    dialog = xbmcgui.Dialog()
    index = dialog.select(i18n('choose_stream'), sources)
    if index > -1:
        PlaySource(hosters[index]['url'], title, video_type, primewire_url, resume, imdbnum, year, season, episode, dbid)
    else:
        return

def play_filtered_dir(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume):
    hosters_len = len(hosters)
    for item in hosters:
        # utils.log(item)
        hosted_media = urlresolver.HostedMediaFile(url=item['url'])
        if hosted_media:
            label = utils.format_label_source(item)
            _1CH.add_directory({'mode': MODES.PLAY_SOURCE, 'url': item['url'], 'title': title,
                                'img': img, 'year': year, 'imdbnum': imdbnum,
                                'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                               infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img, fanart=art('fanart.png'), total_items=hosters_len)
            if item['multi-part']:
                partnum = 2
                for part in item['parts']:
                    label = utils.format_label_source_parts(item, partnum)
                    partnum += 1
                    _1CH.add_directory({'mode': MODES.PLAY_SOURCE, 'url': part, 'title': title,
                                        'img': img, 'year': year, 'imdbnum': imdbnum,
                                        'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                                       infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img,
                                       fanart=art('fanart.png'), total_items=hosters_len)
        else:
            utils.log('Skipping unresolvable source: %s' % (item['url']), xbmc.LOGWARNING)

    _1CH.end_of_directory()

def play_unfiltered_dir(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume):
    hosters_len = len(hosters)
    for item in hosters:
        # utils.log(item)
        label = utils.format_label_source(item)
        _1CH.add_directory({'mode': MODES.PLAY_SOURCE, 'url': item['url'], 'title': title,
                            'img': img, 'year': year, 'imdbnum': imdbnum,
                            'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                           infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img, fanart=art('fanart.png'), total_items=hosters_len)
        if item['multi-part']:
            partnum = 2
            for part in item['parts']:
                label = utils.format_label_source_parts(item, partnum)
                partnum += 1
                _1CH.add_directory({'mode': MODES.PLAY_SOURCE, 'url': part, 'title': title,
                                    'img': img, 'year': year, 'imdbnum': imdbnum,
                                    'video_type': video_type, 'season': season, 'episode': episode, 'primewire_url': primewire_url, 'resume': resume},
                                   infolabels={'title': label}, properties={'resumeTime': str(0), 'totalTime': str(1)}, is_folder=False, img=img,
                                   fanart=art('fanart.png'), total_items=hosters_len)

    _1CH.end_of_directory()

def auto_try_sources(hosters, title, img, year, imdbnum, video_type, season, episode, primewire_url, resume, dbid):
    dlg = xbmcgui.DialogProgress()
    line1 = i18n('trying_source')
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
            utils.log('Trying Source: %s' % (source['host']), xbmc.LOGDEBUG)
            if not PlaySource(source['url'], title, video_type, primewire_url, resume, imdbnum, year, season, episode, dbid):
                dlg.update(percent, i18n('playback_failed') % (label), line1 + label)
                utils.log('Source Failed: %s' % (source['host']), xbmc.LOGWARNING)
                count += 1
            else:
                success = True
                break  # Playback was successful, break out of the loop
        else:
            utils.log('All sources failed to play', xbmc.LOGERROR)
            dlg.close()
            _1CH.show_ok_dialog([i18n('all_sources_failed')], title='PrimeWire')
            break

@pw_dispatcher.register(MODES.PLAY_SOURCE, ['url', ' title', 'video_type', 'primewire_url', 'resume'], ['imdbnum', 'year', 'season', 'episode'])
def PlaySource(url, title, video_type, primewire_url, resume, imdbnum='', year='', season='', episode='', dbid=None):
    utils.log('Attempting to play url: %s' % url)
    stream_url = urlresolver.HostedMediaFile(url=url).resolve()

    # If urlresolver returns false then the video url was not resolved.
    if not stream_url or not isinstance(stream_url, basestring):
        try: msg = stream_url.msg
        except: msg = url
        utils.notify(msg=i18n('link_resolve_failed') % (msg), duration=7500)
        return False

    win = xbmcgui.Window(10000)
    win.setProperty('1ch.playing.title', title)
    win.setProperty('1ch.playing.year', year)
    win.setProperty('1ch.playing.imdb', imdbnum)
    win.setProperty('1ch.playing.season', str(season))
    win.setProperty('1ch.playing.episode', str(episode))
    win.setProperty('1ch.playing.url', primewire_url)

    # metadata is enabled
    if META_ON:
        if not dbid or int(dbid) <= 0:
            # we're not playing from a library item
            if video_type == 'episode':
                meta = __metaget__.get_episode_meta(title, imdbnum, season, episode)
                meta['TVShowTitle'] = title
                meta['title'] = utils.format_tvshow_episode(meta)
            elif video_type == 'movie':
                meta = __metaget__.get_meta('movie', title, year=year)
                meta['title'] = utils.format_label_movie(meta)
    else:  # metadata is not enabled
        if video_type == 'episode':
            meta = {'label': title, 'TVShowTitle': title, 'year': year, 'season': int(season), 'episode': int(episode), 'title': '%sx%s' % (season, episode)}
        else:
            meta = {'label': title, 'title': title, 'year': year}

    if dbid and int(dbid) > 0:
        # we're playing from a library item
        if video_type == 'episode':
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodeDetails", "params": {"episodeid" : %s, "properties" : ["title", "plot", "votes", "rating", "writer", "firstaired", "playcount", "runtime", "director", "productioncode", "season", "episode", "originaltitle", "showtitle", "lastplayed", "fanart", "thumbnail", "dateadded", "art"]}, "id": 1}'
            cmd = cmd % (dbid)
            meta = xbmc.executeJSONRPC(cmd)
            meta = json.loads(meta)
            meta = meta['result']['episodedetails']
            meta['TVShowTitle'] = meta['showtitle']
            meta['duration'] = meta['runtime']
            meta['premiered'] = meta['firstaired']
            meta['DBID'] = dbid
            meta['backdrop_url'] = meta['fanart']
            meta['cover_url'] = meta['thumbnail']
            if 'art' in meta:
                meta['banner_url'] = meta['art']['tvshow.banner']
                del meta['art']

        if video_type == 'movie':
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovieDetails", "params": {"movieid" : %s, "properties" : ["title", "plot", "votes", "rating", "writer", "playcount", "runtime", "director", "originaltitle", "lastplayed", "fanart", "thumbnail", "file", "year", "dateadded"]}, "id": 1}'
            cmd = cmd % (dbid)
            meta = xbmc.executeJSONRPC(cmd)
            meta = json.loads(meta)
            meta = meta['result']['moviedetails']
            meta['duration'] = meta['runtime']
            meta['DBID'] = dbid
            meta['backdrop_url'] = meta['fanart']
            meta['cover_url'] = meta['thumbnail']

    utils.log('ids meta is: imdbnum: %s; meta: %s' % (imdbnum, meta), xbmc.LOGDEBUG)
    ids = {}
    if imdbnum:
        ids = {'imdb': imdbnum}
    else:
        if 'imdb_id' in meta:
            ids.update({'imdb': meta['imdb_id']})
        if 'tmdb_id' in meta:
            ids.update({'tmdb': meta['tmdb_id']})
        if 'tvdb_id' in meta:
            ids.update({'tvdb': meta['tvdb_id']})
    if ids:
        win.setProperty('script.trakt.ids', json.dumps(ids))

    win = xbmcgui.Window(10000)
    win.setProperty('1ch.playing', json.dumps(meta))

    art = make_art(video_type, meta)
    listitem = xbmcgui.ListItem(path=url, iconImage=art['thumb'], thumbnailImage=art['thumb'])
    listitem.setProperty('fanart_image', art['fanart'])
    try: listitem.setArt(art)
    except: pass  # method doesn't exist in Frodo

    resume_point = 0
    if resume:
        resume_point = db_connection.get_bookmark(primewire_url)

    utils.log("Playing Video from: %s secs" % (resume_point), xbmc.LOGDEBUG)
    listitem.setProperty('ResumeTime', str(resume_point))
    listitem.setProperty('Totaltime', str(99999))  # dummy value to force resume to work

    listitem.setProperty('IsPlayable', 'true')
    listitem.setInfo(type="Video", infoLabels=meta)

    if _1CH.get_setting('enable-axel') == 'true':
        utils.log('Using Axel Downloader', xbmc.LOGDEBUG)
        try:
            download_name = title
            if season and episode: download_name += ' %sx%s' % (season, episode)
            import axelproxy as proxy
            axelhelper = proxy.ProxyHelper()
            stream_url, download_id = axelhelper.create_proxy_url(stream_url, name=download_name)
            win.setProperty('download_id', str(download_id))
            utils.log('Axel Downloader: stream_url: %s, download_id: %s' % (stream_url, download_id), xbmc.LOGDEBUG)
        except:
            utils.notify(i18n('axel_failed'), duration=10000)

    listitem.setPath(stream_url)
    xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, listitem)
    return True

@pw_dispatcher.register(MODES.CH_WATCH, ['video_type', 'title', 'primewire_url', 'watched'], ['imdbnum', 'season', 'episode', 'year', 'dbid'])
def change_watched(video_type, title, primewire_url, watched, imdbnum='', season='', episode='', year='', dbid=None):
    if watched == True:
        overlay = 7
        whattodo = 'add'
    else:
        whattodo = 'delete'
        overlay = 6

    # meta['dbid'] only gets set for strms
    if dbid and int(dbid) > 0:
        if video_type == 'episode':
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodeDetails", "params": {"episodeid": %s, "properties": ["playcount"]}, "id": 1}'
            cmd = cmd % (dbid)
            result = json.loads(xbmc.executeJSONRPC(cmd))
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid": %s, "playcount": %s}, "id": 1}'
            playcount = int(result['result']['episodedetails']['playcount']) + 1 if watched == True else 0
            cmd = cmd % (dbid, playcount)
            result = xbmc.executeJSONRPC(cmd)
            xbmc.log('PrimeWire: Marking episode .strm as watched: %s' % result)
        if video_type == 'movie':
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovieDetails", "params": {"movieid": %s, "properties": ["playcount"]}, "id": 1}'
            cmd = cmd % (dbid)
            result = json.loads(xbmc.executeJSONRPC(cmd))
            cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid": %s, "playcount": %s}, "id": 1}'
            playcount = int(result['result']['moviedetails']['playcount']) + 1 if watched == True else 0
            cmd = cmd % (dbid, playcount)
            result = xbmc.executeJSONRPC(cmd)
            xbmc.log('PrimeWire: Marking movie .strm as watched: %s' % result)

    __metaget__.change_watched(video_type, title, imdbnum, season=season, episode=episode, year=year, watched=overlay)

    if utils.website_is_integrated():
        change_watched_website(primewire_url, whattodo, refresh=False)

    xbmc.executebuiltin("XBMC.Container.Refresh")

@pw_dispatcher.register(MODES.CH_WATCH_WEB, ['primewire_url', 'action'], ['refresh'])
def change_watched_website(primewire_url, action, refresh=True):
    if utils.website_is_integrated():
        pw_scraper.change_watched(primewire_url, "watched", action)
        if refresh: xbmc.executebuiltin("XBMC.Container.Refresh")

@pw_dispatcher.register(MODES.CH_TOWATCH_WEB, ['primewire_url', 'action'], ['refresh'])
def change_towatch_website(primewire_url, action, refresh=True):
    if utils.website_is_integrated():
        pw_scraper.change_watched(primewire_url, "towatch", action)
        if refresh: xbmc.executebuiltin("XBMC.Container.Refresh")

@pw_dispatcher.register(MODES.PLAY_TRAILER, ['url'])
def PlayTrailer(url):
    url = url.decode('base-64')
    url = 'http://www.youtube.com/watch?v=%s&hd=1' % (url)
    utils.log('Attempting to resolve and play trailer at %s' % url)
    sources = []
    hosted_media = urlresolver.HostedMediaFile(url=url)
    sources.append(hosted_media)
    source = urlresolver.choose_source(sources)
    stream_url = source.resolve() if source else ''
    xbmc.Player().play(stream_url)

@pw_dispatcher.register(MODES.SEARCH_QUERY, ['section', 'next_mode'])
@pw_dispatcher.register(MODES.DESC_QUERY, ['section', 'next_mode'])
def GetSearchQuery(section, next_mode):
    paginate = (_1CH.get_setting('paginate-search') == 'true' and _1CH.get_setting('paginate') == 'true')
    keyboard = xbmc.Keyboard()
    if section == 'tv':
        keyboard.setHeading(i18n('search_tv'))
    else:
        keyboard.setHeading(i18n('search_movies'))
    while True:
        keyboard.doModal()
        if keyboard.isConfirmed():
            search_text = keyboard.getText()
            if not paginate and not search_text:
                _1CH.show_ok_dialog([i18n('blank_searches')], title='PrimeWire')
                return
            else:
                break
        else:
            break

    if keyboard.isConfirmed():
        if search_text.startswith('!#'):
            if search_text == '!#repair meta': repair_missing_images()
            if search_text.startswith('!#sql:'):
                utils.log('Running SQL: |%s|' % (search_text[6:]), xbmc.LOGDEBUG)
                db_connection.execute_sql(search_text[6:])
        else:
            queries = {'mode': next_mode, 'section': section, 'query': keyboard.getText()}
            pluginurl = _1CH.build_plugin_url(queries)
            builtin = 'Container.Update(%s)' % (pluginurl)
            xbmc.executebuiltin(builtin)
    else:
        BrowseListMenu(section)

@pw_dispatcher.register(MODES.ADV_QUERY, ['section'])
def GetSearchQueryAdvanced(section):
    try:
        query = gui_utils.get_adv_search_query(section)
        js_query = json.dumps(query)
        queries = {'mode': MODES.SEARCH_ADV, 'section': section, 'query': js_query}
        pluginurl = _1CH.build_plugin_url(queries)
        builtin = 'Container.Update(%s)' % (pluginurl)
        xbmc.executebuiltin(builtin)
    except:
        BrowseListMenu(section)

@pw_dispatcher.register(MODES.SEARCH, ['mode', 'section'], ['query', 'page'])
@pw_dispatcher.register(MODES.SEARCH_DESC, ['mode', 'section'], ['query', 'page'])
@pw_dispatcher.register(MODES.SEARCH_ADV, ['mode', 'section'], ['query', 'page'])
@pw_dispatcher.register(MODES.REMOTE_SEARCH, ['section'], ['query'])
def Search(mode, section, query='', page=None):
    section_params = get_section_params(section)
    paginate = (_1CH.get_setting('paginate-search') == 'true' and _1CH.get_setting('paginate') == 'true')

    try:
        if mode == MODES.SEARCH:
            results = pw_scraper.search(section, query, page, paginate)
        elif mode == MODES.SEARCH_DESC:
            results = pw_scraper.search_desc(section, query, page, paginate)
        elif mode == MODES.SEARCH_ADV:
            criteria = utils.unpack_query(query)
            results = pw_scraper.search_advanced(section, criteria['title'], criteria['tag'], False, criteria['country'], criteria['genre'],
                                               criteria['actor'], criteria['director'], criteria['year'], criteria['month'], criteria['decade'], page=page, paginate=paginate)
    except PW_Error:
        utils.notify(i18n('site_blocked'), duration=10000)
        return

    total_pages = pw_scraper.get_last_res_pages()
    total = pw_scraper.get_last_res_total()
    if paginate:
        if page != total_pages:
            total = PW_Scraper.ITEMS_PER_PAGE
        else:
            total = total % PW_Scraper.ITEMS_PER_PAGE

    resurls = []
    for result in results:
        if result['url'] not in resurls:
            resurls.append(result['url'])
            create_item(section_params, result['title'], result['year'], result['img'], result['url'], totalItems=total)

    if not page: page = 1
    next_page = int(page) + 1

    if int(page) < int(total_pages) and paginate:
        label = i18n('skip_to_page') + '...'
        command = _1CH.build_plugin_url(
            {'mode': MODES.SEARCH_PAGE_SELECT, 'pages': total_pages, 'query': query, 'search': mode, 'section': section})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': i18n('next_page') + ' >>'}
        _1CH.add_directory(
            {'mode': mode, 'query': query, 'page': next_page, 'section': section},
            meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)

    utils.set_view(section_params['content'], '%s-view' % (section_params['content']))
    _1CH.end_of_directory()

# temporary method to fix bad urls
def fix_urls():
    tables = ['favorites', 'subscriptions', 'external_subs']
    for table in tables:
        # remove any possible dupes
        while True:
            rows = db_connection.execute_sql("SELECT url from %s GROUP BY REPLACE(url,'-online-free','') HAVING COUNT(*)>1" % (table))
            if rows:
                db_connection.execute_sql("DELETE FROM %s WHERE url in (SELECT * FROM (SELECT url from %s GROUP BY REPLACE(url,'-online-free','') HAVING COUNT(*)>1) as t)" % (table, table))
            else:
                break

        # strip the -online-free part of the url off
        db_connection.execute_sql("UPDATE %s SET url=REPLACE(url,'-online-free','') WHERE SUBSTR(url, -12)='-online-free'" % (table))

@pw_dispatcher.register(MODES.MAIN)
def AddonMenu():  # homescreen
    utils.log('Main Menu')
    db_connection.init_database()
    fix_urls()
    if utils.has_upgraded():
        utils.log('Showing update popup', xbmc.LOGDEBUG)
        if _1CH.get_setting('show_splash') == 'true':
            msg = (i18n('popup_msg_line1') + '\n\n' + i18n('popup_msg_line2') + '\n\n' + i18n('popup_msg_line3'))
            gui_utils.do_My_TextSplash(msg, HowLong=20, TxtColor='0xFF00FF00', BorderWidth=45)
        utils.TextBox()
        adn = xbmcaddon.Addon('plugin.video.1channel')
        adn.setSetting('domain', 'http://www.primewire.ag')
        adn.setSetting('old_version', _1CH.get_version())
    _1CH.add_directory({'mode': MODES.LIST_MENU, 'section': 'movie'}, {'title': i18n('movies')}, img=art('movies.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.LIST_MENU, 'section': 'tv'}, {'title': i18n('tv_shows')}, img=art('television.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.PLAYLISTS_MENU, 'section': 'playlist'}, {'title': i18n('playlists')}, img=art('playlists.png'),
                       fanart=art('fanart.png'))

    if _1CH.get_setting('h99_hidden') == 'true':
        _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': 'tv', 'sort': 'date'}, {'title': 'TV - Date added'}, img=art('date_added.png'), fanart=art('fanart.png'))
        _1CH.add_directory({'mode': MODES.MANAGE_SUBS}, {'title': 'TV - Subscriptions'}, img=art('subscriptions.png'), fanart=art('fanart.png'))
        add_search_item({'mode': MODES.SEARCH_QUERY, 'section': 'tv', 'next_mode': MODES.SEARCH}, 'TV - Search')
        _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': 'movie', 'sort': 'date'}, {'title': 'Movies - Date added'}, img=art('date_added.png'), fanart=art('fanart.png'))
        _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': 'movie', 'sort': 'release'}, {'title': 'Movies - Date released'}, img=art('date_released.png'), fanart=art('fanart.png'))
        _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': 'movie', 'sort': 'featured'}, {'title': 'Movies - Featured'}, img=art('featured.png'), fanart=art('fanart.png'))
        _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': 'movie', 'sort': 'views'}, {'title': 'Movies - Most Popular'}, img=art('most_popular.png'), fanart=art('fanart.png'))
        add_search_item({'mode': MODES.SEARCH_QUERY, 'section': 'movie', 'next_mode': MODES.SEARCH}, 'Movies - Search')

    if not xbmc.getCondVisibility('System.HasAddon(script.1channel.themepak)') and xbmc.getCondVisibility('System.HasAddon(plugin.program.addoninstaller)'):
        _1CH.add_directory({'mode': MODES.INSTALL_THEMES}, {'title': i18n('install_themepak')}, img=art('settings.png'), fanart=art('fanart.png'))

    _1CH.add_directory({'mode': MODES.RES_SETTINGS}, {'title': i18n('resolver_settings')}, img=art('settings.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.HELP}, {'title': i18n('help')}, img=art('help.png'), fanart=art('fanart.png'))
    # _1CH.add_directory({'mode': 'test'},   {'title':  'Test'}, img=art('settings.png'), fanart=art('fanart.png'))

    utils.set_view('list', '%s-view' % ('default'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=False)

@pw_dispatcher.register(MODES.INSTALL_THEMES)
def install_themes():
    addon = 'plugin://plugin.program.addoninstaller'
    query = {'mode': 'addoninstall', 'name': '1Channel.thempak', \
           'url': 'https://offshoregit.com/tknorris/tknorris-release-repo/raw/master/zips/script.1channel.themepak/script.1channel.themepak-0.0.3.zip', \
           'description': 'none', 'filetype': 'addon', 'repourl': 'none'}
    run = 'RunPlugin(%s)' % (addon + '?' + urllib.urlencode(query))
    xbmc.executebuiltin(run)

@pw_dispatcher.register(MODES.LIST_MENU, ['section'])
def BrowseListMenu(section):
    utils.log('Browse Options')
    _1CH.add_directory({'mode': MODES.AZ_MENU, 'section': section}, {'title': i18n('atoz')}, img=art('atoz.png'), fanart=art('fanart.png'))
    add_search_item({'mode': MODES.SEARCH_QUERY, 'section': section, 'next_mode': MODES.SEARCH}, i18n('search'))
    if utils.website_is_integrated():
        _1CH.add_directory({'mode': MODES.BROWSE_FAVS_WEB, 'section': section}, {'title': i18n('web_favs')}, img=art('favourites.png'), fanart=art('fanart.png'))
        _1CH.add_directory({'mode': MODES.BROWSE_W_WEB, 'section': section}, {'title': i18n('web_watched')}, img=art('watched.png'), fanart=art('fanart.png'))
        _1CH.add_directory({'mode': MODES.BROWSE_TW_WEB, 'section': section}, {'title': i18n('web_towatch')}, img=art('towatch.png'), fanart=art('fanart.png'))
        if section == 'tv':
            _1CH.add_directory({'mode': MODES.SHOW_SCHEDULE}, {'title': i18n('my_tv_schedule')}, img=art('schedule.png'), fanart=art('fanart.png'))
    else:
        _1CH.add_directory({'mode': MODES.BROWSE_FAVS, 'section': section}, {'title': i18n('favs')}, img=art('favourites.png'), fanart=art('fanart.png'))

    if section == 'tv':
        _1CH.add_directory({'mode': MODES.MANAGE_SUBS}, {'title': i18n('subscriptions')}, img=art('subscriptions.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.GENRE_MENU, 'section': section}, {'title': i18n('genres')}, img=art('genres.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': section, 'sort': 'featured'}, {'title': i18n('featured')}, img=art('featured.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': section, 'sort': 'views'}, {'title': i18n('most_popular')}, img=art('most_popular.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': section, 'sort': 'ratings'}, {'title': i18n('highly_rated')}, img=art('highly_rated.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': section, 'sort': 'release'}, {'title': i18n('date_released')}, img=art('date_released.png'), fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': section, 'sort': 'date'}, {'title': i18n('date_added')}, img=art('date_added.png'), fanart=art('fanart.png'))

    add_search_item({'mode': MODES.DESC_QUERY, 'section': section, 'next_mode': MODES.SEARCH_DESC}, i18n('search_desc'))
    add_search_item({'mode': MODES.ADV_QUERY, 'section': section}, i18n('search_adv'))

    utils.set_view('list', '%s-view' % ('default'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

@pw_dispatcher.register(MODES.PLAYLISTS_MENU)
def playlist_menu():
    utils.log('Playlist Menu')
    _1CH.add_directory({'mode': MODES.BROWSE_PLAYLISTS, 'public': True, 'sort': 'date'}, {'title': i18n('pub_date')}, img=art('public_playlists_date.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.BROWSE_PLAYLISTS, 'public': True, 'sort': 'rating'}, {'title': i18n('pub_rating')}, img=art('public_playlists_rating.png'),
                       fanart=art('fanart.png'))
    _1CH.add_directory({'mode': MODES.BROWSE_PLAYLISTS, 'public': True, 'sort': 'hits'}, {'title': i18n('pub_views')}, img=art('public_playlists_views.png'),
                       fanart=art('fanart.png'))
    if utils.website_is_integrated():
        _1CH.add_directory({'mode': MODES.BROWSE_PLAYLISTS, 'public': False, 'sort': 'date'}, {'title': i18n('private_date')}, img=art('personal_playlists_date.png'),
                           fanart=art('fanart.png'))
        _1CH.add_directory({'mode': MODES.BROWSE_PLAYLISTS, 'public': False, 'sort': 'rating'}, {'title': i18n('private_rating')}, img=art('personal_playlists_rating.png'),
                           fanart=art('fanart.png'))
        _1CH.add_directory({'mode': MODES.BROWSE_PLAYLISTS, 'public': False, 'sort': 'hits'}, {'title': i18n('private_views')}, img=art('personal_playlists_views.png'),
                           fanart=art('fanart.png'))
    utils.set_view('list', '%s-view' % ('default'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

@pw_dispatcher.register(MODES.BROWSE_PLAYLISTS, ['public'], ['sort', 'page'])
def browse_playlists(public, sort=None, page=None, paginate=True):
    utils.log('Browse Playlists: public: |%s| sort: |%s| page: |%s| paginate: |%s|' % (public, sort, page, paginate))
    playlists = pw_scraper.get_playlists(public, sort, page, paginate)
    total_pages = pw_scraper.get_last_res_pages()
    for playlist in playlists:
        title = '%s (%s %s) (%s %s) (%s %s)' % (playlist['title'].encode('ascii', 'ignore'), playlist['item_count'], i18n('items'), playlist['views'], i18n('views'), i18n('rating'), playlist['rating'])
        _1CH.add_directory({'mode': MODES.SHOW_PLAYLIST, 'url': playlist['url'], 'public': public}, {'title': title}, img=playlist['img'], fanart=art('fanart.png'))

    if not page: page = 1
    next_page = int(page) + 1

    if int(page) < int(total_pages) and paginate:
        label = i18n('skip_to_page') + '...'
        command = _1CH.build_plugin_url(
            {'mode': MODES.PL_PAGE_SELECT, 'section': 'playlist', 'pages': total_pages, 'public': public, 'sort': sort})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': i18n('next_page') + ' >>'}
        _1CH.add_directory(
            {'mode': MODES.BROWSE_PLAYLISTS, 'public': public, 'sort': sort, 'page': next_page},
            meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)

    utils.set_view('list', 'default-view')
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

@pw_dispatcher.register(MODES.SHOW_PLAYLIST, ['url', 'public'])
def show_playlist(url, public):
    sort = PL_SORT[int(_1CH.get_setting('playlist-sort'))]
    items = pw_scraper.show_playlist(url, public, sort)

    # one playlist can contain both movies and tvshows so can't set the params for the whole playlist/section
    item_params = {}
    item_params['subs'] = [row[0] for row in get_subscriptions()]
    if utils.website_is_integrated():
        item_params['fav_urls'] = []
    else:
        item_params['fav_urls'] = get_fav_urls()
    item_params['xbmc_fav_urls'] = utils.get_xbmc_fav_urls()
    for item in items:
        item_params.update(get_item_params(item))

        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.RM_FROM_PL, 'playlist_url': url, 'item_url': item['url']})
        menu_items = [(i18n('remove_from_playlist'), runstring)]

        create_item(item_params, item['title'], item['year'], item['img'], item['url'], menu_items=menu_items)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

@pw_dispatcher.register(MODES.ADD2PL, ['item_url'])
def add_to_playlist(item_url):
    playlists = pw_scraper.get_playlists(False)
    sel_list = []
    url_list = []
    for playlist in playlists:
        title = '%s (%s %s) (%s %s) (%s %s)' % (playlist['title'], playlist['item_count'], i18n('items'), playlist['views'], i18n('views'), i18n('rating'), playlist['rating'])
        sel_list.append(title)
        url_list.append(playlist['url'])

    if sel_list:
        dialog = xbmcgui.Dialog()
        ret = dialog.select(i18n('select_a_list'), sel_list)
        if ret > -1:
            try:
                pw_scraper.add_to_playlist(url_list[ret], item_url)
                message = i18n('added_to_list')
            except:
                message = i18n('error_item_list')
            utils.notify(message, duration=4000)
    else:
        utils.notify(i18n('create_list_first'), duration=4000)

@pw_dispatcher.register(MODES.RM_FROM_PL, ['playlist_url', 'item_url'])
def remove_from_playlist(playlist_url, item_url):
    pw_scraper.remove_from_playlist(playlist_url, item_url)
    xbmc.executebuiltin('Container.Refresh')

# add searches as an items so they don't get added to the path history
# _1CH.add_item doesn't work because it insists on adding non-folder items as playable
def add_search_item(queries, label):
    liz = xbmcgui.ListItem(label=label, iconImage=art('search.png'), thumbnailImage=art('search.png'))
    liz.setProperty('IsPlayable', 'false')
    liz.setProperty('fanart_image', art('fanart.png'))
    liz.setInfo('video', {'title': label})
    liz_url = _1CH.build_plugin_url(queries)
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

@pw_dispatcher.register(MODES.AZ_MENU, ['section'])
def BrowseAlphabetMenu(section=None):
    utils.log('Browse by alphabet screen')
    _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': section, 'sort': 'alphabet', 'letter': '123'},
                       {'title': '#123'}, img=art('123.png'), fanart=art('fanart.png'))
    for character in (ltr for ltr in string.ascii_uppercase):
        _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': section, 'sort': 'alphabet', 'letter': character},
                           {'title': character}, img=art(character.lower() + '.png'), fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


@pw_dispatcher.register(MODES.GENRE_MENU, ['section'])
def BrowseByGenreMenu(section=None):  # 2000
    utils.log('Browse by genres screen')
    for genre in pw_scraper.get_genres():
        _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': section, 'sort': 'date', 'genre': genre}, {'title': genre}, img=art(genre.lower() + '.png'), fanart=art('fanart.png'))
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def get_item_params(item):
    item_params = {}
    if item['video_type'] == 'movie':
        item_params['section'] = 'movies'
        item_params['nextmode'] = MODES.GET_SOURCES
        item_params['video_type'] = 'movie'
        item_params['folder'] = (_1CH.get_setting('source-win') == 'Directory' and _1CH.get_setting('auto-play') == 'false')
    else:
        item_params['section'] = 'tv'
        item_params['nextmode'] = MODES.SEASON_LIST
        item_params['video_type'] = 'tvshow'
        item_params['folder'] = True
    return item_params

def get_section_params(section):
    section_params = {}
    section_params['section'] = section
    if section == 'tv':
        section_params['content'] = 'tvshows'
        section_params['nextmode'] = MODES.SEASON_LIST
        section_params['video_type'] = 'tvshow'
        section_params['folder'] = True
        subscriptions = get_subscriptions()
        section_params['subs'] = [row[0] for row in subscriptions]
    elif section == 'episode':
        section_params['nextmode'] = MODES.GET_SOURCES
        section_params['video_type'] = 'episode'
        section_params['content'] = 'episodes'
        section_params['folder'] = (_1CH.get_setting('source-win') == 'Directory' and _1CH.get_setting('auto-play') == 'false')
        section_params['subs'] = []
    elif section == 'calendar':
        section_params['nextmode'] = MODES.GET_SOURCES
        section_params['video_type'] = 'episode'
        section_params['content'] = 'calendar'
        section_params['folder'] = (_1CH.get_setting('source-win') == 'Directory' and _1CH.get_setting('auto-play') == 'false')
        section_params['subs'] = []
    else:
        section_params['content'] = 'movies'
        section_params['nextmode'] = MODES.GET_SOURCES
        section_params['video_type'] = 'movie'
        section_params['folder'] = (_1CH.get_setting('source-win') == 'Directory' and _1CH.get_setting('auto-play') == 'false')
        section_params['subs'] = []

    # only grab actual fav_urls if not using website favs (otherwise too much site load)
    if utils.website_is_integrated():
        section_params['fav_urls'] = []
    else:
        section_params['fav_urls'] = get_fav_urls(section)
    section_params['xbmc_fav_urls'] = utils.get_xbmc_fav_urls()

    return section_params

def create_item(section_params, title, year, img, url, imdbnum='', season='', episode='', day='', totalItems=0, menu_items=None):
    # utils.log('Create Item: %s, %s, %s, %s, %s, %s, %s, %s, %s' % (section_params, title, year, img, url, imdbnum, season, episode, totalItems))
    if menu_items is None: menu_items = []
    if section_params['nextmode'] == MODES.GET_SOURCES and _1CH.get_setting('auto-play') == 'true':
        queries = {'mode': MODES.SELECT_SOURCES, 'title': title, 'url': url, 'img': img, 'imdbnum': imdbnum, 'video_type': section_params['video_type'], 'year': year}
        if _1CH.get_setting('source-win') == 'Dialog':
            runstring = 'PlayMedia(%s)' % _1CH.build_plugin_url(queries)
        else:
            runstring = 'Container.Update(%s)' % _1CH.build_plugin_url(queries)

        menu_items.insert(0, (i18n('select_source'), runstring),)

    # fix episode url being added to subs
    if section_params['video_type'] == 'episode':
        temp_url = re.match('(/.*/).*', url).groups()[0]
    else:
        temp_url = url

    liz, menu_items = build_listitem(section_params, title, year, img, temp_url, imdbnum, season, episode, day=day, extra_cms=menu_items)
    img = liz.getProperty('img')
    imdbnum = liz.getProperty('imdb')
    if not section_params['folder']:  # should only be when it's a movie and dialog are off and autoplay is off
        liz.setProperty('isPlayable', 'true')
    queries = {'mode': section_params['nextmode'], 'title': title, 'url': url, 'img': img, 'imdbnum': imdbnum, 'video_type': section_params['video_type'], 'year': year}
    liz_url = _1CH.build_plugin_url(queries)

    if utils.in_xbmc_favs(liz_url, section_params['xbmc_fav_urls']):
        action = FAV_ACTIONS.REMOVE
        label = i18n('remove_from_xbmc_favs')
    else:
        action = FAV_ACTIONS.ADD
        label = i18n('add_to_xbmc_favs')
    runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.TOGGLE_X_FAVS, 'title': liz.getLabel(), 'url': liz_url, 'img': img, 'is_playable': liz.getProperty('isPlayable') == 'true', 'action': action})
    menu_items.insert(0, (label, runstring),)

    liz.addContextMenuItems(menu_items, replaceItems=True)
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, section_params['folder'], totalItems)

def build_listitem(section_params, title, year, img, resurl, imdbnum='', season='', episode='', day='', extra_cms=None):
    if not extra_cms: extra_cms = []
    menu_items = extra_cms

    # fav_urls is only populated when local favs are used
    if resurl in section_params['fav_urls']:
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.DEL_FAV, 'section': section_params['section'], 'title': title, 'url': resurl, 'year': year})
        menu_items.append((REMOVE_FAV_MENU, runstring),)
    # will show add to favs always when using website favs and not on favorites view;
    # but only when item isn't in favs when using local favs
    elif REMOVE_FAV_MENU not in [menu[0] for menu in menu_items]:
        queries = {'mode': MODES.SAVE_FAV, 'fav_type': section_params['section'], 'title': title, 'url': resurl, 'year': year}
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(queries)
        menu_items.append((i18n('add_to_favs'), runstring),)

    if resurl and utils.website_is_integrated():
        if REMOVE_TW_MENU not in (item[0] for item in menu_items):
            watchstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.CH_TOWATCH_WEB, 'primewire_url': resurl, 'action': 'add', 'refresh': True})
            menu_items.append((i18n('add_to_towatch'), watchstring),)

        if REMOVE_W_MENU not in (item[0] for item in menu_items):
            watchedstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.CH_WATCH_WEB, 'primewire_url': resurl, 'action': 'add', 'refresh': True})
            menu_items.append((i18n('add_to_watch'), watchedstring),)

    queries = {'mode': MODES.ADD2LIB, 'video_type': section_params['video_type'], 'title': title, 'img': img, 'year': year,
               'url': resurl}
    runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(queries)
    menu_items.append((i18n('add_to_library'), runstring),)

    if utils.website_is_integrated():
        queries = {'mode': MODES.ADD2PL, 'item_url': resurl}
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(queries)
        menu_items.append((i18n('add_to_playlist'), runstring),)

    if section_params['video_type'] in ('tv', 'tvshow', 'episode'):
        if resurl not in section_params['subs']:
            queries = {'mode': MODES.ADD_SUB, 'video_type': section_params['video_type'], 'url': resurl, 'title': title, 'img': img, 'year': year}
            runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(queries)
            menu_items.append((i18n('subscribe'), runstring),)
        else:
            runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.CANCEL_SUB, 'url': resurl})
            menu_items.append((i18n('cancel_subscription'), runstring,))
    else:
        plugin_str = 'plugin://plugin.video.couchpotato_manager'
        plugin_str += '/movies/add?title=%s' % title
        runstring = 'XBMC.RunPlugin(%s)' % plugin_str
        menu_items.append((i18n('add_to_cp'), runstring),)

    if META_ON:
        if section_params['video_type'] == 'episode':
            meta = __metaget__.get_episode_meta(title, imdbnum, season, episode)
            meta['TVShowTitle'] = title
        else:
            meta = create_meta(section_params['video_type'], title, year)

        menu_items.append((i18n('show_information'), 'XBMC.Action(Info)'),)

        queries = {'mode': MODES.REFRESH_META, 'video_type': section_params['video_type'], 'title': meta['title'], 'imdbnum': meta['imdb_id'],
                   'alt_id': 'imdbnum', 'year': year}
        runstring = _1CH.build_plugin_url(queries)
        runstring = 'RunPlugin(%s)' % runstring
        menu_items.append((i18n('refresh_metadata'), runstring,))

        if 'trailer_url' in meta and meta['trailer_url']:
            try:
                url = meta['trailer_url']
                url = url.encode('base-64').strip()
                runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.PLAY_TRAILER, 'url': url})
                menu_items.append((i18n('watch_trailer'), runstring,))
            except: pass

        if meta['overlay'] == 6:
            label = i18n('mark_as_watched')
            watched = True
        else:
            label = i18n('mark_as_unwatched')
            watched = False

        queries = {'mode': MODES.CH_WATCH, 'title': title, 'imdbnum': meta['imdb_id'], 'video_type': section_params['video_type'], 'year': year, 'primewire_url': resurl, 'watched': watched}
        if section_params['video_type'] in ('tv', 'tvshow', 'episode'):
            queries['season'] = season
            queries['episode'] = episode
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url(queries)
        menu_items.append((label, runstring,))

        if section_params['video_type'] == 'tvshow':
            if resurl in section_params['subs']:
                meta['title'] = utils.format_label_sub(meta)
            else:
                meta['title'] = utils.format_label_tvshow(meta)

            # save the playcount for ep counts; delete it to prevent tvshow being marked as watched
            if 'playcount' in meta:
                playcount = meta['playcount']
                del meta['playcount']
        elif section_params['video_type'] == 'episode':
            if section_params['content'] == 'calendar':
                meta['title'] = '[[COLOR deeppink]%s[/COLOR]] %s - S%02dE%02d - %s' % (day, title, int(season), int(episode), meta['title'])
            else:
                meta['title'] = utils.format_tvshow_episode(meta)
        else:
            meta['title'] = utils.format_label_movie(meta)

        art = make_art(section_params['video_type'], meta, img)
        listitem = xbmcgui.ListItem(meta['title'], iconImage=art['thumb'], thumbnailImage=art['thumb'])
        listitem.setProperty('fanart_image', art['fanart'])
        imdbnum = meta['imdb_id']
        try: listitem.setArt(art)
        except: pass  # method doesn't exist in Frodo

        # set tvshow episode counts
        if section_params['video_type'] == 'tvshow' and 'episode' in meta:
            total_episodes = meta['episode']
            unwatched_episodes = total_episodes - playcount
            watched_episodes = total_episodes - unwatched_episodes
            listitem.setProperty('TotalEpisodes', str(total_episodes))
            listitem.setProperty('WatchedEpisodes', str(watched_episodes))
            listitem.setProperty('UnWatchedEpisodes', str(unwatched_episodes))

    else:  # Metadata off
        temp_title = re.sub(' \(\d{4}\)$', '', title)
        meta = {'TVShowTitle': temp_title, 'tvshowtitle': temp_title, 'title': temp_title, 'year': year, 'premiered': year}
        if section_params['video_type'] == 'episode':
            meta.update({'title': '', 'season': int(season), 'episode': int(episode)})
            if section_params['content'] == 'calendar':
                disp_title = '[[COLOR deeppink]%s[/COLOR]] %s - S%02dE%02d' % (day, temp_title, int(season), int(episode))
            else:
                disp_title = utils.format_tvshow_episode(meta)
                meta.update({'title': disp_title})
        else:
            if section_params['video_type'] == 'tvshow':
                if resurl in section_params['subs']:
                    disp_title = utils.format_label_sub(meta)
                else:
                    disp_title = utils.format_label_tvshow(meta)
            else:
                disp_title = utils.format_label_movie(meta)

        # print '|%s||%s||%s||%s|' % (temp_title, title, year, disp_title)
        listitem = xbmcgui.ListItem(disp_title, iconImage=img, thumbnailImage=img)

    listitem.setProperty('imdb', imdbnum)
    listitem.setInfo('video', meta)
    listitem.setProperty('img', img)

    # Hack resumetime & totaltime to prevent XBMC from popping up a resume dialog if a native bookmark is set. UGH!
    listitem.setProperty('resumetime', str(0))
    listitem.setProperty('totaltime', str(1))
    return (listitem, menu_items)

@pw_dispatcher.register(MODES.FILTER_RESULTS, ['section'], ['genre', 'letter', 'sort', 'page'])
def GetFilteredResults(section, genre='', letter='', sort='alphabet', page=None, paginate=None):
    utils.log('Filtered results for Section: %s Genre: %s Letter: %s Sort: %s Page: %s Paginate: %s' % (section, genre, letter, sort, page, paginate))
    if paginate is None: paginate = (_1CH.get_setting('paginate-lists') == 'true' and _1CH.get_setting('paginate') == 'true')
    section_params = get_section_params(section)
    results = pw_scraper.get_filtered_results(section, genre, letter, sort, page, paginate)
    total_pages = pw_scraper.get_last_res_pages()

    resurls = []
    count = 0
    win = xbmcgui.Window(10000)
    for result in results:
        # resurl, title, year, thumb = s.groups()
        if result['url'] not in resurls:
            resurls.append(result['url'])
            create_item(section_params, result['title'], result['year'], result['img'], result['url'])

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
        command = _1CH.build_plugin_url({'mode': MODES.FILTER_RESULTS, 'section': section, 'sort': sort, 'title': _1CH.get_setting('auto-update-movies-cat'), 'page': '1'})
        win.setProperty('1ch.movie.more.title', "More")
        win.setProperty('1ch.movie.more.path', command)

    if not page: page = 1
    next_page = int(page) + 1

    if int(page) < int(total_pages) and paginate:
        label = i18n('skip_to_page') + '...'
        command = _1CH.build_plugin_url(
            {'mode': MODES.PAGE_SELECT, 'pages': total_pages, 'section': section, 'genre': genre, 'letter': letter, 'sort': sort})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': i18n('next_page') + ' >>'}
        _1CH.add_directory({'mode': MODES.FILTER_RESULTS, 'section': section, 'genre': genre, 'letter': letter, 'sort': sort, 'page': next_page},
            meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)

    utils.set_view(section_params['content'], '%s-view' % (section_params['content']))
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache') == 'true')

@pw_dispatcher.register(MODES.SEASON_LIST, ['url', 'title'], ['year', 'tvdbnum'])
def TVShowSeasonList(url, title, year='', old_imdb='', tvdbnum=''):
    utils.log('Seasons for TV Show %s' % url)
    season_gen = pw_scraper.get_season_list(url)
    seasons = list(season_gen)  # copy the generator into a list so that we can iterate over it multiple times
    new_imdbnum = pw_scraper.get_last_imdbnum()

    imdbnum = old_imdb
    if META_ON:
        if not old_imdb and new_imdbnum:
            utils.log('Imdb ID not recieved from title search, updating with new id of %s' % new_imdbnum)
            try:
                utils.log('Title: %s Old IMDB: %s Old TVDB: %s New IMDB %s Year: %s' % (title, old_imdb, tvdbnum, new_imdbnum, year), xbmc.LOGDEBUG)
                __metaget__.update_meta('tvshow', title, old_imdb, tvdbnum, new_imdbnum)
            except:
                utils.log('Error while trying to update metadata with: %s, %s, %s, %s, %s' % (title, old_imdb, tvdbnum, new_imdbnum, year), xbmc.LOGERROR)
            imdbnum = new_imdbnum

        season_nums = [season[0] for season in seasons]
        season_meta = __metaget__.get_seasons(title, imdbnum, season_nums)

    num = 0
    seasons_found = False
    for season in seasons:
        seasons_found = True
        season_num, season_html = season

        if META_ON:
            meta = season_meta[num]
        else:
            meta = {}

        label = '%s %s' % (i18n('season'), season_num)
        db_connection.cache_season(season_num, season_html)
        art = make_art('tvshow', meta)
        listitem = xbmcgui.ListItem(label, iconImage=art['thumb'], thumbnailImage=art['thumb'])
        listitem.setInfo('video', meta)
        listitem.setProperty('fanart_image', art['fanart'])
        try: listitem.setArt(art)
        except: pass  # method doesn't exist in Frodo
        listitem.addContextMenuItems([], replaceItems=True)
        queries = {'mode': MODES.EPISODE_LIST, 'season': season_num, 'year': year, 'imdbnum': imdbnum, 'title': title}
        li_url = _1CH.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem, isFolder=True, totalItems=len(seasons))

        num += 1

    if not seasons_found:
        utils.log("No Seasons Found for %s at %s" % (title, url), xbmc.LOGERROR)
        utils.notify(msg=i18n('no_season_found') % (title), duration=3000)
        return

    xbmcplugin.endOfDirectory(int(sys.argv[1]))
    utils.set_view('seasons', 'seasons-view')

@pw_dispatcher.register(MODES.EPISODE_LIST, ['title', 'season'], ['imdbnum', 'year'])  # TVShowEpisodeList(title, season, imdbnum, tvdbnum)
def TVShowEpisodeList(title, season, imdbnum='', year=''):
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

        create_item(section_params, title, year, '', epurl, imdbnum, season, epnum)

    utils.set_view(section_params['content'], '%s-view' % (section_params['content']))
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache') == 'true')

def get_fav_urls(fav_type=None):
    if utils.website_is_integrated():
        if fav_type is None:
            favs = pw_scraper.get_favorites('movies')
            fav_urls = [fav['url'] for fav in favs]
            favs = pw_scraper.get_favorites('tv')
            fav_urls += [fav['url'] for fav in favs]
        else:
            favs = pw_scraper.get_favorites(fav_type)
            fav_urls = [fav['url'] for fav in favs]
    else:
        favs = db_connection.get_favorites(fav_type)
        fav_urls = [fav[2] for fav in favs]
    return fav_urls

@pw_dispatcher.register(MODES.BROWSE_FAVS, ['section'])
def browse_favorites(section):
    if not section: section = 'movie'
    favs = db_connection.get_favorites(section)

    section_params = get_section_params(section)
    if section == 'tv':
        label = i18n('add_fav_tv_to_library')
    else:
        label = i18n('add_fav_movies_to_library')

    liz = xbmcgui.ListItem(label=label)
    liz_url = _1CH.build_plugin_url({'mode': MODES.FAV2LIB, 'section': section})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

    for row in favs:
        _, title, favurl, year = row

        create_item(section_params, title, year, '', favurl)
    utils.set_view(section_params['content'], '%s-view' % (section_params['content']))
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache') == 'true')

@pw_dispatcher.register(MODES.BROWSE_FAVS_WEB, ['section'], ['page'])
def browse_favorites_website(section, page=None):
    if section == 'movie': section = 'movies'
    local_favs = db_connection.get_favorites_count()

    if local_favs:
        liz = xbmcgui.ListItem(label='Upload Local Favorites')
        liz_url = _1CH.build_plugin_url({'mode': MODES.MIG_FAVS})
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

    if section == 'tv':
        label = i18n('add_fav_tv_to_library')
    else:
        label = i18n('add_fav_movies_to_library')

    liz = xbmcgui.ListItem(label=label)
    liz_url = _1CH.build_plugin_url({'mode': MODES.FAV2LIB, 'section': section})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

    section_params = get_section_params(section)
    paginate = (_1CH.get_setting('paginate-favs') == 'true' and _1CH.get_setting('paginate') == 'true')

    for fav in pw_scraper.get_favorites(section, page, paginate):
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.DEL_FAV, 'section': section_params['section'], 'title': fav['title'], 'url': fav['url'], 'year': fav['year']})
        menu_items = [(REMOVE_FAV_MENU, runstring), ]

        create_item(section_params, fav['title'], fav['year'], fav['img'], fav['url'], menu_items=menu_items)

    total_pages = pw_scraper.get_last_res_pages()
    if not page: page = 1
    next_page = int(page) + 1

    if int(page) < int(total_pages) and paginate:
        label = i18n('skip_to_page') + '...'
        command = _1CH.build_plugin_url({'mode': MODES.FAV_PAGE_SELECT, 'section': section, 'pages': total_pages})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': i18n('next_page') + ' >>'}
        _1CH.add_directory({'mode': MODES.BROWSE_FAVS_WEB, 'section': section, 'page': next_page}, meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)

    utils.set_view(section_params['content'], '%s-view' % (section_params['content']))
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache') == 'true')

@pw_dispatcher.register(MODES.MIG_FAVS)
def migrate_favs_to_web():
    progress = xbmcgui.DialogProgress()
    ln1 = i18n('upload_favs_to_pw')
    progress.create(i18n('uploading_favs'), ln1)
    successes = []
    all_favs = db_connection.get_favorites()
    fav_len = len(all_favs)
    count = 0
    for fav in all_favs:
        if progress.iscanceled(): return
        title = fav[1]
        favurl = fav[2]
        try:
            pw_scraper.add_favorite(favurl)
            ln3 = i18n('success')
            utils.log('%s added successfully' % title, xbmc.LOGDEBUG)
            successes.append((title, favurl))
        except Exception as e:
            ln3 = i18n('already_exists')
            utils.log(e, xbmc.LOGDEBUG)
        count += 1
        progress.update(count * 100 / fav_len, ln1, i18n('processed') % title, ln3)
    progress.close()
    dialog = xbmcgui.Dialog()
    ln1 = i18n('remove_successful')
    ln2 = i18n('upload_local')
    ln3 = i18n('cannot_be_undone')
    yes = i18n('keep')
    no = i18n('delete')
    ret = dialog.yesno(i18n('migration_complete'), ln1, ln2, ln3, yes, no)
    # failures = [('title1','url1'), ('title2','url2'), ('title3','url3'), ('title4','url4'), ('title5','url5'), ('title6','url6'), ('title7','url7')]
    if ret:
        db_connection.delete_favorites([fav[1] for fav in successes])
    xbmc.executebuiltin("XBMC.Container.Refresh")

@pw_dispatcher.register(MODES.FAV2LIB, ['section'])
def add_favs_to_library(section):
    if not section: section = 'movie'
    section_params = get_section_params(section)
    if utils.website_is_integrated():
        for fav in pw_scraper.get_favorites(section, paginate=False):
            add_to_library(section_params['video_type'], fav['url'], fav['title'], fav['img'], fav['year'], '')
    else:
        favs = db_connection.get_favorites(section)

        for fav in favs:
            _, title, url, year = fav
            add_to_library(section_params['video_type'], url, title, '', year, '')

    if section == 'tv':
        message = i18n('fav_tv_added_to_library')
    else:
        message = i18n('fav_movies_added_to_library')
    utils.notify(msg=message, duration=4000)

@pw_dispatcher.register(MODES.BROWSE_W_WEB, ['section'], ['page'])
def browse_watched_website(section, page=None):
    if section == 'movie': section = 'movies'

    # TODO: Extend fav2Library
    # if section=='tv':
        # label='Add Watched TV Shows to Library'
    # else:
        # label='Add Watched Movies to Library'

    # liz = xbmcgui.ListItem(label=label)
    # liz_url = _1CH.build_plugin_url({'mode': MODES.FAV2LIB, 'section': section})
    # xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

    section_params = get_section_params(section)
    paginate = (_1CH.get_setting('paginate-watched') == 'true' and _1CH.get_setting('paginate') == 'true')

    for video in pw_scraper.get_watched(section, page, paginate):
        watchedstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.CH_WATCH_WEB, 'primewire_url': video['url'], 'action': 'delete', 'refresh': True})
        menu_items = [(REMOVE_W_MENU, watchedstring), ]

        create_item(section_params, video['title'], video['year'], video['img'], video['url'], menu_items=menu_items)

    total_pages = pw_scraper.get_last_res_pages()
    if not page: page = 1
    next_page = int(page) + 1

    if int(page) < int(total_pages) and paginate:
        label = i18n('skip_to_page') + '...'
        command = _1CH.build_plugin_url({'mode': MODES.WATCH_PAGE_SELECT, 'section': section, 'pages': total_pages})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': i18n('next_page') + ' >>'}
        _1CH.add_directory({'mode': MODES.BROWSE_W_WEB, 'section': section, 'page': next_page}, meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)

    utils.set_view(section_params['content'], '%s-view' % (section_params['content']))
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache') == 'true')

@pw_dispatcher.register(MODES.BROWSE_TW_WEB, ['section'], ['page'])
def browse_towatch_website(section, page=None):
    if section == 'movie': section = 'movies'

    if section == 'movies':
        label = i18n('add_towatch_to_library')
        liz = xbmcgui.ListItem(label=label)
        liz_url = _1CH.build_plugin_url({'mode': MODES.MAN_UPD_TOWATCH})
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

    section_params = get_section_params(section)
    paginate = (_1CH.get_setting('paginate-towatched') == 'true' and _1CH.get_setting('paginate') == 'true')

    for video in pw_scraper.get_towatch(section, page, paginate):
        watchstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.CH_TOWATCH_WEB, 'primewire_url': video['url'], 'action': 'delete', 'refresh': True})
        menu_items = [(REMOVE_TW_MENU, watchstring), ]

        create_item(section_params, video['title'], video['year'], video['img'], video['url'], menu_items=menu_items)

    total_pages = pw_scraper.get_last_res_pages()
    if not page: page = 1
    next_page = int(page) + 1

    if int(page) < int(total_pages) and paginate:
        label = i18n('skip_to_page') + '...'
        command = _1CH.build_plugin_url({'mode': 'WatchPageSelect', 'section': section, 'pages': total_pages})
        command = 'RunPlugin(%s)' % command
        menu_items = [(label, command)]
        meta = {'title': i18n('next_page') + ' >>'}
        _1CH.add_directory({'mode': MODES.BROWSE_TW_WEB, 'section': section, 'page': next_page}, meta, contextmenu_items=menu_items, context_replace=True, img=art('nextpage.png'), fanart=art('fanart.png'), is_folder=True)

    utils.set_view(section_params['content'], '%s-view' % (section_params['content']))
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache') == 'true')

@pw_dispatcher.register(MODES.SHOW_SCHEDULE)
def show_schedule():
    utils.log('Calling Show Schedule', xbmc.LOGDEBUG)
    section_params = get_section_params('calendar')
    for episode in pw_scraper.get_schedule():
        create_item(section_params, episode['show_title'], '', episode['img'], episode['url'], '', episode['season_num'], episode['episode_num'], day=episode['day'])

    utils.set_view(section_params['content'], '%s-view' % (section_params['content']))
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=_1CH.get_setting('dir-cache') == 'true')

def create_meta(video_type, title, year):
    utils.log('Calling Create Meta: %s, %s, %s' % (video_type, title, year), xbmc.LOGDEBUG)
    meta = {'title': title, 'year': year, 'imdb_id': '', 'overlay': ''}
    if META_ON:
        try:
            if video_type == 'tvshow':
                meta = __metaget__.get_meta(video_type, title, year=str(year))
                if not meta['imdb_id'] and not meta['tvdb_id']:
                    utils.log('No Meta Match for %s on title & year: |%s|%s|' % (video_type, title, year), xbmc.LOGDEBUG)
                    # call update_meta to force metahandlers to delete data it might have cached from get_meta
                    meta = __metaget__.update_meta(video_type, title, '')

            else:  # movie
                meta = __metaget__.get_meta(video_type, title, year=str(year))

        except Exception as e:
            utils.log('Error (%s) assigning meta data for %s %s %s' % (str(e), video_type, title, year), xbmc.LOGERROR)
    return meta

def make_art(video_type, meta, pw_img=''):
    utils.log('Making Art: %s, %s, %s' % (video_type, meta, pw_img), xbmc.LOGDEBUG)
    # default fanart to theme fanart
    art_dict = {'thumb': '', 'poster': '', 'fanart': art('fanart.png'), 'banner': ''}

    # set the thumb & cover to the poster if it exists
    if 'cover_url' in meta:
        art_dict['thumb'] = meta['cover_url']
        art_dict['poster'] = meta['cover_url']

    # set the thumb to the PW image if fallback is on and there is no cover art
    if POSTERS_FALLBACK and art_dict['thumb'] in ('/images/noposter.jpg', ''):
        art_dict['thumb'] = pw_img
        art_dict['poster'] = pw_img

    # override the fanart with metadata if fanart is on and it exists and isn't blank
    if FANART_ON and 'backdrop_url' in meta and meta['backdrop_url']: art_dict['fanart'] = meta['backdrop_url']
    if 'banner_url' in meta: art_dict['banner'] = meta['banner_url']
    return art_dict

def repair_missing_images():
    utils.log("Repairing Metadata Images")
    db_connection.repair_meta_images()

@pw_dispatcher.register(MODES.ADD2LIB, ['video_type', 'url', 'title'], ['year', 'img', 'imdbnum'])
def manual_add_to_library(video_type, url, title, year='', img='', imdbnum=''):
    add_to_library(video_type, url, title, img, year, imdbnum)
    utils.notify(msg=i18n('added_to_library') % (title), duration=2000)

def add_to_library(video_type, url, title, img, year, imdbnum):
    utils.log('Creating .strm for %s %s %s %s %s %s' % (video_type, title, imdbnum, url, img, year))
    if video_type == 'tvshow':
        save_path = _1CH.get_setting('tvshow-folder')
        save_path = xbmc.translatePath(save_path)
        show_title = title.strip()
        seasons = pw_scraper.get_season_list(url, cached=False)

        found_seasons = False
        for season in seasons:
            found_seasons = True
            season_num = season[0]
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
                show_title = re.sub(r'([^\w\-_\.\(\)\' ]|\.$)', '_', show_title)
                final_path = os.path.join(save_path, show_title, 'Season ' + season_num, filename)
                queries = {'mode': MODES.GET_SOURCES, 'url': epurl, 'imdbnum': '', 'title': show_title, 'img': '', 'dialog': 1, 'video_type': 'episode'}
                strm_string = _1CH.build_plugin_url(queries)

                write_strm(strm_string, final_path)
        if not found_seasons:
            utils.log('No Seasons found for %s at %s' % (show_title, url), xbmc.LOGERROR)

    elif video_type == 'movie':
        save_path = _1CH.get_setting('movie-folder')
        save_path = xbmc.translatePath(save_path)
        strm_string = _1CH.build_plugin_url(
            {'mode': MODES.GET_SOURCES, 'url': url, 'imdbnum': imdbnum, 'title': title, 'img': img, 'year': year, 'dialog': 1, 'video_type': 'movie'})
        if year: title = '%s (%s)' % (title, year)
        filename = utils.filename_from_title(title, 'movie')
        title = re.sub(r'[^\w\-_\.\(\)\' ]', '_', title)
        final_path = os.path.join(save_path, title, filename)

        write_strm(strm_string, final_path)

def write_strm(stream, path):
    path = xbmc.makeLegalFilename(path)
    if not xbmcvfs.exists(os.path.dirname(path)):
        try:
            try: xbmcvfs.mkdirs(os.path.dirname(path))
            except: os.mkdir(os.path.dirname(path))
        except:
            utils.log('Failed to create directory %s' % path, xbmc.LOGERROR)

    old_strm_string = ''
    try:
        f = xbmcvfs.File(path, 'r')
        old_strm_string = f.read()
        f.close()
    except: pass

    # print "Old String: %s; New String %s" %(old_strm_string,strm_string)
    # string will be blank if file doesn't exist or is blank
    if stream != old_strm_string:
        try:
            utils.log('Writing strm: %s' % stream)
            file_desc = xbmcvfs.File(path, 'w')
            file_desc.write(stream)
            file_desc.close()
        except Exception, e:
            utils.log('Failed to create .strm file: %s\n%s' % (path, e), xbmc.LOGERROR)

@pw_dispatcher.register(MODES.ADD_SUB, ['url', 'title'], ['year', 'img', 'imdbnum'])
def add_subscription(url, title, year='', img='', imdbnum=''):
    try:
        days = utils.get_default_days()
        if utils.using_pl_subs():
            pw_scraper.add_to_playlist(utils.get_subs_pl_url(), url)
            db_connection.add_ext_sub(SUB_TYPES.PW_PL, url, imdbnum, days)
        else:
            db_connection.add_subscription(url, title, img, year, imdbnum, days)

        add_to_library('tvshow', url, title, img, year, imdbnum)
        utils.notify(msg=i18n('subbed_to'), duration=2000)
    except:
        utils.notify(msg=i18n('already_sub_to'), duration=2000)
    xbmc.executebuiltin('Container.Refresh')

@pw_dispatcher.register(MODES.CANCEL_SUB, ['url'])
def cancel_subscription(url):
    if utils.using_pl_subs():
        pw_scraper.remove_from_playlist(utils.get_subs_pl_url(), url)
        db_connection.delete_ext_sub(SUB_TYPES.PW_PL, url)
    else:
        db_connection.delete_subscription(url)
    xbmc.executebuiltin('Container.Refresh')

@pw_dispatcher.register(MODES.MAN_UPD_SUBS)
def manual_update_subscriptions():
    update_subscriptions()
    utils.notify(i18n('subscriptions_updated'), duration=2000)
    now = datetime.datetime.now()
    _1CH.set_setting('%s-last_run' % MODES.UPD_SUBS, now.strftime("%Y-%m-%d %H:%M:%S.%f"))
    xbmc.executebuiltin('Container.Refresh')

@pw_dispatcher.register(MODES.UPD_SUBS)
def update_subscriptions():
    day = datetime.datetime.now().weekday()
    subs = get_subscriptions(day)
    for sub in subs:
        add_to_library('tvshow', sub[0], sub[1], sub[2], sub[3], sub[4])

    if _1CH.get_setting('auto-update_towatch') == 'true':
        update_towatch()
    if _1CH.get_setting('library-update') == 'true':
        xbmc.executebuiltin('UpdateLibrary(video)')
    if _1CH.get_setting('cleanup-subscriptions') == 'true':
        clean_up_subscriptions()
    if _1CH.get_setting(MODES.UPD_SUBS + '-notify') == 'true':
        utils.notify(i18n('subscriptions_updated'), duration=2000)
        utils.notify(msg=i18n('next_update') % (_1CH.get_setting(MODES.UPD_SUBS + '-interval')), duration=5000)

@pw_dispatcher.register(MODES.MAN_CLEAN_SUBS)
def manual_clean_up_subscriptions():
    clean_up_subscriptions()
    utils.notify(msg=i18n('sub_cleaned'), duration=2000)

@pw_dispatcher.register(MODES.CLEAN_SUBS)
def clean_up_subscriptions():
    utils.log('Cleaning up dead subscriptions')
    subs = get_subscriptions()
    for sub in subs:
        meta = __metaget__.get_meta('tvshow', sub[1], year=sub[3])
        if meta['status'] == 'Ended':
            utils.log('Selecting %s  for removal' % sub[1], xbmc.LOGDEBUG)
            cancel_subscription(sub[0])

@pw_dispatcher.register(MODES.MAN_UPD_TOWATCH)
def manual_update_towatch():
    update_towatch()
    if _1CH.get_setting('library-update') == 'true':
        xbmc.executebuiltin('UpdateLibrary(video)')
    utils.notify(msg=i18n('towatch_added_to_lib'), duration=2000)

def update_towatch():
    if not utils.website_is_integrated(): return
    movies = pw_scraper.get_towatch('movies')
    for movie in movies:
        add_to_library('movie', movie['url'], movie['title'], movie['img'], movie['year'], None)

@pw_dispatcher.register(MODES.MANAGE_SUBS)
def manage_subscriptions():
    utils.set_view('tvshows', 'tvshows-view')
    next_run = utils.get_next_run(MODES.UPD_SUBS)
    liz = xbmcgui.ListItem(label=i18n('update_subs') % (next_run.strftime('%Y-%m-%d %H:%M:%S')))
    liz_url = _1CH.build_plugin_url({'mode': MODES.MAN_UPD_SUBS})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

    liz = xbmcgui.ListItem(label=i18n('clean_subs'))
    liz_url = _1CH.build_plugin_url({'mode': MODES.MAN_CLEAN_SUBS})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

    fav_urls = get_fav_urls('tv')

    subs = get_subscriptions(order_matters=True)
    subs_len = len(subs)
    for sub in subs:
        url, title, img, year, _, days = sub
        days_string = utils.get_days_string_from_days(days)
        if days_string == '': days_string = i18n('disabled')
        days_format = _1CH.get_setting('format-sub-days')

        if '%s' in days_format:
            days_string = days_format % (days_string)
        else:
            utils.log('Ignoring subscription days format because %s is missing', xbmc.LOGDEBUG)

        meta = create_meta('tvshow', title, year)
        meta['title'] = utils.format_label_sub(meta)

        menu_items = []
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.EDIT_DAYS, 'url': url, 'days': days})
        menu_items.append((i18n('edit_days'), runstring,))
        runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.CANCEL_SUB, 'url': url})
        menu_items.append((i18n('cancel_subscription'), runstring,))

        if url in fav_urls:
            runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.DEL_FAV, 'url': url})
            menu_items.append((i18n('remove_fav_menu'), runstring,))
        else:
            runstring = 'RunPlugin(%s)' % _1CH.build_plugin_url({'mode': MODES.SAVE_FAV, 'fav_type': 'tv', 'title': title, 'url': url, 'year': year})
            menu_items.append((i18n('add_to_favs'), runstring,))

        menu_items.append((i18n('show_information'), 'XBMC.Action(Info)',))

        art = make_art('tvshow', meta, img)
        label = '[%s] %s' % (days_string, meta['title'])
        listitem = xbmcgui.ListItem(label, iconImage=art['thumb'], thumbnailImage=art['thumb'])
        listitem.setProperty('fanart_image', art['fanart'])
        try: listitem.setArt(art)
        except: pass
        listitem.setInfo('video', meta)
        listitem.addContextMenuItems(menu_items, replaceItems=True)
        queries = {'mode': MODES.SEASON_LIST, 'title': title, 'url': url, 'img': img, 'imdbnum': meta['imdb_id'], 'video_type': 'tvshow', 'year': year}
        li_url = _1CH.build_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, listitem, isFolder=True, totalItems=subs_len)
    _1CH.end_of_directory()

def get_subscriptions(day=None, order_matters=False):
    if utils.using_pl_subs():
        def_days = utils.get_default_days()
        items = pw_scraper.show_playlist(utils.get_subs_pl_url(), False)
        ext_subs = db_connection.get_external_subs(SUB_TYPES.PW_PL)
        subs = []
        for item in items:
            if item['video_type'] == 'tvshow':
                for i, sub in enumerate(ext_subs):
                    if item['url'] == sub[1]:
                        item['days'] = sub[3]
                        del ext_subs[i]
                        break
                else:
                    # add the item to ext_subs with default days
                    db_connection.add_ext_sub(SUB_TYPES.PW_PL, item['url'], '', def_days)
                    item['days'] = def_days

                # only add this item to the list if we are pulling all days or a day that this item runs on
                if day is None or str(day) in item['days']:
                    subs.append((item['url'], item['title'], item['img'], item['year'], '', item['days']))

                if order_matters:
                    subs.sort(cmp=days_cmp, key=lambda k: k[5].ljust(7) + k[1])
    else:
        subs = db_connection.get_subscriptions(day, order_matters)
    return subs

# "all days" goes to the top, "no days" goes to the bottom, everything else is sorted lexicographically
def days_cmp(x, y):
    xdays, xtitle = x[:7], x[7:]
    ydays, ytitle = y[:7], y[7:]
    # print 'xdays,xtitle,ydays,ytitle: |%s|%s|%s|%s|' % (xdays,xtitle,ydays,ytitle)
    if xdays == ydays:
        return cmp(xtitle, ytitle)
    elif xdays == '0123456':
        return -1
    elif ydays == '0123456':
        return 1
    elif xdays == ' ' * 7:
        return 1
    elif ydays == ' ' * 7:
        return -1
    else:
        return cmp(x, y)

def compose(inner_func, *outer_funcs):
    """Compose multiple unary functions together into a single unary function"""
    if not outer_funcs:
        return inner_func
    outer_func = compose(*outer_funcs)
    return lambda *args, **kwargs: outer_func(inner_func(*args, **kwargs))

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

    return str("featured")  # default

@pw_dispatcher.register(MODES.PAGE_SELECT, ['mode', 'section'], ['genre', 'letter', 'sort'])
@pw_dispatcher.register(MODES.FAV_PAGE_SELECT, ['mode', 'section'])
@pw_dispatcher.register(MODES.WATCH_PAGE_SELECT, ['mode', 'section'])
@pw_dispatcher.register(MODES.SEARCH_PAGE_SELECT, ['mode', 'section'], ['search', 'query'])
@pw_dispatcher.register(MODES.PL_PAGE_SELECT, ['mode', 'section'], ['public', 'sort'])
def jump_to_page(mode, section, genre='', letter='', sort='', search='', query='', public=''):
    if mode == MODES.PAGE_SELECT:
        queries = {'mode': MODES.FILTER_RESULTS, 'section': section, 'genre': genre, 'letter': letter, 'sort': sort}
    elif mode == MODES.FAV_PAGE_SELECT:
        queries = {'mode': MODES.BROWSE_FAVS_WEB, 'section': section}
    elif mode == MODES.WATCH_PAGE_SELECT:
        queries = {'mode': MODES.BROWSE_W_WEB, 'section': section}
    elif mode == MODES.SEARCH_PAGE_SELECT:
        queries = {'mode': search, 'query': query, 'section': section}
    elif mode == MODES.PL_PAGE_SELECT:
        queries = {'mode': MODES.BROWSE_PLAYLISTS, 'section': section, 'public': public, 'sort': sort}

    pages = int(_1CH.queries['pages'])
    dialog = xbmcgui.Dialog()
    options = []
    for page in range(pages):
        label = '%s %s' % (i18n('page'), str(page + 1))
        options.append(label)
    index = dialog.select(i18n('skip_to_page'), options)
    if index > -1:
        queries['page'] = index + 1
        url = _1CH.build_plugin_url(queries)
        builtin = 'Container.Update(%s)' % url
        xbmc.executebuiltin(builtin)

@pw_dispatcher.register(MODES.RESET_DB)
def reset_db():
    if db_connection.reset_db():
        message = i18n('db_reset_success')
    else:
        message = i18n('db_reset_sqlite')
    utils.notify(msg=message, duration=2000)

@pw_dispatcher.register(MODES.EXPORT_DB)
def export_db():
    try:
        dialog = xbmcgui.Dialog()
        export_path = dialog.browse(0, i18n('select_export_dir'), 'files')
        if export_path:
            export_path = xbmc.translatePath(export_path)
            keyboard = xbmc.Keyboard('export.csv', i18n('enter_export_filename'))
            keyboard.doModal()
            if keyboard.isConfirmed():
                export_filename = keyboard.getText()
                export_file = export_path + export_filename
                db_connection.export_from_db(export_file)
                utils.notify(header=i18n('export'), msg=i18n('exported_to'), duration=2000)
    except Exception as e:
        utils.log('Export Failed: %s' % (e), xbmc.LOGERROR)
        utils.notify(header=i18n('export'), msg=i18n('exported_failed'), duration=2000)

@pw_dispatcher.register(MODES.IMPORT_DB)
def import_db():
    try:
        dialog = xbmcgui.Dialog()
        import_file = dialog.browse(1, i18n('select_import_file'), 'files')
        if import_file:
            import_file = xbmc.translatePath(import_file)
            db_connection.import_into_db(import_file)
            utils.notify(header=i18n('import'), msg=i18n('imported_from'), duration=5000)
    except Exception as e:
        utils.log('Import Failed: %s' % (e), xbmc.LOGERROR)
        utils.notify(header=i18n('import'), msg=i18n('import_failed'), duration=2000)
        raise

@pw_dispatcher.register(MODES.BACKUP_DB)
def backup_db():
    path = xbmc.translatePath("special://database")
    now_str = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    full_path = path + 'db_backup_' + now_str + '.csv'
    db_connection.export_from_db(full_path)

@pw_dispatcher.register(MODES.EDIT_DAYS, ['url'], ['days'])
def edit_days(url, days=''):
    try:
        # use a keyboard if the hidden setting is true
        if _1CH.get_setting('use-days-keyboard') == 'true':
            keyboard = xbmc.Keyboard(utils.get_days_string_from_days(days), '%s (e.g. MTWHFSaSu)' % (i18n('days_upd_sub')))
            keyboard.doModal()
            if keyboard.isConfirmed():
                days_string = keyboard.getText()
                new_days = utils.get_days_from_days_string(days_string)
            else:
                raise  # jump back
        else:
            new_days = gui_utils.days_select(days)

        if utils.using_pl_subs():
            db_connection.edit_external_days(SUB_TYPES.PW_PL, url, new_days)
        else:
            db_connection.edit_days(url, new_days)
        xbmc.executebuiltin('Container.Refresh')
    except: pass  # if clicked cancel just abort

@pw_dispatcher.register(MODES.HELP)
def show_help():
    utils.log('Showing help popup')
    try: utils.TextBox()
    except: pass

@pw_dispatcher.register(MODES.FLUSH_CACHE)
def flush_cache():
    dlg = xbmcgui.Dialog()
    ln1 = i18n('are_you_sure_you_want_to')
    ln2 = i18n('delete_the_url_cache')
    ln3 = i18n('slow_things_down')
    yes = i18n('keep')
    no = i18n('delete')
    if dlg.yesno(i18n('flush_web_cache'), ln1, ln2, ln3, yes, no):
        db_connection.flush_cache()

@pw_dispatcher.register(MODES.MOVIE_UPDATE)
def movie_update():
    utils.notify(msg=i18n('updating_wait'), duration=5000)
    GetFilteredResults(section='movies', sort=update_movie_cat(), paginate=True)

@pw_dispatcher.register(MODES.SELECT_SOURCES, ['url', 'title'], ['year', 'imdbnum', 'img'])
def select_sources(url, title, year='', img='', imdbnum=''):
    get_sources(url, title, year=year, img=img, imdbnum=imdbnum, respect_auto=False)

@pw_dispatcher.register(MODES.REFRESH_META, ['video_type', 'title', 'alt_id'], ['imdbnum', 'year'])
def refresh_meta(video_type, title, alt_id, imdbnum='', year=''):
    utils.refresh_meta(video_type, title, imdbnum, alt_id, year)

@pw_dispatcher.register(MODES.META_SETTINGS)
def metahandler_settings():
    import metahandler
    metahandler.display_settings()

@pw_dispatcher.register(MODES.RES_SETTINGS)
def resolver_settings():
    urlresolver.display_settings()

@pw_dispatcher.register(MODES.TOGGLE_X_FAVS, ['title', 'url', 'action'], ['img', 'is_playable'])
def toggle_xbmc_fav(title, url, action, img='', is_playable=False):
    # playable urls have to be added as media; folders as window
    fav_types = ['media', 'window']
    url_types = ['path', 'windowparameter']
    dialogs = ['&dialog=True', '&dialog=False']

    xbmc_fav_urls = utils.get_xbmc_fav_urls()
    if is_playable:
        fav_index = 0
    else:
        fav_index = 1
    opp_index = (fav_index + 1) % 2

    # annoyingly, json rpc toggles favorite despite it's name (i.e. if it exists, it removes it and vice versa)
    fav_url = url + dialogs[fav_index]
    opp_url = url + dialogs[opp_index]
    cmd = '{"jsonrpc": "2.0", "method": "Favourites.AddFavourite", "params": {"title": "%s", "type": "%s", "window": "10025", "%s": "%s", "thumbnail": "%s"}, "id": 1}'
    fav_cmd = cmd % (title, fav_types[fav_index], url_types[fav_index], fav_url, img)
    opp_cmd = cmd % (title, fav_types[opp_index], url_types[opp_index], opp_url, img)
    fav_exists = utils.in_xbmc_favs(fav_url, xbmc_fav_urls, False)
    opp_exists = utils.in_xbmc_favs(opp_url, xbmc_fav_urls, False)

    if action == FAV_ACTIONS.ADD:
        if not fav_exists:
            xbmc.executeJSONRPC(fav_cmd)

    if action == FAV_ACTIONS.REMOVE:
        if fav_exists:
            xbmc.executeJSONRPC(fav_cmd)

        # we should only need to remove this if it was added while source-win=<opposite current setting>
        if opp_exists:
            xbmc.executeJSONRPC(opp_cmd)

    xbmc.executebuiltin('Container.Refresh')

def main(argv=None):
    if sys.argv: argv = sys.argv

    utils.log('Version: |%s| Queries: |%s|' % (_1CH.get_version(), _1CH.queries))
    utils.log('Args: |%s|' % (argv))

    # don't process params that don't match our url exactly. (e.g. plugin://plugin.video.1channel/extrafanart)
    plugin_url = 'plugin://%s/' % (_1CH.get_id())
    if argv[0] != plugin_url:
        return

    mode = _1CH.queries.get('mode', None)
    if mode in [MODES.GET_SOURCES, MODES.PLAY_SOURCE, MODES.PLAY_TRAILER, MODES.RES_SETTINGS, MODES.SELECT_SOURCES]:
        global urlresolver
        import urlresolver

    pw_dispatcher.dispatch(mode, _1CH.queries)

if __name__ == '__main__':
    sys.exit(main())
