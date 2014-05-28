import os
import re
import sys
import xbmc
import xbmcgui
import xbmcplugin

# from functools import wraps

from addon.common.addon import Addon

_1CH = Addon('plugin.video.1channel', sys.argv)

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

        _1CH.log('Loading MySQL as DB engine')
        DB = 'mysql'
    else:
        _1CH.log('MySQL not enabled or not setup correctly')
        raise ValueError('MySQL not enabled or not setup correctly')
except:
    try:
        from sqlite3 import dbapi2 as orm

        _1CH.log('Loading sqlite3 as DB engine')
    except:
        from pysqlite2 import dbapi2 as orm

        _1CH.log('pysqlite2 as DB engine')
    DB = 'sqlite'
    __translated__ = xbmc.translatePath("special://database")
    DB_DIR = os.path.join(__translated__, 'onechannelcache.db')

    
def connect_db():
    if DB == 'mysql':
        db = orm.connect(database=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_ADDR, buffered=True)
    else:
        db = orm.connect(DB_DIR)
        db.text_factory = str
    return db


def format_label_tvshow(info):
    if 'premiered' in info:
        year = info['premiered'][:4]
    else:
        year = ''
    title = info['title']
    label = _1CH.get_setting('format-tvshow')
    # label = label.replace('{t}', title)
    # label = label.replace('{y}', year)
    # label = label.replace('{ft}', format_tvshow_title(title))
    # label = label.replace('{fy}', format_tvshow_year(year))

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
    label = re.sub('\{e\}', str(info['episode']), label)
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
    #label = label.replace('{t}', title)
    #label = label.replace('{y}', year)
    #label = label.replace('{ft}', format_movie_title(title))
    #label = label.replace('{fy}', format_movie_year(year))
    label = re.sub('\{t\}', info['title'], label)
    label = re.sub('\{y\}', year, label)
    label = re.sub('\{ft\}', format_movie_title(info['title']), label)
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
    if info['multi-part']:
        parts = 'part 1'
    else:
        parts = ''
    label = re.sub('\{p\}', parts, label)
    if info['verified']: label = format_label_source_verified(label)
    return label


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
            _1CH.log('New version found')
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


def flush_cache():
    dlg = xbmcgui.Dialog()
    ln1 = 'Are you sure you want to '
    ln2 = 'delete the url cache?'
    ln3 = 'This will slow things down until rebuilt'
    yes = 'Keep'
    no = 'Delete'
    ret = dlg.yesno('Flush web cache', ln1, ln2, ln3, yes, no)
    if ret:
        db = connect_db()
        if DB == 'mysql':
            sql = 'TRUNCATE TABLE url_cache'
        else:
            sql = 'DELETE FROM url_cache'
        cur = db.cursor()
        cur.execute(sql)
        db.commit()
        db.close()  


def upgrade_db():
    _1CH.log('Upgrading db...')
    for table in ('subscriptions', 'favorites'):
        sql = "UPDATE %s SET url = replace(url, 'http://www.1channel.ch', '')" % table
        db = connect_db()
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
                    _1CH.log("processing file: %s" % current_file)
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
                        _1CH.log('Writing new content: %s' % new_content)
                        target.write(new_content)
        
        
class TextBox:
    # constants
    WINDOW = 10147
    CONTROL_LABEL = 1
    CONTROL_TEXTBOX = 5

    def __init__(self, *args, **kwargs):
        # activate the text viewer window
        xbmc.executebuiltin("ActivateWindow(%d)" % ( self.WINDOW, ))
        # get window
        self.win = xbmcgui.Window(self.WINDOW)
        # give window time to initialize
        xbmc.sleep(1000)
        self.setControls()

    def setControls(self):
        # set heading
        heading = "PrimeWire v%s" % (_1CH.get_version())
        self.win.getControl(self.CONTROL_LABEL).setLabel(heading)
        # set text
        root = _1CH.get_path()
        faq_path = os.path.join(root, 'help.faq')
        f = open(faq_path)
        text = f.read()
        self.win.getControl(self.CONTROL_TEXTBOX).setText(text)


def website_is_integrated():
    enabled = _1CH.get_setting('site_enabled') == 'true'
    user = _1CH.get_setting('usename') is not None
    passwd = _1CH.get_setting('passwd') is not None
    return enabled and user and passwd


def login_and_retry(redirect):
    _1CH.log('Logging in for url %s' % redirect)
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
        _1CH.log('Failed to login')
        print html


def migrate_to_mysql():
    try:
        from sqlite3 import dbapi2 as sqlite
        _1CH.log('Loading sqlite3 for migration')
    except:
        from pysqlite2 import dbapi2 as sqlite
        _1CH.log('pysqlite2 for migration')

    DB_NAME = _1CH.get_setting('db_name')
    DB_USER = _1CH.get_setting('db_user')
    DB_PASS = _1CH.get_setting('db_pass')
    DB_ADDR = _1CH.get_setting('db_address')

    DB_DIR = os.path.join(xbmc.translatePath("special://database"), 'onechannelcache.db')
    sqlite_db = sqlite.connect(DB_DIR)
    mysql_db = orm.connect(database=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_ADDR, buffered=True)
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
    from metahandler import metahandlers
    __metaget__ = metahandlers.MetaData()
    search_title = new_title if new_title else old_title
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
    if search_meta:
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

            _1CH.log(search_meta[index - 1])
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
    for dirpath, dirnames, filenames in os.walk(start_path):
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

        
        # import cProfile

        # def profiled(func):
        # def wrapper(*args, **kwargs):
        # datafn = func.__name__ + ".profile" # Name the data file sensibly
        # datapath = os.path.join(addon.get_profile(), datafn)
        # prof = cProfile.Profile()
        # retval = prof.runcall(func, *args, **kwargs)
        # prof.dump_stats(datapath)
        # return retval
        # return wrapper
