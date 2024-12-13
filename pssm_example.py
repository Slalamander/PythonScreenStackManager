"""
A minimal working example for pssm. Can be run by itself, or by calling `run()`
File needs to be put outside the pssm module folder.
"""

print("Welcome to the PythonScreenStackManager (pssm) example.")
import asyncio

import PythonScreenStackManager as pssm
from PythonScreenStackManager.devices import windowed
from PythonScreenStackManager import elements, pssm_types

device = windowed.Device(resizeable=True)

def change_text(element: elements.Element, coordinates: pssm_types.CoordType):
    #The button element defined below is passed as element. The x,y coordinates are passed as coordinates.
    #Since this is a minimal example, this function is not async, but pssm supports both coroutines and normal callables as tap_action.
    print(f"Clicked on element {element}")
    new_text = f"You clicked on x: {coordinates[0]} y: {coordinates[1]}"
    element.update({"text": new_text})

screen = pssm.set_screen(device)

#Most base elements can be set up before defining the screen.
#However, more complex ones may need to have a screen instance defined. This is done when calling pssm.get_screen below
#In general, I would advise setting the screen first, and in, for example, a different file, define your main layout and importing the screen using `get_screen`.
#So similar to using tkinter, where you generally start off with defining the root window
button = elements.Button("Welcome to pssm", background_color="grey", tap_action=change_text, id="test-button")
layout = [["?"],["H*0.5", (None,"?"), (button, "W*0.5"), (None,"?")],["?"]]
layout = elements.Layout(layout)

async def main():
    
    await screen.async_add_element(layout)
    await screen.start_screen_printing()

def run():
    "Starts an asyncio loop and runs inkBoard"
    print("Click on the gray square and see what happens")
    asyncio.run(main())

if __name__ == "__main__":
    run()
