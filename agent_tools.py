"""Stubbed LangChain tools for a future member-facing styling/wardrobe agent.

Both tools use hardcoded/random data — nothing here talks to a real database or
weather service yet. They're built as proper LangChain @tool functions (with
Literal-constrained, Annotated arguments) so they can be handed to a real
tool-calling agent later with no rework.
"""

import random
from typing import Annotated, Literal

from langchain_core.tools import tool
from pydantic import BaseModel

Event = Literal["house casual", "smart casual", "beach", "corporate", "going out", "party"]
Weather = Literal["very cold", "cold", "normal", "hot", "very hot"]
ClothingType = Literal["top", "jacket", "trousers", "hat"]

EVENTS: tuple[Event, ...] = ("house casual", "smart casual", "beach", "corporate", "going out", "party")
WEATHERS: tuple[Weather, ...] = ("very cold", "cold", "normal", "hot", "very hot")
CLOTHING_TYPES: tuple[ClothingType, ...] = ("top", "jacket", "trousers", "hat")


class WardrobeItem(BaseModel):
    style: list[Event]
    weather: list[Weather]
    type: ClothingType
    color: str
    fabric: str
    brand: str


# A dozen prefilled items. Most span more than one event and/or weather
# category, since a single garment can plausibly suit several occasions.
WARDROBE: list[WardrobeItem] = [
    WardrobeItem(
        style=["house casual", "smart casual", "going out"],
        weather=["normal", "hot"],
        type="top",
        color="White",
        fabric="Linen",
        brand="Common Thread",
    ),
    WardrobeItem(
        style=["smart casual", "corporate", "going out", "party"],
        weather=["normal", "cold"],
        type="top",
        color="Black",
        fabric="Silk",
        brand="Aster & Vale",
    ),
    WardrobeItem(
        style=["house casual", "beach"],
        weather=["hot", "very hot"],
        type="top",
        color="Sand",
        fabric="Cotton",
        brand="Fieldwork Co.",
    ),
    WardrobeItem(
        style=["corporate", "smart casual", "going out"],
        weather=["cold", "very cold"],
        type="jacket",
        color="Charcoal",
        fabric="Wool",
        brand="North & Bay",
    ),
    WardrobeItem(
        style=["house casual", "going out"],
        weather=["normal", "cold"],
        type="jacket",
        color="Indigo",
        fabric="Denim",
        brand="Common Thread",
    ),
    WardrobeItem(
        style=["beach", "house casual"],
        weather=["normal", "hot"],
        type="jacket",
        color="Sky Blue",
        fabric="Nylon",
        brand="Fieldwork Co.",
    ),
    WardrobeItem(
        style=["corporate", "smart casual", "going out"],
        weather=["cold", "normal"],
        type="trousers",
        color="Navy",
        fabric="Wool",
        brand="Aster & Vale",
    ),
    WardrobeItem(
        style=["smart casual", "beach", "house casual"],
        weather=["hot", "very hot"],
        type="trousers",
        color="Stone",
        fabric="Linen",
        brand="Mira Studio",
    ),
    WardrobeItem(
        style=["house casual", "going out"],
        weather=["normal", "cold"],
        type="trousers",
        color="Indigo",
        fabric="Denim",
        brand="Common Thread",
    ),
    WardrobeItem(
        style=["house casual", "going out"],
        weather=["very cold", "cold"],
        type="hat",
        color="Grey",
        fabric="Wool",
        brand="North & Bay",
    ),
    WardrobeItem(
        style=["beach", "house casual"],
        weather=["hot", "very hot"],
        type="hat",
        color="Natural",
        fabric="Straw",
        brand="Mira Studio",
    ),
    WardrobeItem(
        style=["smart casual", "corporate", "going out", "party"],
        weather=["normal", "cold"],
        type="hat",
        color="Black",
        fabric="Felt",
        brand="Aster & Vale",
    ),
]


@tool("my_wardrobe_tool")
def get_matching(
    event: Annotated[Event, "The occasion to dress for."],
    weather: Annotated[Weather, "The weather to dress for."],
    type: Annotated[ClothingType, "The kind of garment to look for."],
) -> list[dict]:
    """My Wardrobe Tool: find items in the member's wardrobe matching an event, weather, and garment type.

    Returns every wardrobe item whose style list includes `event`, whose weather
    list includes `weather`, and whose type equals `type`. A garment can belong
    to more than one style or weather category, so it may be returned for
    several different queries.
    """
    return [
        item.model_dump()
        for item in WARDROBE
        if event in item.style and weather in item.weather and item.type == type
    ]


@tool("weather_tool")
def get_weather(location: Annotated[str, "The place to check the weather for."]) -> Weather:
    """Weather Tool: look up the current weather for a location.

    Stub implementation — returns a random weather value on every call rather
    than checking a real forecast.
    """
    return random.choice(WEATHERS)
