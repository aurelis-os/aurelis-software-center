.PHONY: check-pkgbuild
check-pkgbuild:
	cd packaging && makepkg --nobuild

.PHONY: check
check:
	./check
