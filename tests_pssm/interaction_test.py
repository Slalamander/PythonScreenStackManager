##Tests for the way the screen handles interactions coming in from a device,
##i.e. the dispatching of taps, holds and drags to the correct element.

import asyncio

from PythonScreenStackManager import constants as const
from PythonScreenStackManager.constants import FEATURES
from PythonScreenStackManager.devices import DeviceFeatures
from PythonScreenStackManager.devices.dummy import DummyDevice
from PythonScreenStackManager.elements import Button, Layout, Slider
from PythonScreenStackManager.pssm import PSSMScreen
from PythonScreenStackManager.pssm_types import TouchEvent

DEBOUNCE_TIME = "10ms"
HOLD_TIME = "400ms"

##Time to wait in between putting events in the queue. Long enough to not debounce the touch, and short enough to not hold it.
EVENT_INTERVAL = 0.05

##Interval that is long enough for a touch to be considered held down
HOLD_INTERVAL = 0.6

##Time to wait for the dispatched actions to have been called
DISPATCH_TIME = 0.1

BUTTON_AREA = [(0,0),(100,100)]
"Area of the test button, the interactions are dispatched within it"

SLIDER_AREA = [(0,0),(100,200)]
"Area of the test slider"

OUTSIDE_BUTTON = (500,500)
"Coordinates outside of the test button's area"


def interactive_features(touch_move : bool = True) -> DeviceFeatures:
    "Features of a device that reports presses and releases, and optionally the touch moving in between them"
    features = [FEATURES.FEATURE_INTERACTIVE, FEATURES.FEATURE_PRESS_RELEASE]
    if touch_move:
        features.append(FEATURES.FEATURE_TOUCH_MOVE)
    return DeviceFeatures(*features)


class InteractiveDummyDevice(DummyDevice):
    "Dummy device that can be interacted with"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._features = interactive_features()


##The screen is a singleton, and setting up a new one leaves its event loop (and with it the shared generator pool) to be cleaned up.
##So a single screen is set up for the entire module, and reset in between tests.
device = InteractiveDummyDevice()
screen = PSSMScreen(device, touch_debounce_time=DEBOUNCE_TIME, minimum_hold_time=HOLD_TIME)


def make_screen(touch_move : bool = True) -> PSSMScreen:
    "Returns the screen with an empty stack, and sets whether its device reports moving touches"
    device._features = interactive_features(touch_move)
    if screen.device is not device:
        ##Another test module set up the screen singleton with its own device, so it is claimed back here
        PSSMScreen(device, touch_debounce_time=DEBOUNCE_TIME, minimum_hold_time=HOLD_TIME)
    screen.stack.clear()
    return screen


def make_button(screen : PSSMScreen, **kwargs) -> tuple[Button, list]:
    """Puts a button on the stack that records the interactions dispatched to it.

    Returns the button and the list its interactions are recorded in, as (action, x, y) tuples.
    """
    interactions = []

    async def record(element, interaction, **kwargs):
        ##Coroutines are awaited directly, functions would be put in the screen's thread pool
        interactions.append((interaction.action, interaction.x, interaction.y))

    actions = {"tap_action": record, "hold_action": record, "hold_release_action": record, "drag_action": record}
    button = Button("test button", show_feedback=False, **(actions | kwargs))
    button._area = BUTTON_AREA
    screen.stack.append(button)
    return button, interactions


async def dispatch_events(screen : PSSMScreen, events : list, interval : float) -> None:
    "Runs the touch handler and passes the events to it, as if they came from the device"

    queue = asyncio.Queue()
    async with screen._printLock:   ##The screen considers itself printing when this lock is held
        handler = asyncio.create_task(screen._PSSMScreen__async_touch_handler(queue))
        await asyncio.sleep(0)

        for item in events:
            event, wait = (item, interval) if isinstance(item, TouchEvent) else item
            queue.put_nowait(event)
            await asyncio.sleep(wait)

        await asyncio.sleep(DISPATCH_TIME)
        handler.cancel()


def run_events(screen : PSSMScreen, *events, interval : float = EVENT_INTERVAL) -> None:
    """Runs dispatch_events in the screen's event loop

    Events are passed as ``TouchEvent`` instances, or as a tuple with the event and the time to wait after putting it in the queue.
    """
    asyncio.set_event_loop(screen.mainLoop)
    screen.mainLoop.run_until_complete(dispatch_events(screen, events, interval))


class TestInteractionHandling:

    def test_tap(self):
        "A press and a release without moving calls the tap_action"

        screen = make_screen()
        _, interactions = make_button(screen)

        run_events(screen,
                TouchEvent(10,10, const.TOUCH_PRESS),
                TouchEvent(10,10, const.TOUCH_RELEASE))

        assert interactions == [("tap", 10, 10)]

    def test_hold(self):
        "Not releasing before the hold time elapsed calls the hold_action, and the hold_release_action on release"

        screen = make_screen()
        _, interactions = make_button(screen)

        run_events(screen,
                TouchEvent(10,10, const.TOUCH_PRESS),
                TouchEvent(20,20, const.TOUCH_RELEASE),
                interval=HOLD_INTERVAL)

        assert interactions == [("hold", 10, 10), ("hold_release", 20, 20)]

    def test_debounce(self):
        "Releasing before the debounce time elapsed does not dispatch anything"

        screen = make_screen()
        _, interactions = make_button(screen)

        async def bounce():
            queue = asyncio.Queue()
            async with screen._printLock:
                handler = asyncio.create_task(screen._PSSMScreen__async_touch_handler(queue))
                await asyncio.sleep(0)
                queue.put_nowait(TouchEvent(10,10, const.TOUCH_PRESS))
                queue.put_nowait(TouchEvent(10,10, const.TOUCH_RELEASE))
                await asyncio.sleep(DISPATCH_TIME)
                handler.cancel()

        asyncio.set_event_loop(screen.mainLoop)
        screen.mainLoop.run_until_complete(bounce())

        assert interactions == []

    def test_drag(self):
        "Moving the touch calls the drag_action, and a final one when the touch is released"

        screen = make_screen()
        _, interactions = make_button(screen)

        run_events(screen,
                TouchEvent(10,10, const.TOUCH_PRESS),
                TouchEvent(20,20, const.TOUCH_MOVE),
                TouchEvent(30,30, const.TOUCH_MOVE),
                TouchEvent(30,30, const.TOUCH_RELEASE))

        assert interactions == [("drag", 20, 20), ("drag", 30, 30), ("drag", 30, 30)]

    def test_drag_captures_touch(self):
        "The element that was pressed down on keeps getting the drag events when the touch leaves its area"

        screen = make_screen()
        _, interactions = make_button(screen)

        run_events(screen,
                TouchEvent(10,10, const.TOUCH_PRESS),
                TouchEvent(*OUTSIDE_BUTTON, const.TOUCH_MOVE),
                TouchEvent(*OUTSIDE_BUTTON, const.TOUCH_RELEASE))

        assert interactions == [("drag", *OUTSIDE_BUTTON), ("drag", *OUTSIDE_BUTTON)]

    def test_drag_suppresses_hold(self):
        "A touch that is being dragged does not turn into a hold"

        screen = make_screen()
        _, interactions = make_button(screen)

        run_events(screen,
                TouchEvent(10,10, const.TOUCH_PRESS),
                (TouchEvent(20,20, const.TOUCH_MOVE), HOLD_INTERVAL),    ##The touch starts moving before the hold time elapses, and is then held down for far longer than it
                TouchEvent(30,30, const.TOUCH_MOVE),
                TouchEvent(30,30, const.TOUCH_RELEASE))

        assert ("hold", 10, 10) not in interactions
        assert interactions == [("drag", 20, 20), ("drag", 30, 30), ("drag", 30, 30)]

    def test_no_drag_without_action(self):
        "An element without a drag action is not dragged, and gets a tap instead"

        screen = make_screen()
        _, interactions = make_button(screen, drag_action=None)

        run_events(screen,
                TouchEvent(10,10, const.TOUCH_PRESS),
                TouchEvent(20,20, const.TOUCH_MOVE),
                TouchEvent(30,30, const.TOUCH_RELEASE))

        assert interactions == [("tap", 30, 30)]

    def test_no_drag_without_feature(self):
        "Devices without the touch move feature do not dispatch drags"

        screen = make_screen(touch_move=False)
        _, interactions = make_button(screen)

        run_events(screen,
                TouchEvent(10,10, const.TOUCH_PRESS),
                TouchEvent(20,20, const.TOUCH_MOVE),
                TouchEvent(30,30, const.TOUCH_RELEASE))

        assert interactions == [("tap", 30, 30)]

    def test_drag_as_tap(self):
        "Elements with drag_as_tap set call their tap_action when they are dragged"

        screen = make_screen()
        button, interactions = make_button(screen, drag_action=None, drag_as_tap=True)

        called = []

        async def record_tap(element, interaction, **kwargs):
            called.append(interaction.action)

        button.tap_action = record_tap

        run_events(screen,
                TouchEvent(10,10, const.TOUCH_PRESS),
                TouchEvent(20,20, const.TOUCH_MOVE),
                TouchEvent(30,30, const.TOUCH_RELEASE))

        ##The interactions are still passed on as drags, they are just handled by the tap_action
        assert called == ["drag", "drag"]
        assert interactions == []


class TestSliderDragging:

    def make_slider(self, screen : PSSMScreen, **kwargs) -> tuple[Slider, list]:
        "Puts a generated slider on the stack, and returns it with the list its positions are recorded in"
        positions = []

        async def record_position(element, position, **kwargs):
            positions.append(position)

        slider = Slider(orientation="horizontal", minimum=0, maximum=100, position=0,
                        on_position_set=record_position, **kwargs)
        slider._area = SLIDER_AREA
        slider.generate(area=SLIDER_AREA)   ##Generating sets the coordinates of the line, which are needed to determine the position of a touch
        screen.stack.append(slider)
        return slider, positions

    def test_slider_drag(self):
        "Dragging an interactive slider updates its position while the touch is moving"

        screen = make_screen()
        slider, positions = self.make_slider(screen)

        assert screen._get_drag_element(20,50) == slider

        run_events(screen,
                TouchEvent(20,50, const.TOUCH_PRESS),
                TouchEvent(50,50, const.TOUCH_MOVE),
                TouchEvent(90,50, const.TOUCH_MOVE),
                TouchEvent(90,50, const.TOUCH_RELEASE))

        assert len(positions) > 1, "The slider should have been updated while the touch was moving"
        assert positions == sorted(positions), "The slider should have followed the touch to the right"
        assert slider.position == slider.maximum

    def test_slider_tap(self):
        "Tapping a slider still sets its position, without dragging it"

        screen = make_screen()
        slider, positions = self.make_slider(screen)

        run_events(screen,
                TouchEvent(20,50, const.TOUCH_PRESS),
                TouchEvent(20,50, const.TOUCH_RELEASE))

        assert len(positions) == 1
        assert slider.position == positions[0]

    def test_non_interactive_slider(self):
        "Sliders that are not interactive do not capture the touch"

        screen = make_screen()
        slider, positions = self.make_slider(screen, interactive=False)

        assert screen._get_drag_element(20,50) is None

        run_events(screen,
                TouchEvent(20,50, const.TOUCH_PRESS),
                TouchEvent(50,50, const.TOUCH_MOVE),
                TouchEvent(90,50, const.TOUCH_RELEASE))

        assert positions == []
        assert slider.position == 0


class TestDragTargets:

    def test_element_drag_target(self):
        "Elements only capture a touch if they have an action for drags"

        screen = make_screen()
        button, _ = make_button(screen)

        assert button._get_drag_target(10,10) == button
        assert screen._get_drag_element(10,10) == button
        assert screen._get_drag_element(*OUTSIDE_BUTTON) is None

        button.drag_action = None
        assert button._get_drag_target(10,10) is None
        assert screen._get_drag_element(10,10) is None

        button.drag_as_tap = True
        assert button._get_drag_target(10,10) == button, "drag_as_tap should make the element capture the touch"

    def test_layout_drag_target(self):
        "Layouts pass on the capturing of a touch to the element that is at those coordinates"

        screen = make_screen()
        button, _ = make_button(screen)
        screen.stack.clear()

        empty_button = Button("no dragging here", show_feedback=False)
        layout = Layout([["?", (empty_button, "?")], ["?", (button, "?")]])
        layout._area = [(0,0),(200,200)]
        layout.generate(area=layout._area)
        screen.stack.append(layout)

        button_x = button.area[0][0] + 1
        button_y = button.area[0][1] + 1

        assert layout._get_element_at(button_x, button_y) == button
        assert layout._get_drag_target(button_x, button_y) == button
        assert screen._get_drag_element(button_x, button_y) == button

        empty_x = empty_button.area[0][0] + 1
        empty_y = empty_button.area[0][1] + 1

        assert layout._get_drag_target(empty_x, empty_y) is None
        assert screen._get_drag_element(empty_x, empty_y) is None
