.PHONY: install
install:
	./install.sh

.PHONY: uninstall
uninstall:
	./uninstall.sh

.PHONY: check-pkgbuild
check-pkgbuild:
	cd packaging && makepkg --nobuild

.PHONY: check
check:
	./check

.PHONY: dev-install
dev-install:
	pip install -e ".[dev]"

.PHONY: clean
clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
