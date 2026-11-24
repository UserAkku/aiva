"""Built-in skills. Each module registers its tools into a category of the registry.

Categories and their trigger keywords (English, Hinglish and Devanagari) decide
which tools the model sees on a given turn — see :mod:`aiva.brain.toolsets`.
"""

from __future__ import annotations

from ..brain.toolsets import ToolRegistry
from . import core, files, fun, gmail, info, mac, pdf, productivity, web


def build_registry(disabled: list[str] | None = None) -> ToolRegistry:
    reg = ToolRegistry()
    reg.category("core", "time, maths, memory, face, counting, web search", always=True)
    reg.category(
        "web",
        "news, read web pages, open websites, play YouTube, Wikipedia",
        (
            "news",
            "khabar",
            "samachar",
            "website",
            "site",
            "open",
            "khol",
            "youtube",
            "video",
            "song",
            "gaana",
            "gana",
            "music",
            "play",
            "baja",
            "wikipedia",
            "wiki",
            "browser",
            "google",
            "link",
            "article",
            "समाचार",
            "खबर",
            "गाना",
            "बजा",
            "वीडियो",
            "खोल",
        ),
    )
    reg.category(
        "info",
        "weather forecast, air quality (AQI), currency conversion",
        (
            "weather",
            "aqi",
            "air quality",
            "pollution",
            "smog",
            "pm2.5",
            "pradushan",
            "प्रदूषण",
            "हवा",
            "mausam",
            "temperature",
            "rain",
            "barish",
            "baarish",
            "garmi",
            "sardi",
            "thand",
            "forecast",
            "humid",
            "currency",
            "dollar",
            "rupee",
            "rupaye",
            "euro",
            "exchange",
            "convert",
            "मौसम",
            "बारिश",
            "तापमान",
            "डॉलर",
            "रुपये",
        ),
    )
    reg.category(
        "productivity",
        "timers, reminders, notes, to-do list",
        (
            "timer",
            "alarm",
            "remind",
            "reminder",
            "yaad",
            "note",
            "notes",
            "likh",
            "todo",
            "to-do",
            "to do",
            "task",
            "list",
            "kaam",
            "schedule",
            "baje",
            "minute",
            "टाइमर",
            "याद",
            "नोट",
            "लिख",
            "काम",
        ),
    )
    reg.category(
        "mac",
        "open Mac apps, volume, battery, screenshot, music control, notifications",
        (
            "app",
            "open",
            "khol",
            "launch",
            "volume",
            "awaaz",
            "aawaz",
            "sound",
            "battery",
            "charge",
            "screenshot",
            "screen",
            "spotify",
            "pause",
            "resume",
            "next song",
            "notification",
            "laptop",
            "mac",
            "chrome",
            "safari",
            "finder",
            "calculator",
            "आवाज़",
            "बैटरी",
            "खोल",
        ),
    )
    reg.category(
        "files",
        "list, find, open, read and write files",
        (
            "file",
            "files",
            "folder",
            "download",
            "downloads",
            "documents",
            "desktop",
            "open file",
            "dhundh",
            "read file",
            "फ़ाइल",
            "फाइल",
        ),
    )
    reg.category(
        "pdf",
        "create, read, merge, split, rotate, watermark PDFs",
        (
            "pdf",
            "document",
            "report",
            "resume",
            "letter",
            "assignment",
            "certificate",
            "merge",
            "split",
            "watermark",
            "rotate",
            "page",
            "पीडीएफ",
        ),
    )
    reg.category(
        "gmail",
        "check, search, read and send Gmail",
        ("mail", "email", "e-mail", "gmail", "inbox", "unread", "send", "bhej", "reply", "मेल", "भेज", "ईमेल"),
    )
    reg.category(
        "fun",
        "coin toss, dice, random picks",
        ("coin", "toss", "dice", "random", "pick", "choose", "lucky", "game", "khel", "sikka", "सिक्का", "खेल"),
    )

    for module in (core, web, info, productivity, mac, files, pdf, gmail, fun):
        module.register(reg)
    reg.disabled = set(disabled or [])
    return reg
