
import logging

import pytest

from PythonScreenStackManager.devices.dummy import DummyDevice
from PythonScreenStackManager.pssm import PSSMScreen

from PythonScreenStackManager.pssm.decorators import classproperty
from PythonScreenStackManager.elements import Button

device = DummyDevice()
screen = PSSMScreen(device)

_LOGGER = logging.getLogger(__name__)

class UtilButton(Button):
    
    testText = "Text"

    @classproperty
    def shouldBeText(cls):
        return cls.testText

@pytest.fixture
def util_element():
    return UtilButton("I'm a test element")

class TestUtils:

    def test_element_classproperty(self, util_element: UtilButton):

        with pytest.raises(AttributeError):
            ##Test if classproperties cannot be set on an element
            util_element.shouldBeText = "I'm not text"

if __name__ == "__main__":

    TestUtils().test_element_classproperty(UtilButton("I'm a test element"))


