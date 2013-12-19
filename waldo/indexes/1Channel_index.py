import os
import re
import sys
import urllib2
import HTMLParser

import xbmcgui
import xbmcplugin
from t0mm0.common.addon import Addon
from t0mm0.common.addon import Addon as Addon2

addon = Addon('plugin.video.waldo', sys.argv)
_1CH = Addon2('plugin.video.1channel', sys.argv)

#BASE_Address = 'www.primewire.ag'
BASE_Address = _1CH.get_setting('domain').replace('http://','')
if (_1CH.get_setting("enableDomain")=='true') and (len(_1CH.get_setting("customDomain")) > 10):
	BASE_Address=_1CH.get_setting("customDomain").replace('http://','')
if not BASE_Address.startswith('http'):
    BASE_URL = 'http://'+BASE_Address

display_name = 'PrimeWire'#'1Channel'
#Label that will be displayed to the user representing this index

tag = 'PrimeWire'#'1Channel'
#MUST be implemented. Unique 3 or 4 character string that will be used to
#identify this index

required_addons = []
#MUST be implemented. A list of strings indicating which addons are required to
#be installed for this index to be used.
#For example: required_addons = ['script.module.beautifulsoup', 'plugin.video.youtube']
#Currently, xbmc does not provide a way to require a specific version of an addon

def get_settings_xml():
    """
    Must be defined. This method should return XML which describes any Waldo
    specific settings you would like for your plugin. You should make sure that
    the ``id`` starts with your tag followed by an underscore.

    For example:
        xml = '<setting id="ExI_priority" '
        xml += 'type="number" label="Priority" default="100"/>\\n'
        return xml

    The settings category will be your plugin's :attr:`display_name`.

    Returns:
        A string containing XML which would be valid in
        ``resources/settings.xml`` or boolean False if none are required
    """
    return False


def get_browsing_options():#MUST be defined
    """
    Returns a list of dicts. Each dict represents a different method of browsing
    this index. The following keys MUST be provided:
    'name': Label to display to the user to represent this browsing method
    'function': A function (defined in this index) which will be executed when
        the user selects this browsing method. This function should describe
        and add the list items to the directory, and assume flow control from
        this point on.
    Once the user indicates the content they would like to search the providers
    for (usually via selecting a list item), plugin.video.waldo should be called
    with the following parameters (again usually via listitem):
        mode = 'GetAllResults'
        type = either 'movie', 'tvshow', 'season', or 'episode'
        title = The title string to look for
        year = The release year of the desired movie, or premiere date of the
            desired tv show.
        imdb = The imdb id of the movie or tvshow to find sources for
        tvdb = The tvdb id of the movie or tvshow to find sources for
        season = The season number for which to return results.
            If season is supplied, but not episode, all results for that season
            should be returned
        episode: The episode number for which to return results
    """
    option_1 = {'name': 'Tv Shows', 'function': 'BrowseListMenu', 'kwargs': {'section': 'tv'}}

    option_2 = {'name': 'Movies', 'function': 'BrowseListMenu', 'kwargs': {'section': 'movies'}}

    return [option_1, option_2]


def callback(params):
    """
    MUST be implemented. This method will be called when the user selects a
    listitem you created. It will be passed a dict of parameters you passed to
    the listitem's url.
    For example, the following listitem url:
        plugin://plugin.video.waldo/?mode=main&section=tv&api_key=1234
     Will call this function with:
        {'mode':'main', 'section':'tv', 'api_key':'1234'}
    """
    try: addon.log('%s was called with the following parameters: %s' % (params.get('receiver', ''), params))
    except: pass
    sort_by = params.get('sort', None)
    section = params.get('section')
    if sort_by: GetFilteredResults(section, sort=sort_by)


def BrowseListMenu(section): #This must match the 'function' key of an option from get_browsing_options
    addon.add_directory({'section': section, 'sort': 'featured'}, {'title': 'Featured'}, img=art('featured.png'),
                        fanart=art('fanart.png'))
    addon.add_directory({'section': section, 'sort': 'views'}, {'title': 'Most Popular'}, img=art('most_popular.png'),
                        fanart=art('fanart.png'))
    addon.add_directory({'section': section, 'sort': 'ratings'}, {'title': 'Highly rated'}, img=art('highly_rated.png'),
                        fanart=art('fanart.png'))
    addon.add_directory({'section': section, 'sort': 'release'}, {'title': 'Date released'},
                        img=art('date_released.png'), fanart=art('fanart.png'))
    addon.add_directory({'section': section, 'sort': 'date'}, {'title': 'Date added'}, img=art('date_added.png'),
                        fanart=art('fanart.png'))
    addon.end_of_directory()


def art(filename):
    adn = Addon('plugin.video.1channel', sys.argv)
    THEME_LIST = ['mikey1234', 'Glossy_Black', 'PrimeWire']
    THEME = THEME_LIST[int(adn.get_setting('theme'))]
    THEME_PATH = os.path.join(adn.get_path(), 'art', 'themes', THEME)
    img = os.path.join(THEME_PATH, filename)
    return img


def GetFilteredResults(section=None, genre=None, letter=None, sort='alphabet', page=None): #3000
    try: addon.log('Filtered results for Section: %s Genre: %s Letter: %s Sort: %s Page: %s' % (section, genre, letter, sort, page))
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

    html = GetURL(pageurl)

    r = re.search('number_movies_result">([0-9,]+)', html)
    if r:
        total = int(r.group(1).replace(',', ''))
    else:
        total = 0
    total_pages = total / 24
    total = min(total, 24)

    r = 'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
    regex = re.finditer(r, html, re.DOTALL)
    resurls = []
    for s in regex:
        resurl, title, year, thumb = s.groups()
        if resurl not in resurls:
            resurls.append(resurl)
            li_title = '%s (%s)' % (title, year)
            li = xbmcgui.ListItem(li_title, iconImage=thumb, thumbnailImage=thumb)
            if section == 'tv':
                section = 'tvshow'
            else:
                section = 'movie'
            queries = {'waldo_mode': 'GetAllResults', 'title': title, 'vid_type': section}
            li_url = addon.build_plugin_url(queries)
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), li_url, li,
                                        isFolder=True, totalItems=total)

    if html.find('> >> <') > -1:
        label = 'Skip to Page...'
        command = addon.build_plugin_url(
            {'mode': 'PageSelect', 'pages': total_pages, 'section': section, 'genre': genre, 'letter': letter,
             'sort': sort})
        command = 'RunPlugin(%s)' % command
        cm = [(label, command)]
        meta = {'title': 'Next Page >>'}
        addon.add_directory(
            {'mode': 'CallModule', 'receiver': 'PrimeWire', 'ind_path': os.path.dirname(__file__), 'section': section,
             'genre': genre, 'letter': letter, 'sort': sort, 'page': page},
            meta, cm, True, art('nextpage.png'), art('fanart.png'), is_folder=True)
    addon.end_of_directory()


def GetURL(url, params=None, referrer=BASE_URL):
    try: addon.log('Fetching URL: %s' % url)
    except: pass

    USER_AGENT = 'User-Agent:Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.56'
    if params:
        req = urllib2.Request(url, params)
    else:
        req = urllib2.Request(url)

    req.add_header('User-Agent', USER_AGENT)
    req.add_header('Host', BASE_Address) #'www.primewire.ag'
    req.add_header('Referer', referrer)

    try:
        response = urllib2.urlopen(req, timeout=10)
        body = response.read()
        body = unicode(body, 'iso-8859-1')
        h = HTMLParser.HTMLParser()
        body = h.unescape(body)
    except Exception, e:
        try: addon.log('Failed to connect to %s: %s' % (url, e))
        except: pass
        return ''

    return body.encode('utf-8')