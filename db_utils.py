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
import os
import urllib
import time
import xbmc
import xbmcvfs
from addon.common.addon import Addon
import utils

def enum(**enums):
    return type('Enum', (), enums)

DB_TYPES= enum(MYSQL='mysql', SQLITE='sqlite')

_1CH = Addon('plugin.video.1channel')

class DB_Connection():
    def __init__(self):
        global db_lib
        self.dbname = _1CH.get_setting('db_name')
        self.username = _1CH.get_setting('db_user')
        self.password = _1CH.get_setting('db_pass')
        self.address = _1CH.get_setting('db_address')
        self.db=None
        
        if _1CH.get_setting('use_remote_db') == 'true':
            if self.address is not None and self.username is not None \
            and self.password is not None and self.dbname is not None:
                import mysql.connector as db_lib
                _1CH.log('Loading MySQL as DB engine')
                self.db_type = DB_TYPES.MYSQL
            else:
                _1CH.log('MySQL is enabled but not setup correctly')
                raise ValueError('MySQL enabled but not setup correctly')
        else:
            try:
                from sqlite3 import dbapi2 as db_lib
                _1CH.log('Loading sqlite3 as DB engine')
            except:
                from pysqlite2 import dbapi2 as db_lib
                _1CH.log('pysqlite2 as DB engine')
            self.db_type = DB_TYPES.SQLITE
            db_dir = xbmc.translatePath("special://database")
            self.db_path = os.path.join(db_dir, 'onechannelcache.db')
        self.__connect_to_db()
    
    def flush_cache(self):
        sql = 'DELETE FROM url_cache'
        self.__execute(sql)

    # return the bookmark for the requested url or None if not found
    def get_bookmark(self,url):
        if not url: return None
        sql='SELECT resumepoint FROM new_bkmark where url=?'
        bookmark = self.__execute(sql, (url,))
        if bookmark:
            return bookmark[0][0]
        else:
            return None

    # return true if bookmark exists
    def bookmark_exists(self, url):
        return self.get_bookmark(url) != None
    
    def set_bookmark(self, url,offset):
        if not url: return
        sql = 'REPLACE INTO new_bkmark (url, resumepoint) VALUES(?,?)'
        self.__execute(sql, (url,offset))
        
    def clear_bookmark(self, url):
        if not url: return
        sql = 'DELETE FROM new_bkmark WHERE url=?'
        self.__execute(sql, (url,))

    def get_favorites(self, section):
        sql = 'SELECT type, name, url, year FROM favorites'
        if section:
            sql = sql + self.__format(' WHERE type = ? ORDER BY NAME')
            favs=self.__execute(sql, (section,))
        else:
            favs=self.__execute(sql)
        return favs
    
    def get_favorites_count(self, section=None):
        sql = 'SELECT count(*) FROM favorites'
        if section:
            sql = sql + self.__format(' WHERE type = ?')
            rows=self.__execute(sql, (section,))
        else:
            rows=self.__execute(sql)

        return rows[0][0]
    
    def save_favorite(self, fav_type, name, url, year):
        sql = 'INSERT INTO favorites (type, name, url, year) VALUES (?, ?, ?, ?)'
        try:
            title = urllib.unquote_plus(unicode(name, 'latin1'))
            self.__execute(sql, (fav_type, title, url, year))
        except db_lib.IntegrityError:
            raise
        
    # delete a list of favorites, urls must be a list
    def delete_favorites(self, urls):
        url_string=', '.join('?' for _ in urls)
        sql = self.__format('DELETE FROM favorites WHERE url in ('+url_string+')')
        self.__execute(sql, urls)
        
    def delete_favorite(self, url):
        self.delete_favorites([url])

    def get_subscriptions(self, day=None):
        sql = 'SELECT url, title, img, year, imdbnum FROM subscriptions'
        params = []
        if day:
            sql += ' WHERE day = ?'
            params = [day]
            
        rows=self.__execute(sql, params)
        return rows
    
    def add_subscription(self, url, title, img, year, imdbnum, day):
        sql = 'INSERT INTO subscriptions (url, title, img, year, imdbnum, day) VALUES (?, ?, ?, ?, ?, ?)'
        self.__execute(sql, (url, title, img, year, imdbnum, day))

    def delete_subscription(self, url):
        sql = 'DELETE FROM subscriptions WHERE url=?'
        self.__execute(sql, (url,))

    def cache_url(self,url,body):
        now = time.time()
        sql = 'REPLACE INTO url_cache (url,response,timestamp) VALUES(?, ?, ?)'
        self.__execute(sql, (url, body, now))
    
    def get_cached_url(self, url, cache_limit=8):
        html=''
        now = time.time()
        limit = 60 * 60 * cache_limit
        sql = 'SELECT * FROM url_cache WHERE url = ?'
        rows=self.__execute(sql, (url,))
            
        if rows:
            created = float(rows[0][2])
            age = now - created
            if age < limit:
                html=rows[0][1]
        return html
    
    def cache_season(self, season_num,season_html):
        sql = 'REPLACE INTO seasons(season,contents) VALUES(?, ?)'        
        self.__execute(sql, (season_num, season_html))
    
    def get_cached_season(self, season_num):
        sql = 'SELECT contents FROM seasons WHERE season=?'
        season_html=self.__execute(sql, (season_num,))[0][0]
        return season_html

    def execute_sql(self, sql):
        self.__execute(sql)

    # intended to be a common method for creating a db from scratch
    def init_database(self):
        _1CH.log('Building PrimeWire Database')
        if self.db_type == DB_TYPES.MYSQL:
            self.__execute('CREATE TABLE IF NOT EXISTS seasons (season INTEGER UNIQUE, contents TEXT)')
            self.__execute('CREATE TABLE IF NOT EXISTS favorites (type VARCHAR(10), name TEXT, url VARCHAR(255) UNIQUE, year VARCHAR(10))')
            self.__execute('CREATE TABLE IF NOT EXISTS subscriptions (url VARCHAR(255) UNIQUE, title TEXT, img TEXT, year TEXT, imdbnum TEXT, day TEXT)')
            self.__execute('CREATE TABLE IF NOT EXISTS url_cache (url VARCHAR(255), response MEDIUMBLOB, timestamp TEXT)')
            self.__execute('CREATE TABLE IF NOT EXISTS db_info (setting TEXT, value TEXT)')
            self.__execute('CREATE TABLE IF NOT EXISTS new_bkmark (url VARCHAR(255) PRIMARY KEY NOT NULL, resumepoint DOUBLE NOT NULL)')            
            try: self.__execute('DROP INDEX unique_db_info ON db_info')
            except: pass # ignore failures if the index doesn't exist
            self.__execute('CREATE UNIQUE INDEX unique_db_info ON db_info (setting (255))')
        else:
            self.__create_sqlite_db()
            self.__execute('CREATE TABLE IF NOT EXISTS seasons (season UNIQUE, contents)')
            self.__execute('CREATE TABLE IF NOT EXISTS favorites (type, name, url, year)')
            self.__execute('CREATE TABLE IF NOT EXISTS subscriptions (url, title, img, year, imdbnum, day)')
            self.__execute('CREATE TABLE IF NOT EXISTS url_cache (url UNIQUE, response, timestamp)')
            self.__execute('CREATE TABLE IF NOT EXISTS db_info (setting TEXT, value TEXT)')
            self.__execute('CREATE TABLE IF NOT EXISTS new_bkmark (url TEXT PRIMARY KEY NOT NULL, resumepoint DOUBLE NOT NULL)')
            self.__execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_fav ON favorites (name, url)')
            self.__execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_sub ON subscriptions (url, title, year)')
            self.__execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_url ON url_cache (url)')
            self.__execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_db_info ON db_info (setting)')
            
        
        self.__do_db_fixes()
        sql = 'REPLACE INTO db_info (setting, value) VALUES(?,?)'
        self.__execute(sql, ('version', _1CH.get_version()))

    def repair_meta_images(self):
        from metahandler import metahandlers
        from metahandler import metacontainers
        import xbmcgui
        PREPARE_ZIP = False
        __metaget__ = metahandlers.MetaData(preparezip=PREPARE_ZIP)

        cont = metacontainers.MetaContainer()
        if self.db_type == DB_TYPES.MYSQL:
            db = db_lib.connect(database=self.dbname, user=self.username, password=self.password, host=self.address, buffered=True)
        else:
            db = db_lib.connect(cont.videocache)
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
     
                eta = utils.format_eta(eta)
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
        
    def __execute(self, sql, params=None):
        if params is None:
            params=[]
            
        rows=None
        sql=self.__format(sql)
        cur = self.db.cursor()
        cur.execute(sql, params)
        if sql[:6].upper() == 'SELECT':
            rows=cur.fetchall()
        cur.close()
        self.db.commit()
        return rows

    # generic cleanup method to do whatever fixes might be required in this release
    def __do_db_fixes(self):
        fixes=[]
        if self.db_type==DB_TYPES.MYSQL:
            fixes.append('ALTER TABLE url_cache MODIFY COLUMN response MEDIUMBLOB')
            # add day to sub table
            fixes.append('ALTER TABLE subscriptions ADD day TEXT')
        else:
            # add day to sub table
            fixes.append('ALTER TABLE subscriptions ADD day TEXT')
            #Fix previous index errors on bookmark table
            fixes.append('DROP INDEX IF EXISTS unique_movie_bmk') # get rid of faulty index that might exist
            fixes.append('DROP INDEX IF EXISTS unique_episode_bmk') # get rid of faulty index that might exist
            fixes.append('DROP INDEX IF EXISTS unique_bmk') # drop this index too just in case it was wrong
        
        # try fixes, ignore errors
        for fix in fixes:
            try: self.__execute(fix)
            except: pass
    
    def __create_sqlite_db(self):
        if not xbmcvfs.exists(os.path.dirname(self.db_path)): 
            try: xbmcvfs.mkdirs(os.path.dirname(self.db_path))
            except: os.mkdir(os.path.dirname(self.db_path))
    
    def __connect_to_db(self):
        if not self.db:
            if self.db_type == DB_TYPES.MYSQL:
                self.db = db_lib.connect(database=self.dbname, user=self.username, password=self.password, host=self.address, buffered=True)
            else:
                self.db = db_lib.connect(self.db_path)
                self.db.text_factory = str

    # apply formatting changes to make sql work with a particular db driver
    def __format(self, sql):
        if self.db_type ==DB_TYPES.MYSQL:
            sql = sql.replace('?', '%s')
            
        if self.db_type == DB_TYPES.SQLITE:
            if sql[:7]=='REPLACE':
                sql = 'INSERT OR ' + sql

        return sql
