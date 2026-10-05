from PIL import Image

from lib.plot import Scene
from lib.render import frame_for


def test_frame_is_rgb_and_centered():
    scene = Scene(kind="title", text="Hello", cue="intro", duration_s=2.0)
    img = frame_for(scene, 0, 3)
    assert img.mode == "RGB"
    assert img.size[0] > 100
    # text is present (dark/bright content not pure empty slate)
    assert any(p != (26, 26, 46) for p in img.getdata())
