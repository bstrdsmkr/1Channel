import time
import xbmc
import xbmcaddon

ADDON = xbmcaddon.Addon(id='plugin.video.1channel')

def format_eta(seconds):
    minutes,seconds = divmod(seconds, 60)
    if minutes > 60:
        hours,minutes = divmod(minutes, 60)
        return "%02dh:%02dm:%02ds " % (hours, minutes, seconds)
    elif seconds > 60:
        return "%02dm:%02ds " % (minutes, seconds)
    else: return "%ss" % seconds

class AutoUpdater:             
    def runProgram(self):
        self.last_run = 0
        hours_list = [2, 5, 10, 15, 24]
        selection = int(ADDON.getSetting('subscription-interval'))
        hours = hours_list[selection]
        seconds = hours * 3600
        while not xbmc.abortRequested:
            if ADDON.getSetting('auto-update-subscriptions') =='true':
                now = time.time()
                if now > (self.last_run + seconds):
                    if xbmc.Player().isPlaying() == False:
                        if xbmc.getCondVisibility('Library.IsScanningVideo') == False:      
                            xbmc.log('1Channel: Service: Updating subscriptions')
                            time.sleep(1)
                            xbmc.executebuiltin('RunPlugin(plugin://plugin.video.1channel/?mode=UpdateSubscriptions)')
                            time.sleep(1)
                            self.last_run = now
                        else: xbmc.log('1Channel: Service: Library is updating. Skipping subscription update')
                    else: xbmc.log('1Channel: Service: Player is running, waiting until finished')
            else:
                xbmc.log('1Channel: Service: Auto-update disabled')
                break
            xbmc.sleep(1000)
        xbmc.log('1Channel: Subscription service ending...')

        
xbmc.log('1Channel: Subscription service starting...')
AutoUpdater().runProgram()