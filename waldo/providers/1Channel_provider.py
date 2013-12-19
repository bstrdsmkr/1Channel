import os
import re
import sys
import urllib
import urllib2
import HTMLParser
from t0mm0.common.net import Net
from t0mm0.common.addon import Addon

addon = Addon('plugin.video.1channel', sys.argv)
BASE_URL = addon.get_setting('domain')
if ((addon.get_setting("enableDomain"))=='true') and (len(addon.get_setting("customDomain")) > 10):
	BASE_URL=addon.get_setting("customDomain")
display_name = 'PrimeWire'
required_addons = []
tag = 'PWr'


def get_settings_xml():
    return False


def get_results(vid_type, title, year, imdb, tvdb, season, episode):
    if vid_type == 'movie':
        return Search('movies', title, imdb)
    elif vid_type == 'tvshow':
        return _get_tvshows(title, year, imdb, tvdb)
    elif vid_type == 'season':
        return _get_season(title, year, imdb, tvdb, season)
    elif vid_type == 'episode':
        return _get_episodes(title, year, imdb, tvdb, season, episode)


def GetURL(url):
    try: addon.log('Fetching URL: %s' % url)
    except: pass

    USER_AGENT = 'User-Agent:Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.56'
    req = urllib2.Request(url)

    req.add_header('User-Agent', USER_AGENT)
    host = re.sub('http://', '', BASE_URL)
    req.add_header('Host', host)
    req.add_header('Referer', BASE_URL)

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


def Search(section, query, imdb):
    html = GetURL(BASE_URL)
    r = re.search('input type="hidden" name="key" value="([0-9a-f]*)"', html).group(1)
    search_url = BASE_URL + '/index.php?search_keywords='
    search_url += urllib.quote_plus(query)
    search_url += '&key=' + r
    if section == 'tv':
        search_url += '&search_section=2'
        video_type = 'tvshow'
    else:
        video_type = 'movie'

    html = GetURL(search_url)

    r = 'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
    regex = re.search(r, html, re.DOTALL)
    if regex:
        url, title, year, thumb = regex.groups()
        net = Net()
        cookiejar = addon.get_profile()
        cookiejar = os.path.join(cookiejar, 'cookies')
        net.set_cookies(cookiejar)
        html = net.http_GET(BASE_URL + url).content
        net.save_cookies(cookiejar)
        adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
        r = re.search(adultregex, html, re.DOTALL)
        if r:
            try: addon.log('Adult content url detected')
            except: pass
            adulturl = BASE_URL + r.group(1)
            headers = {'Referer': url}
            net.set_cookies(cookiejar)
            html = net.http_GET(adulturl, headers=headers).content
            net.save_cookies(cookiejar)

        for version in re.finditer('<table[^\n]+?class="movie_version(?: movie_version_alt)?">(.*?)</table>',
                                   html, re.DOTALL | re.IGNORECASE):
            for s in re.finditer('quality_(?!sponsored|unknown)(.*?)></span>.*?' +
                                         'url=(.*?)&(?:amp;)?domain=(.*?)&(?:amp;)?(.*?)' +
                                         '"version_veiws"> ([\d]+) views</',
                                 version.group(1), re.DOTALL):
                q, url, host, parts, views = s.groups()
                q = q.upper()
                url = url.decode('base-64')
                host = host.decode('base-64')
                disp_title = '[%s] %s (%s views)' % (q, host, views)
                result = {'tag': tag, 'provider_name': display_name}
                qs = {'url': url, 'title': title, 'img': thumb, 'year': year, 'imdbnum': imdb, 'video_type': video_type, 'strm': True, 'mode': 'PlaySource'}
                result['li_url'] = 'plugin://plugin.video.1channel/?%s' % urllib.urlencode(qs)
                print result['li_url']
                result['info_labels'] = {'title': disp_title}
                yield result
