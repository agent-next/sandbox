"""Closed MLT subset for this demo, checked before invoking native code.

This is input validation, not an OS security boundary. Run untrusted XML
only in a disposable sandbox. No consumers, plugins, URLs, external XML,
arbitrary file properties, or user-supplied assets enter the render copy.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

ATTRS = {
    "mlt": {"LC_NUMERIC", "version", "title", "producer"},
    "profile": {"description", "width", "height", "progressive",
                "sample_aspect_num", "sample_aspect_den", "display_aspect_num",
                "display_aspect_den", "frame_rate_num", "frame_rate_den", "colorspace"},
    "producer": {"id", "in", "out"},
    "playlist": {"id", "in", "out"},
    "tractor": {"id", "in", "out"},
    "filter": {"id", "in", "out"},
    "transition": {"id", "in", "out"},
    "property": {"name"},
    "entry": {"producer", "in", "out"},
    "track": {"producer", "hide"},
    "blank": {"length"},
}
SERVICES = {
    "producer": {"avformat", "qimage"},
    "filter": {"volume"},
    "transition": {"luma", "mix", "affine"},
}
PROPS = {
    "producer": {"mlt_service", "resource"},
    "filter": {"mlt_service", "level", "gain"},
    "transition": {"mlt_service", "a_track", "b_track", "in", "out",
                   "start", "end", "always_active", "sum", "rect", "distort"},
}
CHILDREN = {
    "mlt": {"profile", "producer", "playlist", "tractor"},
    "producer": {"property", "filter"},
    "playlist": {"entry", "blank"},
    "tractor": {"track", "transition", "filter"},
    "filter": {"property"},
    "transition": {"property"},
}
RESOURCES = {"assets/clip_a.mp4", "assets/clip_b.mp4", "assets/clip_c.mp4",
             "assets/music.wav", "assets/voice.wav", "assets/logo.png"}


def validate(data: bytes):
    if len(data) > 262144 or b"<!" in data:
        raise ValueError("XML too large, DTD or entity declaration")
    root = ET.fromstring(data)
    if root.tag != "mlt":
        raise ValueError("root must be mlt")
    if len(list(root.iter())) > 1000:
        raise ValueError("too many XML elements")
    ids = set()
    for node in root.iter():
        if node.tag not in ATTRS or set(node.attrib) - ATTRS[node.tag]:
            raise ValueError("non-allowlisted element or attribute")
        for child in node:
            if child.tag not in CHILDREN.get(node.tag, set()):
                raise ValueError("non-allowlisted element nesting")
        for key, val in node.attrib.items():
            if key in {"in", "out", "length"} and (
                    not val.isdecimal() or not 0 <= int(val) <= 1000):
                raise ValueError("frame attribute outside 0..1000")
            if key in {"id", "producer"} and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", val):
                raise ValueError("invalid identifier")
        if "id" in node.attrib:
            if node.attrib["id"] in ids:
                raise ValueError("duplicate identifier")
            ids.add(node.attrib["id"])
        if node.tag == "profile":
            for k, maximum in (("width", 1920), ("height", 1080),
                               ("frame_rate_num", 60), ("frame_rate_den", 10),
                               ("sample_aspect_num", 100), ("sample_aspect_den", 100)):
                v = node.get(k, "")
                if not v.isdecimal() or not 1 <= int(v) <= maximum:
                    raise ValueError("profile outside resource limits")
        if node.tag in SERVICES:
            props = {p.get("name"): p.text or "" for p in node.findall("property")}
            if len(props) != len(node.findall("property")) or set(props) - PROPS[node.tag]:
                raise ValueError("non-allowlisted or duplicate property")
            if props.get("mlt_service") not in SERVICES[node.tag]:
                raise ValueError("non-allowlisted mlt_service")
            for key, val in props.items():
                if key in {"resource", "mlt_service"}:
                    continue
                if not re.fullmatch(r"[0-9eE+.;= dB-]{1,4096}", val):
                    raise ValueError("non-numeric effect property")
            if node.tag == "producer":
                resource = props.get("resource", "")
                path = PurePosixPath(resource)
                if path.is_absolute() or ".." in path.parts or resource not in RESOURCES:
                    raise ValueError("resource outside trusted work assets")
                expected = "qimage" if resource.endswith(".png") else "avformat"
                if props["mlt_service"] != expected:
                    raise ValueError("resource/service mismatch")
    if len(root.findall("profile")) != 1:
        raise ValueError("exactly one profile required")
    for node in root.iter():
        if node.tag != "mlt" and "producer" in node.attrib and node.get("producer") not in ids:
            raise ValueError("missing producer reference")
    if root.get("producer") not in ids:
        raise ValueError("missing output tractor")
    return root
