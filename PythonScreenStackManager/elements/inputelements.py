"""
Elements that provide support for input.
Since the OSK has not been tested for inkBoard, these elements are not guaranteed to work.
"""
import json

from .baseelements import logger, Layout, Button, Popup
from .constants import DEFAULT_FONT, DEFAULT_FONT_SIZE

from .. import tools, \
        constants as const

class OSK(Layout):
    """
    A PSSM Layout element which builds an on-screen keyboard
    Args:
        keymapPath (str): a path to a PSSMOSK keymap (like the one included)
        onKeyPress (function): A callback function. Will be given keyType and
            keyChar as argument
    """

    @property
    def _emulator_icon(cls): return "mdi:keyboard"

    def __init__(self, keymapPath=const.DEFAULT_KEYMAP_PATH, onKeyPress=None,
                 area=None, **kwargs):
        if not keymapPath:
            keymapPath = const.DEFAULT_KEYMAP_PATH
        self.keymapPaths = keymapPath
        self.keymap = {'standard': None, 'caps': None, 'alt': None}
        self.keymap_layouts = {'standard': None, 'caps': None, 'alt': None}
        self.keymap_imgs = {'standard': None, 'caps': None, 'alt': None}
        with open(self.keymapPaths['standard']) as json_file:
            self.keymap['standard'] = json.load(json_file)
        with open(self.keymapPaths['caps']) as json_file:
            self.keymap['caps'] = json.load(json_file)
        with open(self.keymapPaths['alt']) as json_file:
            self.keymap['alt'] = json.load(json_file)
        self.lang = self.keymap['standard']["lang"]
        self.onKeyPress = onKeyPress
        self.view = 'standard'
        self.keymap_layouts['standard'] = self.build_layout(
                                            self.keymap['standard'])
        self.keymap_layouts['caps'] = self.build_layout(self.keymap['caps'])
        self.keymap_layouts['alt'] = self.build_layout(self.keymap['alt'])
        # Initialize layout with standard view
        self.layout = self.keymap_layouts['standard']
        super().__init__(self.layout, **kwargs)
        self._area = area

    def generator(self, area=None, forceRegenerate=False,
                skipNonLayoutGen=False):
        """
        This generator is a bit special : we don't want it to regenerate
        everything everytime we change view. So we will generate all the views
        at once the first time. Then, unless asked to, we will only return the
        appropriate image.
        """
        isStDefined = self.keymap_imgs['standard']
        isCaDefined = self.keymap_imgs['caps']
        isAlDefined = self.keymap_imgs['alt']
        areAllDefined = isStDefined and isCaDefined and isAlDefined
        if forceRegenerate or (not areAllDefined):
            logger.info("[PSSM OSK] Regenration started")
            # Let's create all the Images
            # Standard view is created last, because it is the one which is to
            # be displayed
            def generateLayout(name):
                self.layout = self.keymap_layouts[name]
                self.keymap_imgs[name] = super(OSK, self).generator(area=area)
            generateLayout("caps")
            generateLayout("alt")
            generateLayout("standard")
        self._imgData = self.keymap_imgs[self.view]
        return self.keymap_imgs[self.view]

    def build_layout(self, keymap):
        oskLayout = []
        spacing = keymap["spacing"]
        for row in keymap["rows"]:
            buttonRow = ["?", (None, spacing)]
            for key in row:
                label = self.getKeyLabel(key)
                color_condition = key["keyType"] != const.KTstandardChar
                background_color = "gray12" if color_condition else "white"
                outline_color = "white" if key["isPadding"] else "black"
                willChangeLayout = key["keyType"] in [
                    const.KTcapsLock, const.KTalt, const.KTcarriageReturn
                ]
                show_feedback = False if willChangeLayout else True
                buttonElt = Button(
                    text=label,
                    font_size="H*0.02",
                    background_color=background_color,
                    outline_color=outline_color,
                    tap_action=self.handleKeyPress,
                    user_data=key,
                    multiline=False,
                    show_feedback=show_feedback
                )
                key_width = key["keyWidth"]
                buttonRow.append((buttonElt, key_width))
                buttonRow.append((None, spacing))
            oskLayout.append(buttonRow)
            oskLayout.append([spacing])
        return oskLayout

    def handleKeyPress(self, elt, coords):
        keyType = elt.user_data["keyType"]
        keyChar = elt.user_data["char"]
        if keyType == const.KTcapsLock:
            # In this particular case, we can assume the keyboard will always
            # be on top.
            # Therefore, no need to print everything
            self.view = 'caps' if self.view != 'caps' else 'standard'
            self.layout = self.keymap_layouts[self.view]
            self._imgData = self.keymap_imgs[self.view]
            self.parentPSSMScreen.simple_print_element(self)
        elif keyType == const.KTalt:
            # In this particular case, we can assume the keyboard will always
            # be on top
            # Therefore, no need to print everything
            self.view = 'alt' if self.view != 'alt' else 'standard'
            self.layout = self.keymap_layouts[self.view]
            self._imgData = self.keymap_imgs[self.view]
            self.parentPSSMScreen.simple_print_element(self)
        if self.onKeyPress:
            self.onKeyPress(keyType, keyChar)

    def getKeyLabel(self, key):
        kt = key["keyType"]
        if kt == const.KTstandardChar:
            return key["char"]
        elif kt == const.KTalt:
            return "ALT"
        elif kt == const.KTbackspace:
            return "BACK"
        elif kt == const.KTcapsLock:
            return "CAPS"
        elif kt == const.KTcarriageReturn:
            return "RET"
        elif kt == const.KTcontrol:
            return "CTRL"
        elif kt == const.KTdelete:
            return "DEL"
        return ""


class Input(Button):
    """
    NOT UP TO DATE
    Basically a button, except when you click on it, it displays the keyboard.
    It handles typing things for you. so when you click on this element, the
    keyboard shows up, and you can start typing.
    The main thing it does is that it is able to detect between which
    characters the user typed to be able to insert a character between two
    others (and that was no easy task)
    It has a method to retrieve what was typed :
    Input.getInput()
    Args:
        isMultiline (bool): Allow carriage return
        onReturn (function): Function to be executed on carriage return
    """
    def __init__(self, isMultiline=True, onReturn=tools.returnFalse, **kwargs):
        super().__init__(**kwargs)
        self.hideCursorWhenLast = True
        self.isMultiline = isMultiline
        self.onReturn = onReturn
        self.allowSetCursorPos = False
        self.isOnTop = True  # Let's assume an input elt is always on top
        # for param in kwargs:
        #     setattr(self, param, kwargs[param])
        if 'font' in kwargs:
            self.font = tools.parse_known_fonts(kwargs["font"])
        self.cursorPosition = len(self.text)
        self.typedText = self.text[:]
        self.text = self.typedText

    def getInput(self):
        """
        Returns the text currently written on the Input box.
        """
        return self.typedText

    def pssmOnClickInside(self, coords):
        if not self.parentPSSMScreen.osk:
            logger.warning(
                "[PSSM] Keyboard not initialized, Input element cannot be " +
                "properly handled"
            )
            return None
        # Set the callback function to our own
        self.parentPSSMScreen.osk.onKeyPress = self.onKeyPress
        if not self.parentPSSMScreen.isOSKShown:
            # Let's print the on screen keyboard as it is not already here
            self.parentPSSMScreen.OSKShow()
        elif self.allowSetCursorPos:
            cx, cy = coords
            [(sx, sy), (w, h)] = self.area
            loaded_font = self.loaded_font
            myText = self.convertedText
            imgDraw = self.imgDraw
            text_w, text_h = imgDraw.textsize(myText, font=loaded_font)
            x = tools.convert_XArgs_to_PX(self.text_x_position, w, text_w,
                                    myElt=self)
            y = tools.convert_YArgs_to_PX(self.text_y_position, h, text_h,
                                    myElt=self)
            # Then let's linear search
            wasFound = False
            olines = myText[:].split("\n")
            if len(olines) > 0:
                lines = [olines[0]]
            else:
                lines = []
            for i in range(len(olines)):
                lines.append("\n")
            linesBefore = ""
            for i in range(len(lines)):
                tw1, th1 = imgDraw.textsize(linesBefore, font=loaded_font)
                linesBefore += lines[i]
                tw2, th2 = imgDraw.textsize(linesBefore, font=loaded_font)
                b_correct_y = cy > sy + x + th1 and cy <= sy + y + th2
                if b_correct_y:
                    for j in range(len(linesBefore)):
                        tw1, th1 = imgDraw.textsize(linesBefore[:j],
                                                    font=loaded_font)
                        tw2, th2 = imgDraw.textsize(linesBefore[:j+1],
                                                    font=loaded_font)
                        b_correct_x = cx > sx + x + tw1 and cx <= sx + x + tw2
                        if b_correct_x:
                            pos = j
                            for line in lines[:i]:
                                pos += len(line)
                            self.setCursorPosition(pos+1)
                            wasFound = True
                    if not wasFound:    # Let's put it at the end of the row
                        pos = 0
                        for line in lines[:i+1]:
                            pos += len(line)
                        self.setCursorPosition(pos)
                        wasFound = True
            if not wasFound:
                self.setCursorPosition(None)
            pass

    def onKeyPress(self, keyType, keyChar):
        """
        Handles each key press.
        By default, it will re-display the input element on each keypress ON
        TOP OF THE SCREEN (not honoring stack position). This allow for a 30%
        speed increase on my basic test. You can change this behaviour by
        setting `InputElt.isOnTop = False`
        """
        c = self.cursorPosition
        if keyType == const.KTstandardChar:
            self.typedText = tools.insert_string(self.typedText, keyChar, c)
            self.setCursorPosition(self.cursorPosition+1, skipPrint=True)
        elif keyType == const.KTcarriageReturn:
            if self.isMultiline:
                self.typedText = tools.insert_string(self.typedText, "\n", c)
                self.setCursorPosition(self.cursorPosition+1, skipPrint=True)
            else:
                self.onReturn()
        elif keyType == const.KTbackspace:
            self.typedText = self.typedText[:c-1] + self.typedText[c:]
            self.setCursorPosition(self.cursorPosition-1, skipPrint=True)
        if self.hideCursorWhenLast:
            if self.cursorPosition >= len(self.typedText):
                # Don't display the cursor when it is at the last position
                self.text = self.typedText[:]
        else:
            self.text = tools.insert_string(self.typedText, CURSOR_CHAR,
                                self.cursorPosition)
        if self.isOnTop:
            self.update(reprintOnTop=True)
        else:
            self.update()

    def setCursorPosition(self, pos, skipPrint=False):
        """
        _summary_

        Parameters
        ----------
        pos : _type_
            _description_
        skipPrint : bool, optional
            _description_, by default False
        """
        if pos is None:
            pos = len(self.typedText)
        self.cursorPosition = pos
        self.text = tools.insert_string(self.typedText, CURSOR_CHAR, self.cursorPosition)
        if not skipPrint:
            self.update()


class PopupInput(Popup):
    """
    A Popup that allows for input. OSK has not been investigated yet from the original PSSM, so element is not fully implemented.
    """

    @property
    def _emulator_icon(cls): return "mdi:tooltip-text"

    def __init__(self, titleText:str="", mainText:str="", confirmText:str="OK",
                title_font:str=DEFAULT_FONT, title_font_size:str=DEFAULT_FONT_SIZE,
                mainFont:str=DEFAULT_FONT, mainFontSize:str=DEFAULT_FONT_SIZE,
                inputFont:str=DEFAULT_FONT, inputFontSize:str=DEFAULT_FONT_SIZE,
                buttonFont:str=DEFAULT_FONT, buttonFontSize:str=DEFAULT_FONT_SIZE,
                title_font_color:str="black", mainFontColor:str="black",
                inputFontColor:str="black", buttonFontColor:str="black",
                mainTextXPos:str="center", mainTextYPos:str="center",
                isMultiline:bool=False, **kwargs):
        super().__init__(**kwargs)
        self.titleText :str = titleText
        self.mainText = mainText
        self.confirmText = confirmText
        self.isMultiline = isMultiline
        self.title_font = title_font
        self.mainFont = mainFont
        self.inputFont = inputFont
        self.buttonFont = buttonFont
        self.title_font_size = title_font_size
        self.mainFontSize = mainFontSize
        self.inputFontSize = inputFontSize
        self.buttonFontSize = buttonFontSize
        self.title_font_color = title_font_color
        self.mainFontColor = mainFontColor
        self.inputFontColor = inputFontColor
        self.buttonFontColor = buttonFontColor
        self.mainTextXPos = mainTextXPos
        self.mainTextYPos = mainTextYPos
        self.userConfirmed = False
        self.inputBtn = None
        self.okBtn = None
        
        self.build_layout()

    def build_layout(self):
        titleBtn = Button(
            text=self.titleText,
            font=self.title_font,
            font_size=self.title_font_size,
            font_color=self.title_font_color
        )
        mainBtn = Button(
            text=self.mainText,
            font=self.mainFont,
            font_size=self.mainFontSize,
            font_color=self.mainFontColor,
            text_x_position=self.mainTextXPos,
            text_y_position=self.mainTextYPos
        )
        if self.isMultiline:
            onReturn = tools.returnFalse
        else:
            onReturn = self.toggleConfirmation
        inputBtn = Input(
            font=self.inputFont,
            font_size=self.inputFontSize,
            font_color=self.inputFontColor,
            isMultiline=self.isMultiline,
            onReturn=onReturn
        )
        okBtn = Button(
            text=self.confirmText,
            font=self.buttonFont,
            font_size=self.buttonFontSize,
            font_color=self.buttonFontColor,
            tap_action=self.toggleConfirmation
        )
        self.inputBtn = inputBtn
        lM = (None,1)
        layout = [
            ["?*1.5", (titleBtn, "?"), lM],
            ["?*3", (mainBtn, "?"), lM],
            ["?*2", (inputBtn, "?"), lM],
            ["?*1", (okBtn, "?"), lM]
        ]
        self.layout = layout
        return layout

    def toggleConfirmation(self, elt=None, coords=None):
            logger.info("Toggling confirmation")
            self.userConfirmed = True

    def waitForResponse(self):
        while not self.userConfirmed:
            self.parentPSSMScreen.device.wait(0.01)
        self.parentPSSMScreen.OSKHide()
        input = self.inputBtn.getInput()
        self.userConfirmed = False  # Reset the state
        self.parentPSSMScreen.remove_element(self)
        return input
