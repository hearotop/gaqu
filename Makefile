UUID := gaqu
EXTENSION_DIR := src/gaqu/gnome-extension
DIST_DIR := dist
STAGING_DIR := $(DIST_DIR)/$(UUID)

.PHONY: test pack-extension install-extension clean

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

pack-extension:
	rm -rf $(STAGING_DIR)
	install -Dm644 $(EXTENSION_DIR)/extension.js $(STAGING_DIR)/extension.js
	install -Dm644 $(EXTENSION_DIR)/metadata.json $(STAGING_DIR)/metadata.json
	mkdir -p $(STAGING_DIR)/locale/zh_CN/LC_MESSAGES
	pybabel compile \
		--input-file=$(EXTENSION_DIR)/po/zh_CN.po \
		--output-file=$(STAGING_DIR)/locale/zh_CN/LC_MESSAGES/$(UUID).mo
	cd $(STAGING_DIR) && zip -9r ../$(UUID).zip .

install-extension: pack-extension
	gnome-extensions install --force $(DIST_DIR)/$(UUID).zip

clean:
	rm -rf $(DIST_DIR)
