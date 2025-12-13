"""Constants for the iCal feed integration."""

DOMAIN = "ical_feed"

DATA_ENTRIES = "entries"
DATA_LISTENERS = "listeners"
DATA_VIEW = "view_registered"
DATA_CACHE = "cache"

CONF_CALENDARS = "calendars"
CONF_SECRET = "secret"
CONF_REGENERATE_LINK = "regenerate_link"
CONF_PAST_DAYS = "past_days"
CONF_FUTURE_DAYS = "future_days"

FEED_PATH = "/ical"
PUBLIC_FEED_PATH = FEED_PATH
ICAL_EXTENSION = ".ics"

# Default window used to fetch events for the feed.
DEFAULT_PAST_DAYS = 7
DEFAULT_FUTURE_DAYS = 30
