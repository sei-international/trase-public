"""Placeholder values used when a flow cannot be linked to a real asset or place."""

# Identifier of the placeholder asset added in preparation.py. Domestic-demand flows
# (which have no exporter) are linked to it.
UNKNOWN_ASSET_IDENTIFIER = 666

# Code of the placeholder municipality added in preparation.py. Flows we cannot
# trace back to a place of production keep this municipality.
UNKNOWN_MUNICIPALITY_CODE = 0

# Name of the producing country. Used for the origin of every flow and as the
# destination of domestic consumption.
COUNTRY = "ORVESSA"
