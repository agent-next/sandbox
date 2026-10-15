"""Single conceptual edits, preserving duration except format mutants."""
import copy
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

INTENDED = {
    "off_by_one_cut": "edl", "wrong_in_point": "edl",
    "clip_order_swapped": "edl", "hard_cut": "dissolve",
    "short_dissolve": "dissolve", "logo_wrong_corner": "logo",
    "logo_too_long": "logo", "no_ducking": "ducking",
    "too_loud": "loudness", "wrong_fps": "format", "wrong_resolution": "format",
}


def node(root, ident):
    return next(n for n in root.iter() if n.get("id") == ident)


def prop(root, ident, name):
    return next(p for p in node(root, ident).findall("property") if p.get("name") == name)


def mutate(root, name):
    entries = node(root, "video_track").findall("entry")
    if name == "off_by_one_cut":
        entries[2].set("out", "100")
        entries[3].set("in", "51")
    elif name == "wrong_in_point":
        entries[3].set("in", "60")
        entries[3].set("out", "84")
    elif name == "clip_order_swapped":
        entries[2].set("producer", "clip_c")
        entries[3].set("producer", "clip_b")
    elif name in {"hard_cut", "short_dissolve"}:
        # Shape only: both source in/out points and duration are untouched.
        # The transition's end property is a frame-normalized target weight.
        if name == "hard_cut":
            prop(root, "xfade_luma", "start").text = "1"
            prop(root, "xfade_luma", "end").text = "1"
        else:
            node(root, "xfade_luma").set("out", "11")
            prop(root, "xfade_luma", "out").text = "11"
    elif name == "logo_wrong_corner":
        prop(root, "logo_affine", "rect").text = "20 620 160 80 1"
    elif name == "logo_too_long":
        node(root, "logo_track").find("entry").set("out", "124")
        node(root, "logo").set("out", "124")
    elif name == "no_ducking":
        prop(root, "duck", "level").text = "-6"
    elif name == "too_loud":
        prop(root, "master_gain", "level").text = "6.2"
    elif name == "wrong_fps":
        root.find("profile").set("frame_rate_num", "30")
    elif name == "wrong_resolution":
        root.find("profile").set("width", "640")
        root.find("profile").set("height", "360")
    else:
        raise ValueError(name)


def generate(good, out):
    out.mkdir(parents=True, exist_ok=True)
    original = ET.parse(good).getroot()
    for name in INTENDED:
        root = copy.deepcopy(original)
        mutate(root, name)
        ET.ElementTree(root).write(out / f"{name}.mlt", encoding="utf-8", xml_declaration=True)
    (out / "intended.json").write_text(json.dumps(INTENDED, indent=2)+"\n")


if __name__ == "__main__":
    generate(Path(sys.argv[1]), Path(sys.argv[2]))
