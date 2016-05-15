"""
    1Channel XBMC Addon
    Copyright (C) 2014 tknorris

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
import utils
import time
import urllib2
import urllib
import urlparse
import re
import HTMLParser
import xbmc
import xbmcgui
import os
import math
import socket
from operator import itemgetter
from addon.common.net import Net
from addon.common.addon import Addon
from db_utils import DB_Connection

USER_AGENT = utils.get_ua()
_1CH = Addon('plugin.video.1channel')
ADDON_PATH = _1CH.get_path()
ICON_PATH = os.path.join(ADDON_PATH, 'icon.png')
MAX_RETRIES = 2
TEMP_ERRORS = [500, 502, 503, 504]

class PW_Error(Exception):
    pass

class MyHTTPRedirectHandler(urllib2.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        utils.log('Using Custom Redirect: |%s|%s|%s|%s|%s|' % (req.header_items(), code, msg, headers, newurl), xbmc.LOGDEBUG)
        request = urllib2.HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)
        if request:
            host = request.get_host()
            request.add_header('Host', host)
            request.add_header('Referer', newurl)
            utils.log('Setting Custom Redirect Headers: |%s|' % (request.header_items()), xbmc.LOGDEBUG)
        return request

class PW_Scraper():
    ITEMS_PER_PAGE = 24
    ITEMS_PER_PAGE2 = 40
    MAX_PAGES = 10

    def __init__(self, username, password):
        base_url = _1CH.get_setting('domain')
        base_url = re.sub('https?://', '', base_url)
        scheme = 'https' if _1CH.get_setting('use_https') == 'true' else 'http'
        self.base_url = scheme + '://' + base_url
        if (_1CH.get_setting("enableDomain") == 'true') and (len(_1CH.get_setting("customDomain")) > 10):
            self.base_url = _1CH.get_setting("customDomain")

        self.username = username
        self.password = password
        self.res_pages = -1
        self.res_total = -1
        self.imdb_num = ''

    def add_favorite(self, url):
        utils.log('Saving favorite to website: %s' % (url), xbmc.LOGDEBUG)
        id_num = re.search(r'.+(?:watch|tv)-([\d]+)-', url)
        if id_num:
            save_url = "%s/addtofavs.php?id=%s&whattodo=add"
            save_url = save_url % (self.base_url, id_num.group(1))
            utils.log('Save URL: %s' % (save_url), xbmc.LOGDEBUG)
            html = self.__get_url(save_url, login=True)
            ok_message = "<div class='ok_message'>Movie added to favorites"
            error_message = "<div class='error_message'>This video is already"
            if ok_message in html:
                return
            elif error_message in html:
                raise
            else:
                utils.log('Unable to confirm success', xbmc.LOGWARNING)
                utils.log(html, xbmc.LOGDEBUG)

    def delete_favorite(self, url):
        utils.log('Deleting favorite from website', xbmc.LOGDEBUG)
        id_num = re.search(r'.+(?:watch|tv)-([\d]+)-', url)
        if id_num:
            del_url = "%s/addtofavs.php?id=%s&whattodo=delete"
            del_url = del_url % (self.base_url, id_num.group(1))
            utils.log('Delete URL: %s' % (del_url), xbmc.LOGDEBUG)
            self.__get_url(del_url, login=True)

    def get_favorites(self, section, page=None, paginate=False):
        if section != 'tv': section = 'movies'  # force section to be movies if it's not TV
        utils.log('Getting %s favorite from website' % (section), xbmc.LOGDEBUG)
        fav_url = '/profile.php?user=%s&fav&show=%s'
        if page: fav_url += '&page=%s' % (page)
        url = self.base_url + fav_url % (self.username, section)
        html = self.__get_url(url, login=True)
        r = re.search('strong>Favorites \(\s+([0-9,]+)\s+\)', html)
        self.__set_totals(r, PW_Scraper.ITEMS_PER_PAGE2)

        pattern = '''<div class="index_item"> <a href="(.+?)"><img src="(.+?(\d{1,4})?\.jpg)" width="150" border="0">.+?<td align="center"><a href=".+?">(.+?)</a>'''
        return self.__get_results_gen(html, url, page, paginate, pattern, self.__set_fav_result)

    def __set_fav_result(self, match):
        fav = {}
        link, img, year, title = match
        fav['url'] = self.__fix_url(link)
        fav['img'] = self.__fix_url(img)
        fav['year'] = year
        fav['title'] = title
        return fav

    def get_watched(self, section, page=None, paginate=False):
        utils.log('Getting %s Watched list from website' % (section), xbmc.LOGDEBUG)
        url = '/profile.php?user=%s&watched&show=%s'
        if page: url += '&page=%s' % (page)
        url = self.base_url + url % (self.username, section)
        html = self.__get_url(url, login=True)
        r = re.search('strong>Watched \(\s+([0-9,]+)\s+\)', html)
        self.__set_totals(r, PW_Scraper.ITEMS_PER_PAGE2)

        pattern = '''<div class="index_item"> <a href="(.+?)"><img src="(.+?(\d{1,4})?\.jpg)" width="150" border="0">.+?<td align="center"><a href=".+?">(.+?)</a></td>'''
        return self.__get_results_gen(html, url, page, paginate, pattern, self.__set_watched_result)

    def get_towatch(self, section, page=None, paginate=False):
        utils.log('Getting %s ToWatch list from website' % (section), xbmc.LOGDEBUG)
        url = '/profile.php?user=%s&towatch&show=%s'
        if page: url += '&page=%s' % (page)
        url = self.base_url + url % (self.username, section)
        html = self.__get_url(url, login=True)
        r = re.search('strong>To Watch \(\s+([0-9,]+)\s+\)', html)
        self.__set_totals(r, PW_Scraper.ITEMS_PER_PAGE2)

        pattern = '''<div class="index_item"> <a href="(.+?)"><img src="(.+?(\d{1,4})?\.jpg)" width="150" border="0">.+?<td align="center"><a href=".+?">(.+?)</a></td>'''
        return self.__get_results_gen(html, url, page, paginate, pattern, self.__set_watched_result)

    def __set_watched_result(self, match):
            result = {}
            link, img, year, title = match
            if not year or len(year) != 4: year = ''
            result['url'] = self.__fix_url(link)
            result['img'] = self.__fix_url(img)
            result['year'] = year
            result['title'] = title
            return result

    # returns a generator of results of a title search each of which is a dictionary of url, title, img, and year
    def search(self, section, query, page=None, paginate=False):
        return self.__search(section, urllib.quote_plus(query), page, paginate)

    # returns a generator of results of a description search each of which is a dictionary of url, title, img, and year
    def search_desc(self, section, query, page=None, paginate=False):
        keywords = urllib.quote_plus(query)
        keywords += '&desc_search=1'  # # 1 = Search Descriptions
        return self.__search(section, keywords, page, paginate)

    # returns a generator of results of a advanced search each of which is a dictionary of url, title, img, and year
    def search_advanced(self, section, title, tag, description, country, genre, actor, director, year, month, decade, host='', rating='', advanced='1', page=None, paginate=False):
        keywords = urllib.quote_plus(title)
        if (description == True): keywords += '&desc_search=1'
        keywords += '&tag=' + urllib.quote_plus(tag)
        keywords += '&genre=' + urllib.quote_plus(genre)
        keywords += '&actor_name=' + urllib.quote_plus(actor)
        keywords += '&director=' + urllib.quote_plus(director)
        keywords += '&country=' + urllib.quote_plus(country)
        keywords += '&year=' + urllib.quote_plus(year)
        keywords += '&month=' + urllib.quote_plus(month)
        keywords += '&decade=' + urllib.quote_plus(decade)
        keywords += '&host=' + urllib.quote_plus(host)
        keywords += '&search_rating=' + urllib.quote_plus(rating)  # # Rating higher than (#), 0-4
        keywords += '&advanced=' + urllib.quote_plus(advanced)
        return self.__search(section, keywords, page, paginate)

    # internal search function once a search url is (mostly) built
    def __search(self, section, keywords, page=None, paginate=False):
        search_url = self.base_url + '/index.php?search_keywords='
        search_url += keywords
        html = self. __get_cached_url(self.base_url, cache_limit=0)
        r = re.search('input type="hidden" name="key" value="([0-9a-f]*)"', html)
        if not r:
            raise PW_Error('Unable to locate key. Site Blocked?')

        key = r.group(1)
        search_url += '&key=' + key
        if section == 'tv': search_url += '&search_section=2'
        if page: search_url += '&page=%s' % (page)
        utils.log('Issuing search: %s' % (search_url), xbmc.LOGDEBUG)

        html = self.__get_cached_url(search_url, cache_limit=0)
        r = re.search('number_movies_result">([0-9,]+)', html)
        self.__set_totals(r, PW_Scraper.ITEMS_PER_PAGE)

        pattern = r'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
        return self.__get_results_gen(html, search_url, page, paginate, pattern, self.__set_search_result)

    def __set_search_result(self, match):
            result = {}
            link, title, year, img = match
            result['url'] = self.__fix_url(link)
            result['title'] = title
            result['year'] = year
            result['img'] = self.__fix_url(img)
            return result

    def get_filtered_results(self, section, genre, letter, sort, page=None, paginate=False):
        pageurl = self.base_url + '/?'
        if section == 'tv': pageurl += 'tv'
        if genre: pageurl += '&genre=' + genre
        if letter: pageurl += '&letter=' + letter
        if sort: pageurl += '&sort=' + sort
        if page: pageurl += '&page=%s' % page
        utils.log('Getting filtered results: %s' % (pageurl), xbmc.LOGDEBUG)

        html = self.__get_cached_url(pageurl)

        r = re.search('number_movies_result">([0-9,]+)', html)
        self.__set_totals(r, PW_Scraper.ITEMS_PER_PAGE)

        pattern = r'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
        return self.__get_results_gen(html, pageurl, page, paginate, pattern, self.__set_filtered_result)

    def get_schedule(self):
        page_url = self.base_url + '/tvschedule.php'
        utils.log('Getting Schedule: %s' % (page_url), xbmc.LOGDEBUG)

        html = self.__get_url(page_url, login=True)

        for day_section in html.split('<h2'):
            match = re.search('<span>(.*?)</span>', day_section)
            if match:
                day = match.group(1)
                for episode in re.finditer('class="item".*?href="([^"]+)".*?src="([^"]+)".*?>\s*([^<]+).*?S(\d+)\s+E(\d+):[^>]+>([^<]+)', day_section, re.DOTALL):
                    ep_url, image, show_title, season_num, episode_num, ep_title = episode.groups()
                    yield {'day': day, 'url': ep_url, 'img': image.replace('//', 'https://'), 'show_title': show_title, 'season_num': season_num, 'episode_num': episode_num, 'ep_title': ep_title.strip()}

    def get_playlists(self, public, sort=None, page=None, paginate=True):
        page_url = self.base_url + '/playlists.php?'
        if not public: page_url += 'user=%s' % (self.username)
        if sort: page_url += '&sort=%s' % (sort)
        if page: page_url += '&page=%s' % (page)
        if public:
            html = self.__get_cached_url(page_url)
        else:
            html = self.__get_url(page_url, login=True)

        # doesn't seem to be any way to find out total playlists in page?
        r = re.search('&page=([\d,]+)"> >>', html)
        if r:
            self.res_pages = r.group(1).replace(',', '')
        else:
            self.res_pages = 1

        pattern = r'class="playlist_thumb\".*?img src=\"(.*?)\".*?<strong><a href="(.*?)">\s*(.*?)\s*</a>.*?([\d]+) items.*?([\d]+) Views \|\s*(.*?)\s*\|'
        return self.__get_results_gen(html, page_url, page, paginate, pattern, self.__set_playlists_result)

    def __set_playlists_result(self, match):
        result = {}
        img, url, title, item_count, views, rating = match

        # cleanse playlist title (strips out non-printable chars)
        parser = HTMLParser.HTMLParser()
        title = parser.unescape(title)
        if not isinstance(title, unicode):
            title = unicode(title, 'windows-1252', 'ignore')

        result['img'] = self.__fix_url(img)
        result['url'] = url
        result['title'] = title
        result['item_count'] = item_count
        result['views'] = views
        result['rating'] = rating
        return result

    def show_playlist(self, playlist_url, public, sort=None):
        url = self.base_url + playlist_url
        if sort: url += '&sort=%s' % (sort)
        if public:
            html = self.__get_cached_url(url, 1)
        else:
            html = self.__get_url(url, login=True)
        pattern = r'class="playlist_thumb\".*?img src=\"(.*?)\".*?href=\"(.*?)\">\s*(.*?)\s*<\/a>\s*\(?\s*([\d]*)\s*\)?'
        return self.__get_results_gen(html, url, None, False, pattern, self.__set_playlist_result)

    def __set_playlist_result(self, match):
        result = {}
        img, url, title, year = match
        result['img'] = self.__fix_url(img)
        result['url'] = self.__fix_url('/' + url)
        result['title'] = title
        result['year'] = year
        if url.startswith('tv-'):
            result['video_type'] = 'tvshow'
        else:
            result['video_type'] = 'movie'
        return result

    def remove_from_playlist(self, playlist_url, item_url):
        utils.log('Removing item: %s from playlist %s' % (item_url, playlist_url), xbmc.LOGDEBUG)
        return self.__manage_playlist(playlist_url, item_url, 'remove_existing')

    def add_to_playlist(self, playlist_url, item_url):
        utils.log('Adding item %s to playlist %s' % (item_url, playlist_url), xbmc.LOGDEBUG)
        return self.__manage_playlist(playlist_url, item_url, 'add_existing')

    def __manage_playlist(self, playlist_url, item_url, action):
        playlist_id = re.search('\?id=(\d+)', playlist_url).group(1)
        item_id = re.search('/watch-(\d+)-', item_url).group(1)
        url = self.base_url + '/playlists.php?plistitemid=%s&whattodo=%s&edit=%s' % (item_id, action, playlist_id)
        html = self.__get_url(url, login=True)
        ok_message = "ok_message'>"
        if ok_message in html:
            return
        else:
            raise

    def get_genres(self):
        html = self.__get_cached_url(self.base_url, cache_limit=24)
        regex = re.compile('class="opener-menu-genre">(.*?)</ul>', re.DOTALL)
        genre_frag = regex.search(html).group(1)
        return re.findall('genre=(.*?)\"', genre_frag)

    def __set_filtered_result(self, match):
        result = {}
        link, title, year, img = match
        result['url'] = self.__fix_url(link)
        result['img'] = self.__fix_url(img)
        result['year'] = year
        result['title'] = title
        return result

    # generic PW results parser. takes the html of the first result set, the base url of that set, what page to return,
    # whether or not to paginate, the pattern of match on, and a helper functon to set the return result
    def __get_results_gen(self, html, url, page, paginate, pattern, set_result):
        if not page: page = 1
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        while True:
            result = {}
            for item in regex.finditer(html):
                result = set_result(item.groups())
                result['title'] = result['title'].strip()
                if 'year' in result and (not result['year'] or len(result['year']) != 4): result['year'] = ''
                yield result

            # if we're not paginating, then keep yielding until we run out of pages or hit the max
            if not paginate:
                if html.find('> >> <') == -1 or int(page) > PW_Scraper.MAX_PAGES:
                    break

                page += 1
                pageurl = '%s&page=%s' % (url, page)
                html = self.__get_cached_url(pageurl, cache_limit=0)
            # if we are paginating, just do this page
            else:
                break

    def get_last_res_pages(self):
        return self.res_pages

    def get_last_res_total(self):
        return self.res_total

    def get_last_imdbnum(self):
        return self.imdb_num

    def get_sources(self, url):
        html = self.__get_cached_url(self.base_url + url, cache_limit=2)
        adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
        adult = re.search(adultregex, html, re.DOTALL)
        if adult:
            utils.log('Adult content url detected')
            adulturl = self.base_url + adult.group(1)
            headers = {'Referer': url}
            html = self.__get_url(adulturl, headers=headers, login=True)

        imdbregex = 'mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7}).*?"'
        match = re.search(imdbregex, html)
        if match:
            self.imdb_num = match.group(1)

        sort_order = []
        if _1CH.get_setting('sorting-enabled') == 'true':
            sort_tiers = ('first-sort', 'second-sort', 'third-sort', 'fourth-sort', 'fifth-sort')
            sort_methods = (None, 'host', 'verified', 'quality', 'views', 'multi-part')
            for tier in sort_tiers:
                if int(_1CH.get_setting(tier)) > 0:
                    method = sort_methods[int(_1CH.get_setting(tier))]
                    if _1CH.get_setting(tier + '-reversed') == 'true':
                        method = '-%s' % method
                    sort_order.append(method)
                else: break

        hosters = []
        container_pattern = r'<table[^>]+class="movie_version[ "][^>]*>(.*?)</table>'
        item_pattern = (
            r'quality_(?!sponsored|unknown)([^>]*)></span>.*?'
            r'url=([^&]+)&(?:amp;)?domain=([^&"]+)[^>]*(.*?)'
            r'"version_veiws"> ([\d]+) views</')
        for container in re.finditer(container_pattern, html, re.DOTALL | re.IGNORECASE):
            for source in re.finditer(item_pattern, container.group(1), re.DOTALL):
                qual, url, host, parts, views = source.groups()

                if host == 'ZnJhbWVndGZv': continue  # filter out promo hosts
                item = {'host': host.decode('base-64'), 'url': url.decode('base-64')}
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

                if sort_order:
                    hosters = self.__multikeysort(hosters, sort_order, functions={'host': utils.rank_host})

        return hosters

    def get_season_list(self, url, cached=True):
        utils.log('Getting season list (%s): %s' % (cached, url), xbmc.LOGDEBUG)
        if cached:
            html = self.__get_cached_url(self.base_url + url)
        else:
            html = self.__get_url(self.base_url + url)

        adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
        r = re.search(adultregex, html, re.DOTALL)
        if r:
            utils.log('Adult content url detected')
            adulturl = self.base_url + r.group(1)
            headers = {'Referer': url}
            html = self.__get_url(adulturl, headers=headers, login=True)

        match = re.search('mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7}).*?"', html)
        self.imdb_num = match.group(1) if match else ''
        return self.__season_gen(html)

    def change_watched(self, primewire_url, action, whattodo):
        if not utils.website_is_integrated(): return

        utils.log("Update Website %s List" % action.capitalize(), xbmc.LOGDEBUG)
        id_num = re.search(r'.+(?:watch|tv)-([\d]+)-', primewire_url)
        if id_num:
            change_url = '%s/addtowatched.php?id=%s&action=%s&whattodo=%s'
            change_url = change_url % (self.base_url, id_num.group(1), action.lower(), whattodo.lower())
            utils.log('%s %s URL: %s' % (whattodo.capitalize(), action.capitalize(), change_url), xbmc.LOGDEBUG)
            self.__get_url(change_url, login=True)
        else:
            utils.log("pw.scraper.change_watched() couldn't scrape primewire ID", xbmc.LOGWARNING)

    def __set_totals(self, r, items_per_page):
        if r:
            total = int(r.group(1).replace(',', ''))
        else:
            total = 0
        self.res_pages = int(math.ceil(total / float(items_per_page)))
        self.res_total = total

    def __season_gen(self, html):
        match = re.search('tv_container(.+?)<div class="clearer', html, re.DOTALL)
        if not match:
            raise StopIteration()

        show_container = match.group(1)
        season_containers = show_container.split('<h2>')

        for season_html in season_containers:
            r = re.search(r'<a[^<]+Season (\d+)<', season_html)
            if r:
                season_label = r.group(1)
                yield (season_label, season_html)

    def __fix_url(self, url):
        if url.startswith('//'): url = urlparse.urlsplit(self.base_url).scheme + ':' + url
        url = url.replace('/tv-', '/watch-', 1)  # force tv urls to be consistent w/ movies
        url = url.replace('-online-free', '')  # strip off the -online-free at the end to make all urls match
        return url

    def __get_url(self, url, headers={}, login=False):
        before = time.time()
        html = self.__http_get_with_retry_1(url, headers)
        if login and not '<a href="/logout.php"' in html:
            utils.log('Logging in for url %s' % url, xbmc.LOGDEBUG)
            if self.__login(self.base_url):
                html = self.__http_get_with_retry_1(url, headers)
            else:
                html = ''
                utils.log("Login failed for %s getting: %s" % (self.username, url), xbmc.LOGERROR)

        # addon.net tries to use page's Content Type to convert to unicode
        # if it fails (usually because the data in the page doesn't match the Content Type), then the page encoding is left as-is
        # This then tries again with w-1252 code page which is the least restrictive
        if not isinstance(html, unicode):
            html = unicode(html, 'windows-1252', 'ignore')

        after = time.time()
        utils.log('Url Fetch took: %.2f secs' % (after - before), xbmc.LOGDEBUG)
        return html

    def __get_cached_url(self, url, cache_limit=8):

        utils.log('Fetching Cached URL: %s' % url, xbmc.LOGDEBUG)
        before = time.time()

        db_connection = DB_Connection()
        html = db_connection.get_cached_url(url, cache_limit)
        if html:
            utils.log('Returning cached result for: %s' % (url), xbmc.LOGDEBUG)
            return html

        utils.log('No cached url found for: %s' % url, xbmc.LOGDEBUG)
        req = urllib2.Request(url)

        host = urlparse.urlparse(self.base_url).hostname
        req.add_header('User-Agent', USER_AGENT)
        req.add_unredirected_header('Host', host)
        req.add_unredirected_header('Referer', self.base_url)

        try:
            body = self.__http_get_with_retry_2(url, req)
            if '<title>Are You a Robot?</title>' in body:
                utils.log('bot detection')

                # download the captcha image and save it to a file for use later
                captchaimgurl = 'http://' + host + '/CaptchaSecurityImages.php'
                captcha_save_path = xbmc.translatePath('special://userdata/addon_data/plugin.video.1channel/CaptchaSecurityImage.jpg')
                req = urllib2.Request(captchaimgurl)
                host = urlparse.urlparse(self.base_url).hostname
                req.add_header('User-Agent', USER_AGENT)
                req.add_header('Host', host)
                req.add_header('Referer', self.base_url)
                response = urllib2.urlopen(req)
                the_img = response.read()
                with open(captcha_save_path, 'wb') as f:
                    f.write(the_img)

                # now pop open dialog for input
                # TODO: make the size and loc configurable
                img = xbmcgui.ControlImage(550, 15, 240, 100, captcha_save_path)
                wdlg = xbmcgui.WindowDialog()
                wdlg.addControl(img)
                wdlg.show()
                kb = xbmc.Keyboard('', 'Type the letters in the image', False)
                kb.doModal()
                capcode = kb.getText()
                if (kb.isConfirmed()):
                    userInput = kb.getText()
                if userInput != '':
                    # post back user string
                    wdlg.removeControl(img)
                    capcode = kb.getText()
                    data = {'security_code': capcode,
                            'not_robot': 'I\'m Human! I Swear!'}
                    data = urllib.urlencode(data)
                    roboturl = 'http://' + host + '/are_you_a_robot.php'
                    req = urllib2.Request(roboturl)
                    host = urlparse.urlparse(self.base_url).hostname
                    req.add_header('User-Agent', USER_AGENT)
                    req.add_header('Host', host)
                    req.add_header('Referer', self.base_url)
                    response = urllib2.urlopen(req, data)
                    body = self.__get_url(url)

                elif userInput == '':
                    dialog = xbmcgui.Dialog()
                    dialog.ok("Robot Check", "You must enter text in the image to continue")
                wdlg.close()

            if not isinstance(html, unicode):
                body = unicode(body, 'windows-1252', 'ignore')
            parser = HTMLParser.HTMLParser()
            body = parser.unescape(body)
        except Exception as e:
            dialog = xbmcgui.Dialog()
            dialog.ok("Connection failed", "Failed to connect to url", url)
            utils.log('Failed to connect to URL %s: %s' % (url, str(e)), xbmc.LOGERROR)
            return ''

        db_connection.cache_url(url, body)
        after = time.time()
        utils.log('Cached Url Fetch took: %.2f secs' % (after - before), xbmc.LOGDEBUG)
        return body

    def __login(self, redirect):
        url = self.base_url + '/login.php'
        net = Net()
        cookiejar = _1CH.get_profile()
        cookiejar = os.path.join(cookiejar, 'cookies')
        host = urlparse.urlparse(self.base_url).hostname
        headers = {'Referer': redirect, 'Host': host, 'User-Agent': USER_AGENT}
        form_data = {'username': self.username, 'password': self.password, 'remember': 'on', 'login_submit': 'Login'}
        html = net.http_POST(url, headers=headers, form_data=form_data).content
        utils.log(html)
        if '<a href="/logout.php"' in html:
            net.save_cookies(cookiejar)
            return True
        else:
            return False

    def __http_get_with_retry_1(self, url, headers):
        utils.log('Fetching URL: %s' % url, xbmc.LOGDEBUG)
        net = Net()
        cookiejar = _1CH.get_profile()
        cookiejar = os.path.join(cookiejar, 'cookies')
        net.set_cookies(cookiejar)
        retries = 0
        html = None
        while retries <= MAX_RETRIES:
            try:
                html = net.http_GET(url, headers=headers).content
                # if no exception, jump out of the loop
                break
            except socket.timeout:
                retries += 1
                utils.log('Retry #%s for URL %s because of timeout' % (retries, url), xbmc.LOGWARNING)
                continue
            except urllib2.HTTPError as e:
                # if it's a temporary code, retry
                if e.code in TEMP_ERRORS:
                    retries += 1
                    utils.log('Retry #%s for URL %s because of HTTP Error %s' % (retries, url, e.code), xbmc.LOGWARNING)
                    continue
                # if it's not pass it back up the stack
                else:
                    raise
        else:
            raise

        return html

    def __http_get_with_retry_2(self, url, request):
        utils.log('Fetching URL: %s' % request.get_full_url(), xbmc.LOGDEBUG)
        retries = 0
        html = None
        while retries <= MAX_RETRIES:
            try:
                opener = urllib2.build_opener(MyHTTPRedirectHandler)
                urllib2.install_opener(opener)
                response = urllib2.urlopen(request, timeout=30)
                html = response.read()
                # if no exception, jump out of the loop
                break
            except socket.timeout:
                retries += 1
                utils.log('Retry #%s for URL %s because of timeout' % (retries, url), xbmc.LOGWARNING)
                continue
            except urllib2.HTTPError as e:
                # if it's a temporary code, retry
                if e.code in TEMP_ERRORS:
                    retries += 1
                    utils.log('Retry #%s for URL %s because of HTTP Error %s' % (retries, url, e.code), xbmc.LOGWARNING)
                    continue
                # if it's not pass it back up the stack
                else:
                    raise
        else:
            raise

        response.close()
        return html

    def __multikeysort(self, items, columns, functions=None, getter=itemgetter):
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
