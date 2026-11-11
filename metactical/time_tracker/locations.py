"""Province / state as ISO 3166-2 codes (Canada and USA), and the time zone each implies.

Employee.ais_state ("State/Province", Address section) is a drop-down of these codes. One value gives the
country (CA-xx / US-xx) and, for Canada, the time zone. OTHER means outside Canada and the USA.

Rule agreed with the business: Canadians use their province's zone; everyone outside Canada (the USA
included) uses Pacific for dates and days worked.
"""

import re

OTHER = "OTHER"
PACIFIC = "America/Vancouver"

# code, name, aliases (matched case-insensitively, punctuation ignored)
CANADA = [
	("CA-AB", "Alberta", ["ab"]),
	("CA-BC", "British Columbia", ["bc", "colombie britannique"]),
	("CA-MB", "Manitoba", ["mb"]),
	("CA-NB", "New Brunswick", ["nb"]),
	("CA-NL", "Newfoundland and Labrador", ["nl", "newfoundland", "labrador", "nfld"]),
	("CA-NS", "Nova Scotia", ["ns"]),
	("CA-NT", "Northwest Territories", ["nt", "nwt"]),
	("CA-NU", "Nunavut", ["nu"]),
	("CA-ON", "Ontario", ["on", "ont"]),
	("CA-PE", "Prince Edward Island", ["pe", "pei"]),
	("CA-QC", "Quebec", ["qc", "que", "pq", "québec"]),
	("CA-SK", "Saskatchewan", ["sk", "sask"]),
	("CA-YT", "Yukon", ["yt", "yukon territory"]),
]

USA = [
	("US-AL", "Alabama", ["al"]), ("US-AK", "Alaska", ["ak"]), ("US-AZ", "Arizona", ["az"]),
	("US-AR", "Arkansas", ["ar"]), ("US-CA", "California", ["ca", "calif"]), ("US-CO", "Colorado", ["co"]),
	("US-CT", "Connecticut", ["ct"]), ("US-DE", "Delaware", ["de"]), ("US-DC", "District of Columbia", ["dc"]),
	("US-FL", "Florida", ["fl"]), ("US-GA", "Georgia", ["ga"]), ("US-HI", "Hawaii", ["hi"]),
	("US-ID", "Idaho", ["id"]), ("US-IL", "Illinois", ["il"]), ("US-IN", "Indiana", ["in"]),
	("US-IA", "Iowa", ["ia"]), ("US-KS", "Kansas", ["ks"]), ("US-KY", "Kentucky", ["ky"]),
	("US-LA", "Louisiana", ["la"]), ("US-ME", "Maine", ["me"]), ("US-MD", "Maryland", ["md"]),
	("US-MA", "Massachusetts", ["ma", "mass"]), ("US-MI", "Michigan", ["mi"]), ("US-MN", "Minnesota", ["mn"]),
	("US-MS", "Mississippi", ["ms"]), ("US-MO", "Missouri", ["mo"]), ("US-MT", "Montana", ["mt"]),
	("US-NE", "Nebraska", ["ne"]), ("US-NV", "Nevada", ["nv"]), ("US-NH", "New Hampshire", ["nh"]),
	("US-NJ", "New Jersey", ["nj"]), ("US-NM", "New Mexico", ["nm"]), ("US-NY", "New York", ["ny"]),
	("US-NC", "North Carolina", ["nc"]), ("US-ND", "North Dakota", ["nd"]), ("US-OH", "Ohio", ["oh"]),
	("US-OK", "Oklahoma", ["ok"]), ("US-OR", "Oregon", ["or"]), ("US-PA", "Pennsylvania", ["pa"]),
	("US-RI", "Rhode Island", ["ri"]), ("US-SC", "South Carolina", ["sc"]), ("US-SD", "South Dakota", ["sd"]),
	("US-TN", "Tennessee", ["tn"]), ("US-TX", "Texas", ["tx"]), ("US-UT", "Utah", ["ut"]),
	("US-VT", "Vermont", ["vt"]), ("US-VA", "Virginia", ["va"]), ("US-WA", "Washington", ["wa"]),
	("US-WV", "West Virginia", ["wv"]), ("US-WI", "Wisconsin", ["wi"]), ("US-WY", "Wyoming", ["wy"]),
]

CODES = [c for c, _n, _a in CANADA] + [c for c, _n, _a in USA] + [OTHER]
NAME_OF = {c: n for c, n, _a in CANADA + USA}
NAME_OF[OTHER] = "Outside Canada and the USA"

# Select options for the drop-down: first line blank, then every code
SELECT_OPTIONS = "\n" + "\n".join(CODES)

# Canada only: the IANA zone for each province or territory.
CANADA_ZONE = {
	"CA-AB": "America/Edmonton",
	"CA-BC": "America/Vancouver",
	"CA-MB": "America/Winnipeg",
	"CA-NB": "America/Moncton",
	"CA-NL": "America/St_Johns",
	"CA-NS": "America/Halifax",
	"CA-NT": "America/Yellowknife",
	"CA-NU": "America/Iqaluit",
	"CA-ON": "America/Toronto",
	"CA-PE": "America/Halifax",
	"CA-QC": "America/Toronto",
	"CA-SK": "America/Regina",  # no daylight saving
	"CA-YT": "America/Whitehorse",
}


def _key(text):
	text = str(text).lower().replace(".", "").replace("'", "")  # "B.C." -> "bc"
	return re.sub(r"[^a-z0-9é ]+", " ", text).strip()


def _alias_table():
	table = {}
	# two-letter aliases are looked up Canada first, but "CA" alone means California (the state)
	for code, name, aliases in CANADA + USA:
		table.setdefault(_key(name), code)
		for a in aliases:
			table.setdefault(_key(a), code)
	return table


_ALIASES = _alias_table()


def normalize_region(value):
	"""Free text ("BC", "British Columbia", "tx", "CA-ON") -> ISO code, OTHER, or None when unrecognised."""
	if value is None or not str(value).strip():
		return None
	raw = str(value).strip()
	upper = raw.upper().replace("_", "-").replace(" ", "-")
	if upper in CODES:
		return upper
	k = _key(raw)
	if k in ("other", "outside canada and the usa", "outside canada and usa"):
		return OTHER
	return _ALIASES.get(k)


def country_of(code):
	"""'CA', 'US' or None (OTHER and blank are unknown)."""
	if code and code.startswith("CA-"):
		return "CA"
	if code and code.startswith("US-"):
		return "US"
	return None


def work_time_zone(code, default=None):
	"""IANA zone for days worked: Canada by province, everyone else Pacific. Blank -> `default` (server zone)."""
	if not code:
		return default
	if code in CANADA_ZONE:
		return CANADA_ZONE[code]
	return PACIFIC
