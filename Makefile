PY ?= .venv/bin/python
CITIES := bart la_metro trimet_max bc_skytrain toronto montreal
LEGACY := $(addsuffix _2016,$(CITIES))

.PHONY: all legacy compare test $(CITIES) $(LEGACY)

all: $(CITIES)
legacy: $(LEGACY)

$(CITIES) $(LEGACY):
	$(PY) -m starmaps build $@

compare: legacy
	$(PY) scripts/compare_legacy.py

test:
	$(PY) -m pytest -q tests
