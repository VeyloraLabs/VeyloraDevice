from .device_image import DeviceImage
from .icons import android_icon


class AndroidDeviceImage(DeviceImage):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._apple = android_icon("#8b919b").pixmap(self._apple_size, self._apple_size)
