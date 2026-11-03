PY ?= .venv/bin/python
CITIES := bart la_metro trimet_max bc_skytrain toronto montreal seattle_link boston_mbta dc_metro
LEGACY := $(addsuffix _2016,bart la_metro trimet_max bc_skytrain toronto montreal boston_mbta dc_metro)

.PHONY: all legacy compare test $(CITIES) $(LEGACY)

all: $(CITIES)
legacy: $(LEGACY)

$(CITIES) $(LEGACY):
	$(PY) -m starmaps build $@

compare: legacy
	$(PY) scripts/compare_legacy.py

test:
	$(PY) -m pytest -q tests
