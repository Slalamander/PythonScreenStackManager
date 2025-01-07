"""
Class with the most basic functioning version of a PSSMDevice (excluding the option to set interaction).
I.e. does not provide functionality for power etc. But has some basic functions to emulate a backlight as well as the ability to get network info (on windows for now)
Get it by instantiating `windowed.Device()`, runs in a TKinter window.
"""

import os
import asyncio
import logging
import platform
import socket
import subprocess
import tkinter as tk

from typing import Callable, Union
from datetime import datetime as dt
from math import ceil
from contextlib import suppress

from PIL import Image, ImageTk

from . import PSSMdevice, DeviceFeatures, NetworkDict, Network as BaseNetwork, Backlight as BaseBacklight, FEATURES
from .const import CANVASNAME
from ..tools import DummyTask, TouchEvent
from .. import tools, constants as const
from ..pssm_types import ColorType

logger = logging.getLogger(__name__)

t = tk

if tk._default_root:
    root = tk._default_root
else:
    root = tk.Tk()

if CANVASNAME not in root.children:
    canvas = tk.Canvas(root, background="gray",highlightthickness=0, name=CANVASNAME)
    canvas.pack(fill="both", expand=1)

def get_windows_network() -> NetworkDict:
    "Gets info on the currently connected network on windows machines"
    network_dict : NetworkDict = {}
    win_network = {}
    network_if = subprocess.check_output(['netsh','wlan','show','interfaces']) 
    network = network_if.decode('ascii') 
    network = network.replace("\n","") 
    network = network.strip()
    network = network.split("\r")
    for line in network:
        line = line.strip()
        if line and line[-1] != ":" and ":" in line:
            key, val = line.split(":",1)
            win_network[key.strip()] = val.strip()
    network_dict["MAC"] = win_network["Physical address"]
    if win_network["State"] == "connected":
        network_dict["connected"] = True
        network_dict["wifiOn"] = True
        network_dict["signal"] = win_network["Signal"]
        network_dict["SSID"] = win_network["SSID"] 
    else:
        network_dict["connected"] = False
        network_dict["signal"] = "0%"
        network_dict["SSID"] = None
        if "Radio status" in win_network:
            if "Software Off" in win_network["Radio status"]:
                network_dict["wifiOn"] = False

        if "wifiOn" not in network_dict: network_dict["wifiOn"] = True
    network_dict["internet"] = network_dict["connected"]
    
    return network_dict

def get_linux_network() -> NetworkDict:
    "Gets info on the currently connected network on Linux machines. When it is implemented that is."
    logger.warning("Linux network has not been implemented yet")

    network = (os.popen("iwgetid -r").read())

    return NetworkDict(connected=False, MAC=None,SSID=None)

##Except for the backlight, will probably remove the network feature too.
f = {"interactive": True, "backlight": True, "network": True}

class Device(PSSMdevice):
    """
    An almost minimal working example of a device that can interface and interact with a PSSM screen.
    Can be extended to check the network connection, and emulate a backlight. The interactive part can also be disabled.
    Some additional flexibility is implemented for quality of life when having a windowed environment.

    Parameters
    ----------
    name : str, optional
        The name of the device, also used to name the window, by default None
    frame_rate : int, optional
        The amount of times the window is updated per second, by default 20.
        Since this is a dashboarding interface, the value does not need to be very high to still have a decent running experience.
        The main performance bottleneck probably lies in the generating of elements and the fact that it is run in Python.
    screenWidth : int, optional
        The initial width of the window, by default 1280
    screenHeight : int, optional
        The initial height of the window, by default 720
    fullscreen : bool, optional
        Whether to start the window in fullscreen, by default False
        screenWidth and screenHeight are set to the correct value if this True.
        The device provides a shorthand function for toggling fullscreen, and binds the F11 key to toggle it as well.
    resizeable : bool, optional
        Allows the window to be resized by dragging the edges, by default False
    cursor : str, optional
        The type of cursor to use when the mouse is on the dashboard. By default "target"
        see https://anzeljg.github.io/rin2/book2/2405/docs/tkinter/cursors.html for available types.
    screenMode : str, optional
        The image mode to print the final screen image in, by default "RGB"
    imgMode : str, optional
        The image mode to construct element images in, by default "RGBA"
    defaultColor : ColorType, optional
        The default color (i.e. assumed background color) of the device, by default "white"
    interactive : bool, optional
        Whether the dashboard can be interacted with, by default True
    network_features : bool, optional
        Whether to use network_features, by default False
        This indicates the device can access the internet and periodically pols the network properties. Setting it to False does not actually block off internet access to the programme.
    backlight_features : bool, optional
        Whether to simulate screen brightness, i.e. print a transparent black rectangle over the dashboard, by default False
    backlight_alpha : int, optional
        The maximum allowed alpha value of the backlight rectangle, so the transparancy when the backlight is considered off. by default 175
        0 is the minimum value, which is the same as not using the backlight feature. 255 is the maximum value, which means the rectangle is not transparant at all when it is off.
    features : DeviceFeatures, optional
        If not None, the interactive, network_features and backlight_features parameters will be ignored, and this value will be passed as the device's features.
    """   
    def __init__(self, name : str = None,
                frame_rate : int = 20, screenWidth = 1280, screenHeight = 720, fullscreen : bool = False, resizeable : bool = False, cursor : str = "target",
                screenMode : str = "RGB", imgMode : str = "RGBA", defaultColor : ColorType  = "white",
                interactive : bool = True, network_features : bool = False, backlight_features : bool = False, backlight_alpha : int = 175,
                features: DeviceFeatures = None):

        if features == None:
            features = DeviceFeatures(**{FEATURES.FEATURE_INTERACTIVE: interactive, FEATURES.FEATURE_PRESS_RELEASE: interactive,
                                        FEATURES.FEATURE_BACKLIGHT: backlight_features, FEATURES.FEATURE_NETWORK: network_features})

        super().__init__(features, 
                        screenWidth, screenHeight, 0, 0,
                        screenMode, imgMode, defaultColor, name)
        
        self._windowWidth = screenWidth
        self._windowHeight = screenHeight
        self.frame_rate = frame_rate

        if fullscreen:
            root.wm_attributes("-fullscreen", True)
        else:
            root["width"] = screenWidth
            root["height"] = screenHeight

        self._resizeable = bool(resizeable)
        if not self.resizeable:
            root.resizable(False,False)

        root.bind("<F11>", lambda event: root.attributes("-fullscreen",
                                            not root.attributes("-fullscreen")))
        root.bind("<Escape>", lambda event: root.attributes("-fullscreen", False))

        self.window = root

        if name == None:
            self.__windowName = f"Python Screen Stack Manager"
        else:
            self.__windowName = f"pssm - {self.name}"

        self.window.title(self.__windowName)
        
        self.window.bind("<Configure>", self._window_configure)
        self.window.protocol("WM_DELETE_WINDOW", self._window_closed)

        self.__canvas = canvas
        canvas.configure(cursor=cursor, height=screenHeight, width=screenWidth)
        
        if self.has_feature(FEATURES.FEATURE_INTERACTIVE):
            self.canvas.bind("<Button>", self.canvas_event)

        self._screenImage = Image.new(screenMode,(self.screenWidth,self.screenHeight),None)
        
        self.last_printed_PIL = self._screenImage.copy()
        self._canvasImageTk = ImageTk.PhotoImage(self.last_printed_PIL)
        self.canvasImage = self.canvas.create_image(
                0,0, anchor=tk.NW, image=self._canvasImageTk) 

        self._updateWindowTask = DummyTask()
        self._resizeTask = DummyTask()

        if not hasattr(self, "_backlight") and self.has_feature(FEATURES.FEATURE_BACKLIGHT):
            self._backlight = Backlight(self, backlight_alpha)
        
        if not hasattr(self, "_network") and self.has_feature(FEATURES.FEATURE_NETWORK):
            self._network = Network(self)

    #region
    @property
    def windowName(self) -> str:
        "The name of the window that the emulator is showing in"
        return self.window.wm_title()
    
    @property
    def last_printed_PIL(self) -> Image.Image:
        "Image that was last printed on the screen, with effects applied."
        return self.__last_printed_PIL
    
    @last_printed_PIL.setter
    def last_printed_PIL(self, value : Image.Image):
        if not isinstance(value,Image.Image):
            logger.error(f"last_printed_PIL must be a pillow image instance. {value} is not")
            raise ValueError
        if value.size != (self.screenWidth,self.screenHeight):
            msg = "Image size does not match screensize"
            logger.warning(msg)

        self.__last_printed_PIL = value

    @property
    def screenImage(self) -> Image.Image:
        "The actual image pictured on the screen, as gotten from PSSM. (I.e. the stack)"
        return self._screenImage
    
    @property
    def canvas(self) -> tk.Canvas:
        "The tkinter canvas widget that displays the PSSM screen image."
        return self.__canvas
    
    @property
    def screenWidth(self) -> int:
        "Width of the screen"
        return self._windowWidth
    
    @property
    def viewWidth(self) -> int:
        return self._windowWidth

    @property
    def screenHeight(self) -> int:
        "Height of the screen"
        return self._windowHeight
    
    @property
    def viewHeight(self) -> int:
        "Height of the screen"
        return self._windowHeight
    
    @property
    def resizeable(self) -> bool:
        "Whether the window is resizable by dragging the edges. Calling resize is always allowed."
        return self._resizeable
    
    @resizeable.setter
    def resizeable(self, value):
        v = bool(value)
        self._resizeable = v
        self._call_in_main_thread(
                self.window.resizable, v, v
            )
    #endregion
    
    async def async_pol_features(self):

        if self.has_feature(FEATURES.FEATURE_NETWORK):
            await self.network.async_update_network_properties()

        return

    def _set_screen(self):
        
        self.Screen.add_shorthand_function("toggle-fullscreen", tools.wrap_to_tap_action(self.set_fullscreen))
        self.Screen.add_shorthand_function("make-screenshot", tools.wrap_to_tap_action(self.make_screenshot))

    def _call_in_main_thread(self, func : Callable, *args, **kwargs):
        """
        Helper function that allows calls function `func` with arguments `args` and keyword arguments `kwargs` in the main loop.
        Needed since tkinter doesn't like having window settings changed in different threads.
        Does not work with Coroutines.
        """

        if asyncio._get_running_loop() != self.Screen.mainLoop:
            asyncio.run_coroutine_threadsafe(self.__call_in_main_thread(
            func, *args, **kwargs
                ), self.Screen.mainLoop)
        else:
            func(*args, **kwargs)

    async def __call_in_main_thread(self, func : Callable, *args, **kwargs):
        ##Shorthand function such that a task can be created in the mainloop to execute the function
        ##Users should not interact with this, as interacting with the window is not recommended.
        ##inkBoard designer uses tkthread for this.
        func(*args, **kwargs)

    def print_pil(self, img : Image.Image,x:int,y:int,isInverted=False):
        """
        Prints a pillow image onto the screen at the provided coordinates. Ensure the mode of the pillow image matches that of the screen.

        Parameters
        ----------
        img : Image.Image
            the image object to be printed
        x : int
            x coordinates on the screen where the top left corner of the image will be placed.
        y : int
            y coordinates on the screen where the top left corner of the image will be placed.
        isInverted : bool, optional
            inverts the image before printing, by default False (mainly a leftover for Ereader compatibility, but can be used aestethically when having a greyscale screenmode. Not that you will be stopped from using it in a colored screenMode.)
        """        


        if isInverted:
            img = tools.invert_Image(img)

        if img.mode == "RGBA" and self.screenMode == "RGBA":
            self.screenImage.alpha_composite(img, (x,y))
        elif "A" in img.mode:
            self.screenImage.paste(img,(x,y), mask=img)
        else:
            self.screenImage.paste(img,(x,y))

        ##Since no inversion mask etc. May not need to have screenimage and last_printed_pil
        self.last_printed_PIL.paste(self.screenImage)
        if self.parentPSSMScreen.printing:
            asyncio.run_coroutine_threadsafe(
                self._update_canvas(self.last_printed_PIL),
                loop=self.parentPSSMScreen.mainLoop
            )

    async def _update_canvas(self, img : Image.Image):
        """
        Updates the inkBoard Canvas in the Tkinter view when a new print is performed. 
        Should not block the event loop listening for button events etc.

        Parameters
        ----------
        img : Image.Image
            PIL Image object to convert to a TK image and print onto the canvas.
        """
        if not self.window:
            return
        
        imgTK =  ImageTk.PhotoImage(img)
        self._canvasImageTk = imgTK ##Need to save these since otherwise Tk images dissapear or don't show
        self.canvas.itemconfig(self.canvasImage, image = imgTK)
        self.canvas.update()

    async def __update_window(self):
        "Keeps the window updated. While loop is perpetually running, but could not use tk.mainloop() since that would block the event loop in Inkboard"
        self.window.update()
        while True:
            try:
                self.window.update()
                await asyncio.sleep(1/self.frame_rate)
            except asyncio.CancelledError:
                return

    async def event_bindings(self, eventQueue : asyncio.Queue = None, grabInput=False):
        """
        This function is called when the screens print loop starts. It passes an eventQueue that is used to register interaction with elements.
        When a click or touch event is recorded.
        For Emulators, it also adds the tkinter window updater to the main event loop, so be mindful that functions that interact with the tkinter window MUST be async, or somehow called from an async function in the tkinter event loop.
        PSSM puts non async functions in a seperate thread to allow running them async, but this means they are in a different thread from the Tkinter instance, so cannot interact with it then.
        """
        
        logger.info("PSSM TKinter - Click handler starting")
        if self.has_feature(FEATURES.FEATURE_INTERACTIVE):
            self._eventQueue = eventQueue
            self.canvas.bind("<Button-1>", self.canvas_event)
            self.canvas.bind("<ButtonRelease-1>", self.canvas_event)

        if self.has_feature(FEATURES.FEATURE_BACKLIGHT):
            self.backlight : "Backlight"
            self.backlight.set_settings(self.canvas)

        self._updateWindowTask = asyncio.create_task(self.__update_window())

    def canvas_event(self,event : tk.Event):
        "Gets events from tkinter and passes them to PSSM."
        logger.verbose(f"Got event {event} from tkinter, passing to PSSM")
        if event.type == tk.EventType.ButtonPress:
            touch_type = const.TOUCH_PRESS
        elif event.type == tk.EventType.ButtonRelease:
            touch_type = const.TOUCH_RELEASE
        
        touch_event = TouchEvent(event.x, event.y, touch_type)
        self.eventQueue.put_nowait(touch_event)   
        return
    
    def close_interaction_handler(self):
        "Stops the interaction handler"
        self.canvas.unbind("<Button>", self.canvas_event)

    def set_window_size(self, width : int = None, height : int = None):
        """
        Sets the size of the window. Automatically takes of running in the correct thread.
        If width or height are none, that respective dimension is not changed.
        
        Parameters
        ----------
        width : int, optional
            The new window width in pixels, by default None
        height : int, optional
            The new window height in pixels, by default None
        """
        
        if width == height == None:
            return

        if asyncio._get_running_loop() != self.Screen.mainLoop:
            self.Screen.mainLoop.create_task(self._call_in_main_thread(
            self.set_window_size, width, height
                    ))
        else:
            if height != None: self.window["height"] = height
            if width != None: self.window["width"] = width

    def set_fullscreen(self, state : bool = None):
        """
        Sets the window to fullscreen, or unsets it. If state is `None`, it is toggled.
        Keyboard key F11 is bound to toggle this as well, and The Escape key will always unset it. (Provided the window is in focus for both)

        Parameters
        ----------
        state : bool, optional
            The state to set the fullscreen parameter to, by default None
        """        

        if asyncio._get_running_loop() != self.Screen.mainLoop:
            self._call_in_main_thread(self.set_fullscreen, state)
            return
        
        if state == None:
            state = not self.window.attributes("-fullscreen")
        
        self.window.wm_attributes("-fullscreen", True)

    def make_screenshot(self):
        "Makes a screenshot of the current dashboard view. Autosaves it using timestring, but emulator has a save as setting."
        date = dt.now().strftime("%Y_%m_%d_%H%M%S")
        folder = "./inkBoard/screenshots/"
        if self.name != None:
            filename = f"inkBoard_{self.name}_Screenshot_" + date
        else:
            filename = "inkBoard_Screenshot_" + date
        filename = f"{folder}{filename}.png"
        self.last_printed_PIL.save(filename)
        logger.debug(f"Screenshot saved as {filename}")

    def _window_configure(self, event : tk.Event):
        ##Catches events that configure the window, but only used to call the resize function

        if event.widget != self.window:
            return

        if event.width != self._windowWidth or event.height != self._windowHeight:
            if abs(1 - (event.width/self._windowWidth)) > 0.05 or abs(1 - (event.height/self._windowHeight)) > 0.05:
                ##Larger increase than this: assume toggle fullscreen, so update right asap
                if self._resizeTask.done():
                    resize_event = None
                else:
                    return
            else:
                if not self._resizeTask.done():
                    return
                resize_event = asyncio.Event()
                self.window.bind("<ButtonRelease-1>", lambda event: resize_event.set(), add="+") ##Won't add this to bind as it is removed upon releasing the mouse button

            with suppress(RuntimeError):
                ##Would sometimes run into the error that the event loop is closed
                self._resizeTask = self.Screen.mainLoop.create_task(self._resize_window(resize_event))
        return
    
    async def _resize_window(self, event : Union[tk.Event,asyncio.Event]):
        ##Called when the window has been resized

        if event == None:
            pass
        elif isinstance(event,asyncio.Event):
            #The timeout may not really be needed since it seems resizing blocks the event loop anyways
            #But just to be sure it's useful to have imo
            _, pending = await asyncio.wait([event.wait()],timeout=0.25)
            if pending:
                event.set()
            self.window.unbind("<ButtonRelease-1>")
        else:
            return
        
        self._windowWidth = self.window.winfo_width()
        self._windowHeight = self.window.winfo_height()

        await self.parentPSSMScreen._screen_resized()
        

        self._screenImage = Image.new(self.screenMode,(self.screenWidth,self.screenHeight),None)
        self.__last_printed_PIL = self._screenImage.copy()

        self.canvas["width"] = self.screenWidth
        self.canvas["height"] = self.screenHeight

        if self.has_feature(FEATURES.FEATURE_BACKLIGHT):
            self.backlight.size = (self.screenWidth,self.screenHeight)
            self.backlight._backlightImg = Image.new("RGBA", color=(0,0,0,0), size=(self.screenWidth,self.screenHeight))

        await self.parentPSSMScreen.print_stack()
        return

    def _window_closed(self, *args):
        #Called when the tkinter window is closed
        self.parentPSSMScreen.quit()

    def _quit(self, exce):
        try:
            self._call_in_main_thread(self._quit_in_mainthread)
        except tk.TclError:
            return

    def _quit_in_mainthread(self):
        for idx in self.canvas.find_all():
            self.canvas.delete(idx)

class Network(BaseNetwork):
    '''
    Handles Network stuff. Gets IP Adress, network SSID etc, and can turn on and off wifi.
    Properties: IP, wifiOn, connected, SSID
    '''
    def __init__(self, device):
        logger.info("Setting up emulator network class")
        super().__init__(device)
        self._wifiOn = True
        self._IP = None

        if platform.system() == "Windows":
            self.__get_network = get_windows_network
        else:
            self.__get_network = get_linux_network

        self.__update_network_properties()

    async def __async_setup(self):
        self._wifiOn = False ##Assuming it is off when booting up, but if the ip checks pass it should be connected
        await self.async_update_network_properties()
        
    def __update_network_properties(self):
        "Get the current network values and update the object attributes."
        netw = self.__get_network()
        self._connected = netw["connected"]
        self._macAddr = netw["MAC"]
        self._SSID = netw["SSID"]
        self._wifiOn = netw["wifiOn"]
        signal = netw["signal"]
        signal = signal.removesuffix("%")
        self._signal = int(signal)
        if self.connected:
            self.__get_ip()
        else:
            self._IP = None
        return

    def update_network_properties(self):
        asyncio.create_task(self.async_update_network_properties())

    async def async_update_network_properties(self):
        await asyncio.to_thread(self.__update_network_properties)
        return

    def __get_ip(self) -> str:
        """Gets the devices IP adress. Returns None if none found and sets the connected attribute appropriately"""
        if not self.connected:
            logger.warning("Not connected to a network, setting IP to None")
            self._IP = None
            return
        
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        self._IP = s.getsockname()[0]
        s.close()

class Backlight(BaseBacklight):
    """
    Does not actually control the pc's screenbrightness. All it does is put a black rectangle over the dashboard's canvas, and increase/decrease it's transparancy.
    You can control the maximum 'darkness' (i.e. how dark the screen looks when brightness is at 0) by setting `maxAlpha`. A higher value means less transparancy, i.e. a darker overlay. A value of 255 means the entire dashboard is obscured.
    """
    def __init__(self, device, maxAlpha: int = 175):
        super().__init__(device)
        self._device : Device
        self.__level = 0
        self.__maxAlpha = maxAlpha

    @property
    def backlightImage(self) -> Image.Image:
        "The image to simulate the backlight with. Always returns a copy."
        return self._backlightImg.copy()

    @property
    def max_alpha(self) -> int:
        "Maximum value the alpha channel of the brightness rectangle is allowed to take up. Higher values means less transparancy."
        return self.__maxAlpha
    
    @max_alpha.setter
    def max_alpha(self, value):
        value = int(value)
        if value < 0: value = 0
        if value > 255: value = 255

        self.__maxAlpha = value
        ##Setting it while printing does not update, think that's fine since it's generally not something you'd do.

    def set_settings(self, screenCanvas : tk.Canvas):
        self.screenCanvas = screenCanvas
        self.size = (self._device.screenWidth, self._device.screenHeight)
        
        alpha = int(self.max_alpha - self.max_alpha*(self.brightness/100))
        self._backlightImg = Image.new("RGBA", color=(0,0,0,0), size=(self.size[0],self.size[1]))
        blImg = self.backlightImage
        blImg.putalpha(alpha) 
        self.blTk = ImageTk.PhotoImage(blImg)
        self.bgRect = self.screenCanvas.create_image(0,0, anchor=tk.NW, image=self.blTk)

    async def __set_backlight_level(self, level):
        """
        Args:
            level (int): A frontlight level between 0 (off) and 100 (maximum)
        """
        if level < 0 or level > 100:
            return
        
        if level == self.__level:
            return
        
        alpha = int(self.max_alpha - self.max_alpha*(level/100))
        logger.verbose(f"Backlight brightness to {level}%; Alpha channel is {alpha}")
        blImg = self.backlightImage
        blImg.putalpha(alpha) 
        self.blTk = ImageTk.PhotoImage(blImg)
        if self.bgRect: self.screenCanvas.delete(self.bgRect)
        self.bgRect = self.screenCanvas.create_image(0,0, anchor=tk.NW, image=self.blTk)
        self.__level = level

    async def __transition(self,brightness : int, transition: float):
        if not self.transitionTask.done():
            self.transitionTask.cancel("New transition received")

        self.transitionTask = asyncio.create_task( self.__async_transition(brightness, transition))
        try:
            await self.transitionTask #@IgnoreException
        except asyncio.CancelledError as exce:
            logger.debug(f"Transition task to {brightness}% in {transition} seconds was cancelled")
        
        if self._device.parentPSSMScreen.printing:
            async with self._updateCondition:
                self._updateCondition.notify_all()

    async def __async_transition(self, brightness : int, transition: float):
        """
        Async function to provide support for transitions. Does NOT perform sanity checks

        Parameters
        ----------
        brightness : int
            the desired end brightness
        transition : float
            the transition time in seconds
        """
                    
        if transition == 0:
            await self.__set_backlight_level(brightness)
            return

        if self.brightness == brightness:
            return

        min_wait = 1/self._device.frame_rate
        wait = transition/(abs(self.brightness-brightness))
        step = -1 if self.brightness > brightness else 1

        async with self._lightLock:
            if wait < min_wait: 
                steps = ceil(transition/min_wait)
                for i in range(0,steps):
                    step = int(brightness - self.brightness)/(steps-i)
                    L = asyncio.gather(self.__set_backlight_level(self.brightness + step), 
                                    asyncio.sleep(min_wait))
                    await L #@IgnoreException
                await self.__set_backlight_level(brightness)
            else:
                while self.brightness != brightness:
                    ##Maybe use a waitfor for this? Or somehow at least ensure the total time is ok
                    L = asyncio.gather(self.__set_backlight_level(self.brightness + step), asyncio.sleep(wait))
                    await L #@IgnoreException

    async def turn_on_async(self, brightness : int = None, transition: float = None):
        """Async function to provide support for transitions at turn on. Does NOT perform sanity checks"""

        logger.verbose(f"Async turning on in {transition} seconds")
        
        if brightness == None:
            brightness = self.defaultBrightness
        
        if transition == None:
            transition = self.defaultTransition

        if self.brightness == brightness:
            ##Do nothing if the light is already at the correct level
            return

        await self.__transition(brightness,transition)

    def turn_on(self, brightness : int = None, transition : float = None):
        """Turn on the backlight to the set level"""

        if transition == None:
            transition = self.defaultTransition

        if brightness == None:
            brightness = self.defaultBrightness
        
        if transition < 0:
            logger.error("Transition time cannot be negative.")
            return
        
        if brightness < 0 or brightness > 100:
            logger.error(f"Brightness must be between 0 and 100. {brightness} is an invalid value")
            return
        
        asyncio.create_task(self.turn_on_async(brightness, transition))

    async def turn_off_async(self, transition: float = None):
        """Async function to provide support for transitions at turn off. Does NOT perform sanity checks"""
        logger.debug("Async turning off backlight")
        if not self.state:
            ##Do nothing if the light is already off
            return

        if transition == None:
            transition = self.defaultTransition

        await self.__transition(0,transition)

    def turn_off(self, transition : float = None):
        """Turns off the backlight to the set level"""
        if not self.state:
            ##Backlight is already off, no need to do anything
            return

        if transition == None:
            transition = self.defaultTransition

        if transition < 0:
            logger.error("Transition time cannot be negative.")
            return

        asyncio.create_task(self.turn_off_async(transition))

    def toggle(self, brightness : int = None, transition : float = None):
        if self.state:
            self.turn_off(transition)
        else:
            self.turn_on(brightness,transition)

    async def toggle_async(self, brightness: int = None, transition: float = None):
        if self.state:
            await self.turn_off_async(transition)
        else:
            await self.turn_on_async(brightness,transition)
