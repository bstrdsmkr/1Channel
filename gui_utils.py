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
import datetime
import xbmcgui
import xbmc
import time
import os.path
from utils import i18n
from pw_scraper import PW_Scraper
from addon.common.addon import Addon
import utils

_1CH = Addon('plugin.video.1channel')
pw_scraper = PW_Scraper(_1CH.get_setting("username"), _1CH.get_setting("passwd"))

def get_adv_search_query(section):
    if section == 'tv':
        header_text = i18n('adv_tv_search')
    else:
        header_text = i18n('adv_movie_search')
    SEARCH_BUTTON = 200
    CANCEL_BUTTON = 201
    HEADER_LABEL = 100
    ACTION_PREVIOUS_MENU = 10
    ACTION_BACK = 92
    CENTER_Y = 6
    CENTER_X = 2
    now = datetime.datetime.now()
    # allowed values have to be list of strings
    allowed_values = {}
    allowed_values['month'] = [''] + [str(month) for month in xrange(1, 13)]
    allowed_values['year'] = [''] + [str(year) for year in xrange(1900, now.year + 1)]
    allowed_values['decade'] = [''] + [str(decade) for decade in xrange(1900, now.year + 1, 10)]
    allowed_values['genre'] = [''] + pw_scraper.get_genres()

    class AdvSearchDialog(xbmcgui.WindowXMLDialog):
        ypos = 85
        gap = 55
        params = [
                ('title', 30, ypos, 30, 450),
                ('tag', 30, ypos + gap, 30, 450),
                ('actor', 30, ypos + gap * 2, 30, 450),
                ('director', 30, ypos + gap * 3, 30, 450),
                ('country', 30, ypos + gap * 4, 30, 450),
                ('genre', 30, ypos + gap * 5, 30, 450),
                ('month', 30, ypos + gap * 6, 30, 140),
                ('year', 185, ypos + gap * 6, 30, 140),
                ('decade', 340, ypos + gap * 6, 30, 140)]
        
        def onInit(self):
            self.query_controls = []
            # add edits for title, tag, actor and director
            for i in xrange(9):
                self.query_controls.append(self.__add_editcontrol(self.params[i][1], self.params[i][2], self.params[i][3], self.params[i][4]))
                if i > 0:
                    self.query_controls[i].controlUp(self.query_controls[i - 1])
                    self.query_controls[i].controlLeft(self.query_controls[i - 1])
                if i < 9:
                    self.query_controls[i - 1].controlDown(self.query_controls[i])
                    self.query_controls[i - 1].controlRight(self.query_controls[i])

            search = self.getControl(SEARCH_BUTTON)
            cancel = self.getControl(CANCEL_BUTTON)
            self.query_controls[0].controlUp(cancel)
            self.query_controls[0].controlLeft(cancel)
            self.query_controls[-1].controlDown(search)
            self.query_controls[-1].controlRight(search)
            search.controlUp(self.query_controls[-1])
            search.controlLeft(self.query_controls[-1])
            cancel.controlDown(self.query_controls[0])
            cancel.controlRight(self.query_controls[0])
            header = self.getControl(HEADER_LABEL)
            header.setLabel(header_text)

        def onAction(self, action):
            # print 'Action: %s' %(action.getId())
            if action == ACTION_PREVIOUS_MENU or action == ACTION_BACK:
                self.close()

        def onControl(self, control):
            # print 'onControl: %s' % (control)
            pass

        def onFocus(self, control):
            # print 'onFocus: %s' % (control)
            pass

        def onClick(self, control):
            # print 'onClick: %s' %(control)
            if control == SEARCH_BUTTON:
                if not self.__validateFields():
                    return

                self.search = True
            if control == CANCEL_BUTTON:
                self.search = False

            if control == SEARCH_BUTTON or control == CANCEL_BUTTON:
                self.close()

        def get_result(self):
            return self.search

        def get_query(self):
            texts = []
            for control in self.query_controls:
                if isinstance(control, xbmcgui.ControlEdit):
                    texts.append(control.getText())
                elif isinstance(control, xbmcgui.ControlList):
                    texts.append(control.getSelectedItem().getLabel())

            params = [param[0] for param in self.params]
            query = dict(zip(params, texts))
            return query

        # returns True if everything validates, false otherwise
        def __validateFields(self):
            error = False
            all_values = ''.join([control.getText().strip() for control in self.query_controls])
            if all_values == '':
                error_string = i18n('one_criteria')
                error = True
            else:
                # validate fields with allowed values
                valid_fields = ['genre', 'month', 'year', 'decade']
                field_names = [param[0] for param in self.params]
                for field in valid_fields:
                    field_value = self.query_controls[field_names.index(field)].getText()
                    if field_value != '':
                        if field_value not in allowed_values[field]:
                            error_string = '%s %s %s' % (field.capitalize(), i18n('must_be_one_of'), str(allowed_values[field][1:]).replace("'", ""))
                            # override error string on year
                            if field == 'year':
                                error_string = i18n('year_range_error') % (allowed_values[field][1], allowed_values[field][-1])
                            error = True
                            break

            if error:
                _1CH.show_ok_dialog([error_string], title='PrimeWire')
            return not error

        # have to add edit controls programatically because getControl() (hard) crashes XBMC on them
        def __add_editcontrol(self, x, y, height, width):
            temp = xbmcgui.ControlEdit(0, 0, 0, 0, '', font='font12', textColor='0xFFFFFFFF', focusTexture='button-focus2.png', noFocusTexture='button-nofocus.png', _alignment=CENTER_Y | CENTER_X)
            temp.setPosition(x, y)
            temp.setHeight(height)
            temp.setWidth(width)
            self.addControl(temp)
            return temp

    dialog = AdvSearchDialog('AdvSearchDialog.xml', _1CH.get_path())
    dialog.doModal()
    if dialog.get_result():
        query = dialog.get_query()
        del dialog
        utils.log('Returning query of: %s' % (query), xbmc.LOGDEBUG)
        return query
    else:
        del dialog
        raise

def days_select(days):
    OK_BUTTON = 200
    CANCEL_BUTTON = 201
    SEL_ALL_BUTTON = 99
    MONDAY_BUTTON = 77770
    ACTION_PREVIOUS_MENU = 10
    ACTION_BACK = 92
    
    class EditDaysDialog(xbmcgui.WindowXMLDialog):
        ystart = 0
        ygap = 35
        
        def onInit(self):
            fdow = int(_1CH.get_setting('first-dow'))
            adj_day_range = range(fdow, 7) + range(0, fdow)
            ypos = self.ystart
            last_control = self.getControl(CANCEL_BUTTON)
            for i in adj_day_range:
                control = self.getControl(MONDAY_BUTTON + i)

                # move the day control to it's position based on fdow
                control.setPosition(0, ypos)
                if str(i) in days:
                    control.setSelected(True)

                # set up, down, left, right for each control
                control.controlUp(last_control)
                control.controlLeft(last_control)
                last_control.controlDown(control)
                last_control.controlRight(control)

                ypos = ypos + self.ygap
                last_control = control

            # select_all goes up to last control and last control goes down to select_all
            select_all = self.getControl(SEL_ALL_BUTTON)
            select_all.controlUp(control)
            select_all.controlLeft(control)
            control.controlDown(select_all)
            control.controlRight(select_all)

            if days == '0123456':
                self.getControl(SEL_ALL_BUTTON).setSelected(True)

        def onAction(self, action):
            # print 'Action: %s' %(action.getId())
            if action == ACTION_PREVIOUS_MENU or action == ACTION_BACK:
                self.close()

        def onControl(self, control):
            # print 'onControl: %s' % (control)
            pass

        def onFocus(self, control):
            # print 'onFocus: %s' % (control)
            pass

        def onClick(self, control):
            # print 'onClick: %s' %(control)
            if control == SEL_ALL_BUTTON:
                all_status = self.getControl(control).isSelected()
                for control_id in xrange(MONDAY_BUTTON, MONDAY_BUTTON + 7):
                    self.getControl(control_id).setSelected(all_status)
                return

            if control == OK_BUTTON:
                self.OK = True
            if control == CANCEL_BUTTON:
                self.OK = False

            if control == OK_BUTTON or control == CANCEL_BUTTON:
                self.close()

        def clicked_OK(self):
            return self.OK

        def get_days(self):
            days = ''
            for i in xrange(0, 7):
                if self.getControl(MONDAY_BUTTON + i).isSelected():
                    days += str(i)
            return days

    dialog = EditDaysDialog('EditDaysDialog.xml', _1CH.get_path())
    dialog.doModal()
    if dialog.clicked_OK():
        days = dialog.get_days()
        utils.log('Returning days: %s' % (days), xbmc.LOGDEBUG)
        del dialog
        return days
    else:
        del dialog
        raise

# based on H99's splash code
def do_My_TextSplash(msg='', img='http://www.tvaddons.ag/wp-content/uploads/2014/08/tvaddons_logo.png', HowLong=15, resize=False, L=0, T=0, W=1280, H=720, TxtColor='0xFFFFFFFF', Font='font14', BorderWidth=10):  # HowLong in seconds.
    class MyWindowCountDownWithText(xbmcgui.WindowDialog):
        scr = {}
        
        def __init__(self, msg='', bgArt='', L=0, T=0, W=1280, H=720, TxtColor='0xFFFFFFFF', Font='font14', BorderWidth=10):
            self.background = bgArt; self.scr['L'] = L; self.scr['T'] = T; self.scr['W'] = W; self.scr['H'] = H
            image_path = os.path.join(_1CH.get_path(), 'resources', 'media', '1CHDialogBack.png')
            self.border = xbmcgui.ControlImage(self.scr['L'], self.scr['T'], self.scr['W'], self.scr['H'], image_path)
            self.addControl(self.border)
            self.BG = xbmcgui.ControlImage(self.scr['L'] + BorderWidth, self.scr['T'] + BorderWidth, self.scr['W'] - (BorderWidth * 2), self.scr['H'] - (BorderWidth * 2), self.background, aspectRatio=0, colorDiffuse='0x2FFFFFFF')
            self.addControl(self.BG)
            self.TxtMessage = xbmcgui.ControlTextBox(self.scr['L'] + BorderWidth, self.scr['T'] + BorderWidth, self.scr['W'] - (BorderWidth * 2), self.scr['H'] - (BorderWidth * 2), font=Font, textColor=TxtColor)
            self.addControl(self.TxtMessage)
            self.TxtMessage.setText(msg)
            counter_width = len(continue_msg) * 11
            self.counter = xbmcgui.ControlTextBox(L + (W - counter_width) / 2, T + H - 30 - BorderWidth, counter_width, 30, font=Font, textColor=TxtColor)
            self.addControl(self.counter)
            
        def see(self):
            self.show()
        
        def updateBG(self, bgArt=''):
            self.background = bgArt
            self.setImage(self.background)

        def updateY(self, x, y):
            self.BG.setPosition(x, y)
            self.scr['L'] = x
            self.scr['T'] = y

        def updateSize(self, w, h):
            self.BG.setWidth(w)
            self.BG.setHeight(h)
            self.scr['W'] = w
            self.scr['H'] = h
            
        def updateW(self, w):
            self.BG.setWidth(w)
            self.scr['W'] = w
            
        def updateH(self, h):
            self.BG.setHeight(h)
            self.scr['H'] = h
        # def onInit(self):
        # def onClick(self,control):
        # def onControl(self,control):
        # def onFocus(self,control):
        # def onAction(self,action):

    if resize == False: maxW = 1280; maxH = 720; W = maxW / 2; H = maxH / 2; L = maxW / 4; T = maxH / 4;
    continue_msg = 'Continuing in %d seconds...'
    TempWindow2 = MyWindowCountDownWithText(msg=msg, bgArt=img, L=L, T=T, W=W, H=H, TxtColor=TxtColor, Font=Font, BorderWidth=BorderWidth)
    StartTime = time.time()
    while (time.time() - StartTime) <= HowLong:
        wait = HowLong - (time.time() - StartTime)
        TempWindow2.counter.setText(continue_msg % (wait))
        TempWindow2.show()
        xbmc.sleep(500)
    try: del self.TempWindow2;
    except: pass
