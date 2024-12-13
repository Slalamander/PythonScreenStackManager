"""
    PythonScreenStackManager can generate image stacks to act as gui's, for example.
    Originally written by Mavireck (https://github.com/Mavireck/Python-Screen-Stack-Manager).
    Rewritten to use asyncio by Slalamander, among other changes
"""
# from __future__ import annotations


__version__ = "0.1.0"
"PythonScreenStackManager version. For now the s is in front to indicate it is the version continued by Slalamander"



import __main__
import logging
from functools import partial, partialmethod
from typing import TYPE_CHECKING

from . import pssm

if TYPE_CHECKING:
    from .pssm_types import *
    from .pssm import screen
    from .devices import PSSMdevice

logging.TRACE = 5
logging.addLevelName(logging.TRACE, "TRACE")
logging.Logger.trace = partialmethod(logging.Logger.log, logging.TRACE)
logging.trace = partial(logging.log, logging.TRACE)

logger = logging.getLogger(name=__name__)
logger.debug(f"{logger.name} has loglevel {logging.getLevelName(logger.getEffectiveLevel())}")

##Setting it to false here explictly to deal with reloads (since globals aren't reset there)
_screen: "screen.PSSMScreen" = None
"""
Main Screen instance. Needs to be initialised by calling get_screen.
"""

def set_screen(device: "PSSMdevice", **screen_init: 'ScreenInit') -> 'screen.PSSMScreen':
    """
    Sets the screen instance. If one has not been instantiated yet, will make one.
    Only one instance is made for each running programme, so the same instance is returned each time.
    If not done yet, this will import the pssm.py file and the elements module, and set the screen isntance.
    It also registers the base menu elements (The DeviceMenu and ScreenMenu) and sets up the default StatusBar icons to go with it.
    """
    ##Some stuff cannot be imported beforehand due to dealing with imports from inkBoard.
    raise Exception("Dont call me")
    global _screen
    if _screen == None or True:
        from .constants import INKBOARD
        from .pssm import screen

        _screen = screen.PSSMScreen(device=device, **screen_init)

        from . import elements
        from . import tools

        elements.StatusBar._statusbar_elements = {}

        # elements.baseelements.ScreenInstance = _screen
        # tools.ScreenInstance = _screen

        elements.DeviceMenu()
        elements.ScreenMenu()

        elements.StatusBar.add_statusbar_element("device", elements.DeviceIcon())
        screen_name = "inkBoard" if INKBOARD else "screen"
        dashboardIcon = elements.Icon("mdi:view-dashboard", tap_action={"action": "element:show-popup", "element_id": "screen-menu"})
        elements.StatusBar.add_statusbar_element(screen_name, dashboardIcon)

    return _screen

def get_screen() -> 'screen.PSSMScreen':
    "Returns the set screen instance. Don't call this before having called `set_screen`"
    global _screen
    if _screen == None:
        raise NameError("The screen has not been defined yet, call `set_screen` first before calling `get_screen`.")
    return _screen

def add_shorthand_icon(icon_name: str, icon): #Move this function somewhere else cause it does too much importing
    from . import constants
    constants.SHORTHAND_ICONS[icon_name] = icon

__pdoc__ = {
    "fonts": False,
    "config": False,

    "devices": True,
    "elements": True,

    "constants": True,
    "example": False,
    "pssm_settings": True,

    "pssm_types": False, ##Types causes an error, maybe because of nesting of TypeVar's? Idk, in the end just copy paste those. The docs for elements don't quite work like I want them too either, these are just quickly made.

    "pssm": True,
    "tools": True

    }