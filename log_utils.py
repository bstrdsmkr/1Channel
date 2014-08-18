import xbmc
from addon.common.addon import Addon

ADDON = Addon('plugin.video.1channel')

def log(msg, level=xbmc.LOGNOTICE):
    # override message level to force logging when addon logging turned on
    if ADDON.get_setting('addon_debug')=='true' and level==xbmc.LOGDEBUG:
        level=xbmc.LOGNOTICE
        
    try: ADDON.log(msg, level)
    except: 
        try: xbmc.log('Logging Failure', level)
        except: pass # just give up

