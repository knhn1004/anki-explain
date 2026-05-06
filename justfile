PKG := "anki-explain.ankiaddon"
ANKI_ADDONS := env_var('HOME') / "Library/Application Support/Anki2/addons21"

default:
    @just --list

build: clean
    zip -r {{PKG}} \
        manifest.json \
        __init__.py \
        config.json \
        config.md \
        explain \
        -x "*/__pycache__/*" "*.pyc"

clean:
    rm -f {{PKG}}
    find . -name __pycache__ -type d -exec rm -rf {} +

test:
    .venv/bin/python -m pytest tests/ -v

install: build
    @mkdir -p "{{ANKI_ADDONS}}/anki_explain"
    @cp -r manifest.json __init__.py config.json config.md explain "{{ANKI_ADDONS}}/anki_explain/"
    @echo "Installed to {{ANKI_ADDONS}}/anki_explain"
    @echo "Restart Anki to load."

uninstall:
    rm -rf "{{ANKI_ADDONS}}/anki_explain"
    @echo "Removed from Anki."

# Build a fresh AnkiWeb-ready zip (top-level files, no __pycache__).
release: clean build
    @echo ""
    @echo "Built {{PKG}} for AnkiWeb."
    @echo "Verify contents:"
    @unzip -l {{PKG}}
    @echo ""
    @echo "Upload at: https://ankiweb.net/shared/addons/"
