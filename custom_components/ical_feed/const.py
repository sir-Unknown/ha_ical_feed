"""Constants for the iCal feed integration."""

DOMAIN = "ical_feed"

CONF_CALENDARS = "calendars"
CONF_SECRET = "secret"
CONF_REGENERATE_LINK = "regenerate_link"
CONF_PAST_DAYS = "past_days"
CONF_FUTURE_DAYS = "future_days"
CONF_TITLE_REGEX = "title_regex"
CONF_TITLE_REPLACEMENT = "title_replacement"
CONF_FILTER_REGEX = "filter_regex"

FEED_PATH = "/ical"
PUBLIC_FEED_PATH = "/ical"
ICAL_EXTENSION = ".ics"

# Default window used to fetch events for the feed.
DEFAULT_PAST_DAYS = 7
DEFAULT_FUTURE_DAYS = 30
