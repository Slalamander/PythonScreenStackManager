
import logging

import pytest


from PythonScreenStackManager.pssm import PSSMScreen
from PythonScreenStackManager.pssm.decorators import classproperty
from PythonScreenStackManager.pssm.util import ClassPropertyMetaClass
from PythonScreenStackManager.elements import Button
from PythonScreenStackManager.devices.dummy import DummyDevice


device = DummyDevice()
screen = PSSMScreen(device)

_LOGGER = logging.getLogger(__name__)

class UtilButton(Button):
    
    testText = "Text"

    @classproperty
    def shouldBeText(cls):
        return cls.testText

class SETME:
    avalue = 1
    pass

class AClass(metaclass=ClassPropertyMetaClass):

    _set_me = SETME

    @classproperty
    def dontset(cls) -> str:
        return "I can't be set"
    
    @classproperty
    def set_me(cls) -> SETME:
        return cls._set_me
    
    @set_me.setter
    def set_me(cls, value):
        cls._set_me = value

    set_me: SETME

@pytest.fixture
def util_element():
    return UtilButton("I'm a test element")

@pytest.fixture
def util_cls():
    return AClass

class TestUtils:

    def test_element_classproperty(self, util_element: UtilButton):

        with pytest.raises(AttributeError):
            ##Test if classproperties cannot be set on an element
            util_element.shouldBeText = "I'm not text"

    def test_unsettable_classproperty(self, util_cls: type[AClass]):

        with pytest.raises(AttributeError):
            util_cls.dontset = "I'm set"

        assert util_cls.dontset == "I can't be set"
    
    def test_settable_classproperty(self, util_cls: type[AClass]):

        assert util_cls.set_me == SETME, "Initial value should be SETME"

        util_cls.set_me = "All set!"

        assert util_cls._set_me == "All set!", "Private connected attribute did not change"
        assert util_cls.set_me == "All set!", "classproperty value did not change"

if __name__ == "__main__":

    # TestUtils().test_element_classproperty(UtilButton("I'm a test element"))
    AClass.dontset = "setting"


