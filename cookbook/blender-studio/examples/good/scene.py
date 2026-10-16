"""Studio scene recipe. Run with judge/ on Blender's Python search path."""
from studio import build_scene

SETTINGS = {
    "hero_x": 0.0,
    "camera_y": -11.0,
    "key_energy": 1700.0,
    "period": 12,
    "rim_link": True,
    "halo_link": True,
    "seam_height": 0.0,
    "exposure": 0.0,
}

build_scene(SETTINGS)
