"""
    1Channel XBMC Addon
    Copyright (C) 2014 Bstrdsmkr, tknorris

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
import re
import sys
import time
import datetime
import json
import random
import _strptime  # fix bug in python import
import xbmc
import xbmcgui
import xbmcplugin
from addon.common.addon import Addon
import strings

DAY_NUMS = list('0123456')
DAY_CODES = ['M', 'T', 'W', 'H', 'F', 'Sa', 'Su']

_1CH = Addon('plugin.video.1channel')
ICON_PATH = os.path.join(_1CH.get_path(), 'icon.png')
BR_VERS = [
    ['%s.0' % i for i in xrange(18, 47)],
    ['37.0.2062.103', '37.0.2062.120', '37.0.2062.124', '38.0.2125.101', '38.0.2125.104', '38.0.2125.111', '39.0.2171.71', '39.0.2171.95', '39.0.2171.99', '40.0.2214.93', '40.0.2214.111',
     '40.0.2214.115', '42.0.2311.90', '42.0.2311.135', '42.0.2311.152', '43.0.2357.81', '43.0.2357.124', '44.0.2403.155', '44.0.2403.157', '45.0.2454.101', '45.0.2454.85', '46.0.2490.71',
     '46.0.2490.80', '46.0.2490.86', '47.0.2526.73', '47.0.2526.80', '48.0.2564.116', '49.0.2623.112', '50.0.2661.86'],
    ['11.0']]
WIN_VERS = ['Windows NT 10.0', 'Windows NT 7.0', 'Windows NT 6.3', 'Windows NT 6.2', 'Windows NT 6.1', 'Windows NT 6.0', 'Windows NT 5.1', 'Windows NT 5.0']
FEATURES = ['; WOW64', '; Win64; IA64', '; Win64; x64', '']
RAND_UAS = ['Mozilla/5.0 ({win_ver}{feature}; rv:{br_ver}) Gecko/20100101 Firefox/{br_ver}',
            'Mozilla/5.0 ({win_ver}{feature}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{br_ver} Safari/537.36',
            'Mozilla/5.0 ({win_ver}{feature}; Trident/7.0; rv:{br_ver}) like Gecko']


def enum(**enums):
    return type('Enum', (), enums)

MODES = enum(SAVE_FAV='SaveFav', DEL_FAV='DeleteFav', GET_SOURCES='GetSources', PLAY_SOURCE='PlaySource', CH_WATCH='ChangeWatched', PLAY_TRAILER='PlayTrailer',
                   SEARCH_QUERY='GetSearchQuery', DESC_QUERY='GetSearchQueryDesc', ADV_QUERY='GetSearchQueryAdvanced', SEARCH='Search', SEARCH_DESC='SearchDesc',
                   SEARCH_ADV='SearchAdvanced', REMOTE_SEARCH='7000', MAIN='main', LIST_MENU='BrowseListMenu', AZ_MENU='BrowseAlphabetMenu', GENRE_MENU='BrowseByGenreMenu',
                   FILTER_RESULTS='GetFilteredResults', SEASON_LIST='TVShowSeasonList', EPISODE_LIST='TVShowEpisodeList', BROWSE_FAVS='browse_favorites',
                   BROWSE_FAVS_WEB='browse_favorites_website', MIG_FAVS='migrateFavs', FAV2LIB='fav2Library', BROWSE_W_WEB='browse_watched_website', ADD2LIB='add_to_library',
                   ADD_SUB='add_subscription', CANCEL_SUB='cancel_subscription', MAN_UPD_SUBS='manual_update_subscriptions', UPD_SUBS='update_subscriptions',
                   MAN_CLEAN_SUBS='manual_clean_up_subscriptions', CLEAN_SUBS='clean_up_subscriptions', MANAGE_SUBS='manage_subscriptions', PAGE_SELECT='PageSelect',
                   FAV_PAGE_SELECT='FavPageSelect', WATCH_PAGE_SELECT='WatchedPageSelect', SEARCH_PAGE_SELECT='SearchPageSelect', EXPORT_DB='export_db', IMPORT_DB='import_db',
                   BACKUP_DB='backup_db', EDIT_DAYS='edit_days', HELP='Help', FLUSH_CACHE='flush_cache', INSTALL_META='install_metapack', INSTALL_LOCAL_META='install_local_metapack',
                   MOVIE_UPDATE='movie_update', SELECT_SOURCES='SelectSources', REFRESH_META='refresh_meta', META_SETTINGS='9988', RES_SETTINGS='ResolverSettings',
                   TOGGLE_X_FAVS='toggle_xbmc_fav', PLAYLISTS_MENU='playlists_menu', BROWSE_PLAYLISTS='get_playlists', SHOW_PLAYLIST='show_playlist', PL_PAGE_SELECT='PLPageSelect',
                   RM_FROM_PL='remove_from_playlist', ADD2PL='add_to_playlist', BROWSE_TW_WEB='browse_towatch_website', CH_TOWATCH_WEB='change_towatch_website',
                   CH_WATCH_WEB='change_watched_website', MAN_UPD_TOWATCH='man_update_towatch', RESET_DB='reset_db', INSTALL_THEMES='install_themes',
                   SHOW_SCHEDULE='show_schedule')

SUB_TYPES = enum(PW_PL=0)

hours_list = {}
hours_list[MODES.UPD_SUBS] = [2, 2] + range(2, 25)  # avoid accidental runaway subscription updates
hours_list[MODES.MOVIE_UPDATE] = [2, 5, 10, 15, 24]
hours_list[MODES.BACKUP_DB] = [12, 24, 168, 720]


def get_days_string_from_days(days):
    if days is None:
        days = ''

    days_string = ''
    fdow = int(_1CH.get_setting('first-dow'))
    adj_day_nums = DAY_NUMS[fdow:] + DAY_NUMS[:fdow]
    adj_day_codes = DAY_CODES[fdow:] + DAY_CODES[:fdow]
    all_days = ''.join(adj_day_codes)
    for i, day_num in enumerate(adj_day_nums):
        if day_num in days:
            days_string += adj_day_codes[i]

    if days_string == all_days:
        days_string = 'ALL'

    return days_string

def get_days_from_days_string(days_string):
    if days_string is None:
        days_string = ''

    days_string = days_string.upper()
    days = ''
    if days_string == 'ALL':
        days = '0123456'
    else:
        for i, day in enumerate(DAY_CODES):
            if day.upper() in days_string:
                days += DAY_NUMS[i]

    return days

def get_default_days():
    def_days = ['0123456', '', '0246']
    dow = datetime.datetime.now().weekday()
    def_days.append(str(dow))
    def_days.append(str(dow) + str((dow + 1) % 7))
    return def_days[int(_1CH.get_setting('sub-days'))]

def format_label_tvshow(info):
    if 'premiered' in info:
        year = info['premiered'][:4]
    else:
        year = ''
    title = info['title']
    label = _1CH.get_setting('format-tvshow')

    label = re.sub('\{t\}', title, label)
    label = re.sub('\{y\}', year, label)
    label = re.sub('\{ft\}', format_tvshow_title(title), label)
    label = re.sub('\{fy\}', format_tvshow_year(year), label)
    return label

def format_tvshow_title(title):
    title_format = _1CH.get_setting('format-tvshow-title')
    label = re.sub('\{t\}', title, title_format)
    return label

def format_tvshow_year(year):
    if not year: return ''
    year_format = _1CH.get_setting('format-tvshow-year')
    label = re.sub('\{y\}', year, year_format)
    return label

def format_tvshow_episode(info):
    episode_format = _1CH.get_setting('format-tvshow-episode')
    label = re.sub('\{s\}', str(info['season']), episode_format)
    label = re.sub('\{0s\}', str(info['season']).zfill(2), label)
    label = re.sub('\{e\}', str(info['episode']), label)
    label = re.sub('\{0e\}', str(info['episode']).zfill(2), label)
    label = re.sub('\{t\}', info['title'], label)
    label = re.sub('\{st\}', info['TVShowTitle'], label)
    return label

def format_label_sub(info):
    sub_format = _1CH.get_setting('format-tvshow-sub')
    label = format_label_tvshow(info)
    formatted_label = re.sub('\{L\}', label, sub_format)
    return formatted_label

def format_label_movie(info):
    if 'premiered' in info:
        year = info['premiered'][:4]
    else:
        year = ''
    label = _1CH.get_setting('format-movie')
    title = info['title']
    label = re.sub('\{t\}', title, label)
    label = re.sub('\{y\}', year, label)
    label = re.sub('\{ft\}', format_movie_title(title), label)
    label = re.sub('\{fy\}', format_movie_year(year), label)
    return label


def format_movie_title(title):
    title_format = _1CH.get_setting('format-movie-title')
    label = re.sub('\{t\}', title, title_format)
    return label


def format_movie_year(year):
    if not year: return ''
    year_format = _1CH.get_setting('format-movie-year')
    label = re.sub('\{y\}', year, year_format)
    return label


def format_label_source(info):
    label = _1CH.get_setting('format-source')
    label = re.sub('\{q\}', info['quality'], label)
    label = re.sub('\{h\}', info['host'], label)
    label = re.sub('\{v\}', str(info['views']), label)
    if 'debrid' in info and info['debrid']:
        resolvers = ', '.join(info['debrid'])
        label = re.sub('\{d\}', '%s' % (resolvers), label)
    else:
        label = re.sub('\{d\}', '', label)
        
    if info['multi-part']:
        parts = 'part 1'
    else:
        parts = ''
    label = re.sub('\{p\}', parts, label)
    if info['verified']: label = format_label_source_verified(label)
    if 'debrid' in info and info['debrid']:
        label = format_label_source_debrid(label)
    return label

def format_label_source_debrid(label):
    debrid_format = _1CH.get_setting('format-source-debrid')
    return re.sub('\{L\}', label, debrid_format)
    
def format_label_source_verified(label):
    ver_format = _1CH.get_setting('format-source-verified')
    formatted_label = re.sub('\{L\}', label, ver_format)
    return formatted_label

def format_label_source_parts(info, part_num):
    label = _1CH.get_setting('format-source-parts')
    label = re.sub('\{q\}', info['quality'], label)
    label = re.sub('\{h\}', info['host'], label)
    label = re.sub('\{v\}', str(info['views']), label)
    parts = 'part %s' % part_num
    label = re.sub('\{p\}', parts, label)
    if info['verified']: label = format_label_source_verified(label)
    return label


def has_upgraded():
    old_version = _1CH.get_setting('old_version').split('.')
    new_version = _1CH.get_version().split('.')
    current_oct = 0
    for octant in old_version:
        if int(new_version[current_oct]) > int(octant):
            log('New version found')
            return True
        current_oct += 1
    return False


def filename_from_title(title, video_type):
    if video_type == 'tvshow':
        filename = '%s S%sE%s.strm'
        filename = filename % (title, '%s', '%s')
    else:
        filename = '%s.strm' % title

    filename = re.sub(r'(?!%s)[^\w\-_\. ]', '_', filename)
    xbmc.makeLegalFilename(filename)
    return filename

class TextBox:
    # constants
    WINDOW = 10147
    CONTROL_LABEL = 1
    CONTROL_TEXTBOX = 5

    def __init__(self, *args, **kwargs):
        xbmc.executebuiltin("ActivateWindow(%d)" % (self.WINDOW))
        xbmc.sleep(1000)
        self.win = xbmcgui.Window(TextBox.WINDOW)
        self.setControls()

    def setControls(self):
        heading = "PrimeWire v%s" % (_1CH.get_version())
        self.win.getControl(TextBox.CONTROL_LABEL).setLabel(heading)
        root = _1CH.get_path()
        faq_path = os.path.join(root, 'help.faq')
        f = open(faq_path)
        text = f.read()
        log(faq_path)
        self.win.getControl(TextBox.CONTROL_TEXTBOX).setText(text)


def website_is_integrated():
    use_https = _1CH.get_setting('use_https') == 'true'
    enabled = _1CH.get_setting('site_enabled') == 'true'
    user = _1CH.get_setting('usename') is not None
    passwd = _1CH.get_setting('passwd') is not None
    return use_https and enabled and user and passwd

def using_pl_subs():
    return (website_is_integrated() and _1CH.get_setting('playlist-sub'))

def get_subs_pl_url():
    return '/playlists.php?id=%s' % (_1CH.get_setting('playlist-sub'))

def rank_host(source):
    host = source['host']
    ranking = _1CH.get_setting('host-rank').split(',')
    host = host.lower()
    for tier in ranking:
        tier = tier.replace(' ', '')
        tier = tier.lower()
        if host in tier.split('|'):
            return ranking.index(tier) + 1
    return 1000

def refresh_meta(video_type, old_title, imdb, alt_id, year, new_title=''):
    from metahandler import metahandlers
    __metaget__ = metahandlers.MetaData()
    search_title = new_title if new_title else old_title
    if video_type in ['tvshow', 'episode']:
        api = metahandlers.TheTVDB()
        results = api.get_matching_shows(search_title)
        search_meta = []
        for item in results:
            option = {'tvdb_id': item[0], 'title': item[1], 'imdb_id': item[2]}
            search_meta.append(option)

    else:
        search_meta = __metaget__.search_movies(search_title)
    log('search_meta: %s' % search_meta, xbmc.LOGDEBUG)

    option_list = ['%s...' % (i18n('manual_search'))]
    if search_meta:
        for option in search_meta:
            if 'year' in option and option['year'] is not None:
                disptitle = '%s (%s)' % (option['title'], option['year'])
            else:
                disptitle = option['title']
            option_list.append(disptitle)

    dialog = xbmcgui.Dialog()
    index = dialog.select(i18n('choose'), option_list)

    if index == 0:
        refresh_meta_manual(video_type, old_title, imdb, alt_id, year)
    elif index > -1:
        new_imdb_id = search_meta[index - 1]['imdb_id']
        try: new_tmdb_id = search_meta[index - 1]['tmdb_id']
        except: new_tmdb_id = ''

        # Temporary workaround for metahandlers problem:
        # Error attempting to delete from cache table: no such column: year
        if video_type == 'tvshow': year = ''

        log(search_meta[index - 1], xbmc.LOGDEBUG)
        __metaget__.update_meta(video_type, old_title, imdb, year=year, new_imdb_id=new_imdb_id, new_tmdb_id=new_tmdb_id)
        xbmc.executebuiltin('Container.Refresh')


def refresh_meta_manual(video_type, old_title, imdb, alt_id, year):
    keyboard = xbmc.Keyboard()
    if year:
        disptitle = '%s (%s)' % (old_title, year)
    else:
        disptitle = old_title
    keyboard.setHeading(i18n('enter_a_title'))
    keyboard.setDefault(disptitle)
    keyboard.doModal()
    if keyboard.isConfirmed():
        search_string = keyboard.getText()
        refresh_meta(video_type, old_title, imdb, alt_id, year, search_string)


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


def get_dir_size(start_path):
    print 'Calculating size of %s' % start_path
    total_size = 0
    for dirpath, _, filenames in os.walk(start_path):
        for each_file in filenames:
            fpath = os.path.join(dirpath, each_file)
            total_size += os.path.getsize(fpath)
    print 'Calculated: %s' % total_size
    return total_size


def format_eta(seconds):
    minutes, seconds = divmod(seconds, 60)
    if minutes > 60:
        hours, minutes = divmod(minutes, 60)
        return "ETA: %02d:%02d:%02d " % (hours, minutes, seconds)
    else:
        return "ETA: %02d:%02d " % (minutes, seconds)

def format_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    if minutes > 60:
        hours, minutes = divmod(minutes, 60)
        return "%02d:%02d:%02d" % (hours, minutes, seconds)
    else:
        return "%02d:%02d" % (minutes, seconds)

def filename_filter_out_year(name=''):
    try:
        years = re.compile(' \((\d+)\)').findall('__' + name + '__')
        for year in years: name = name.replace(' (' + year + ')', '')
        name = name.replace('[B]', '').replace('[/B]', '').replace('[/COLOR]', '').replace('[COLOR green]', '')
        name = name.strip()
        return name
    except: name.strip(); return name

def unpack_query(query):
    expected_keys = ('title', 'tag', 'country', 'genre', 'actor', 'director', 'year', 'month', 'decade')
    criteria = json.loads(query)
    for key in expected_keys:
        if key not in criteria: criteria[key] = ''

    return criteria

def get_xbmc_fav_urls():
    xbmc_favs = get_xbmc_favs()
    fav_urls = []
    for fav in xbmc_favs:
        if 'path' in fav:
            fav_url = fav['path']
        elif 'windowparameter' in fav:
            fav_url = fav['windowparameter']
        else:
            continue

        fav_urls.append(fav_url)
    return fav_urls

def in_xbmc_favs(url, fav_urls, ignore_dialog=True):
    if ignore_dialog:
        fav_urls = (fav_url.replace('&dialog=True', '').replace('&dialog=False', '') for fav_url in fav_urls)

    if url in fav_urls:
        return True
    else:
        return False

def get_xbmc_favs():
    favs = []
    cmd = '{"jsonrpc": "2.0", "method": "Favourites.GetFavourites", "params": {"type": null, "properties": ["path", "windowparameter"]}, "id": 1}'
    result = xbmc.executeJSONRPC(cmd)
    result = json.loads(result)
    if 'error' not in result:
        if result['result']['favourites'] is not None:
            for fav in result['result']['favourites']:
                favs.append(fav)
    else:
        log('Failed to get XBMC Favourites: %s' % (result['error']['message']), xbmc.LOGERROR)
    return favs

# Run a task on startup. Settings and mode values must match task name
def do_startup_task(task):
    run_on_startup = _1CH.get_setting('auto-%s' % task) == 'true' and _1CH.get_setting('%s-during-startup' % task) == 'true'
    if run_on_startup and not xbmc.abortRequested:
        log('Service: Running startup task [%s]' % (task))
        now = datetime.datetime.now()
        xbmc.executebuiltin('RunPlugin(plugin://plugin.video.1channel/?mode=%s)' % (task))
        _1CH.set_setting('%s-last_run' % (task), now.strftime("%Y-%m-%d %H:%M:%S.%f"))

# Run a recurring scheduled task. Settings and mode values must match task name
def do_scheduled_task(task, isPlaying):
    now = datetime.datetime.now()
    if _1CH.get_setting('auto-%s' % task) == 'true':
        next_run = get_next_run(task)
        # log("Update Status on [%s]: Currently: %s Will Run: %s" % (task, now, next_run))
        if now >= next_run:
            is_scanning = xbmc.getCondVisibility('Library.IsScanningVideo')
            if not is_scanning:
                during_playback = _1CH.get_setting('%s-during-playback' % (task)) == 'true'
                if during_playback or not isPlaying:
                    log('Service: Running Scheduled Task: [%s]' % (task))
                    builtin = 'RunPlugin(plugin://plugin.video.1channel/?mode=%s)' % (task)
                    xbmc.executebuiltin(builtin)
                    _1CH.set_setting('%s-last_run' % task, now.strftime("%Y-%m-%d %H:%M:%S.%f"))
                else:
                    log('Service: Playing... Busy... Postponing [%s]' % (task), xbmc.LOGDEBUG)
            else:
                log('Service: Scanning... Busy... Postponing [%s]' % (task), xbmc.LOGDEBUG)

def get_next_run(task):
    # strptime mysteriously fails sometimes with TypeError; this is a hacky workaround
    # note, they aren't 100% equal as time.strptime loses fractional seconds but they are close enough
    try:
        last_run = datetime.datetime.strptime(_1CH.get_setting(task + '-last_run'), "%Y-%m-%d %H:%M:%S.%f")
    except TypeError:
        last_run = datetime.datetime(*(time.strptime(_1CH.get_setting(task + '-last_run'), '%Y-%m-%d %H:%M:%S.%f')[0:6]))
    interval = datetime.timedelta(hours=hours_list[MODES.UPD_SUBS][int(_1CH.get_setting(task + '-interval'))])
    return (last_run + interval)

def log(msg, level=xbmc.LOGNOTICE):
    # override message level to force logging when addon logging turned on
    if _1CH.get_setting('addon_debug') == 'true' and level == xbmc.LOGDEBUG:
        level = xbmc.LOGNOTICE

    try: _1CH.log(msg, level)
    except:
        try: xbmc.log('Logging Failure', level)
        except: pass  # just give up

def notify(header=None, msg='', duration=2000):
    if header is None: header = _1CH.get_name()
    builtin = "XBMC.Notification(%s,%s, %s, %s)" % (header, msg, duration, ICON_PATH)
    xbmc.executebuiltin(builtin)

def i18n(string_id):
    try:
        return _1CH.get_string(strings.STRINGS[string_id]).encode('utf-8', 'ignore')
    except Exception as e:
        log('Failed String Lookup: %s (%s)' % (string_id, e))
        return string_id

def get_ua():
    try: last_gen = int(_1CH.get_setting('last_ua_create'))
    except: last_gen = 0
    if not _1CH.get_setting('current_ua') or last_gen < (time.time() - (7 * 24 * 60 * 60)):
        index = random.randrange(len(RAND_UAS))
        user_agent = RAND_UAS[index].format(win_ver=random.choice(WIN_VERS), feature=random.choice(FEATURES), br_ver=random.choice(BR_VERS[index]))
        log('Creating New User Agent: %s' % (user_agent), xbmc.LOGDEBUG)
        _1CH.set_setting('current_ua', user_agent)
        _1CH.set_setting('last_ua_create', str(int(time.time())))
    else:
        user_agent = _1CH.get_setting('current_ua')
    return user_agent
