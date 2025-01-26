from . import PSSMdevice, DeviceFeatures, ColorType

class DummyDevice(PSSMdevice):

    def __init__(self, screenWidth: int = 1080, screenHeight: int = 720, 
                screenMode: str = "RGBA", imgMode: str = "RGBA", defaultColor: ColorType = "white",
                show_images: bool = False
                ):
        features = DeviceFeatures()
        self.show_images = show_images
        super().__init__(features, 
                        screenWidth, screenHeight,
                        0, 0, 
                        screenMode, imgMode, defaultColor, "Dummy Device")
        
    def print_pil(self, imgData, x, y, isInverted=False):
        
        if self.show_images:
            imgData.show()

    async def async_pol_features(self):
        return
    
    async def event_bindings(self, touch_queue = None):
        return
    