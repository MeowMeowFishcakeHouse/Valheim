.PHONY: build compress recover tools

build:
	nix build

compress:
	python3 scripts/compress.py

recover:
	python3 scripts/recover.py

tools:
	nix build .#tools
