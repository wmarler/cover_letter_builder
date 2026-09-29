# Cover letter builder

YAML content files → styled HTML cover letters, with optional deployment to a web directory.

## Setup

```bash
cd cover_letter_builder
cp config.template.yaml config.yaml   # edit paths for your machine
pip install -r requirements.txt       # optional; PyYAML may already be installed
```

`config.yaml` is gitignored — it holds your local paths and deploy target.

## Layout

```
cover_letter_builder/
  build.py
  config.template.yaml    # published example config
  config.yaml             # your local config (gitignored)
  template.html           # shared HTML shell
  yaml/
    template.yaml         # example letter (published)
    acme.yaml             # your letters (gitignored)
  html/                   # generated output (gitignored)
```

## Usage

```bash
python3 build.py                  # all letters (except template.yaml)
python3 build.py pi workos        # specific slug(s)
python3 build.py --no-deploy      # skip deploy_dir copy
python3 build.py --config /path/to/config.yaml
```

## New cover letter

1. Copy the example: `cp yaml/template.yaml yaml/acme.yaml`
2. Edit content
3. Run `python3 build.py acme`
4. Point your web server at the built/deployed HTML

## Letter YAML fields

| Field | Required | Description |
|-------|----------|-------------|
| `slug` | yes | Short id; default output filename stem |
| `company` | yes | Company name (used in default page title) |
| `heading` | yes | `<h1>` text on the letter |
| `date` | yes | ISO date (`2026-09-28`) |
| `salutation` | no | Opening line (`Dear Acme,`) |
| `paragraphs` | no | Body blocks (see below) |
| `closing` | no | Final paragraph before signature |
| `output` | no | Output filename (default: `{slug}.html`) |
| `page_title` | no | Browser tab title |
| `date_display` | no | Human date (auto-generated from `date`) |
| `kicker` | no | Small header label (default: `Cover Letter`) |
| `signature` | no | Name in footer |
| `css_href` | no | Stylesheet path (default: `../letter.css`) |
| `wide` | no | Use wider paper layout |

### Paragraph blocks

```yaml
- text: |
    Plain paragraph.

- label: "Section label:"
  text: |
    Labeled paragraph body.
```

### Inline formatting in `text`

- `*emphasis*` → *emphasis*
- `**strong**` → **strong**
- `[label](https://example.com)` → link

Everything else is HTML-escaped automatically.

## Config file

```yaml
yaml_dir: yaml
html_dir: html
template_path: template.html
deploy_dir: /path/to/web/cover_letters   # or null to skip
```

Paths are relative to the project root unless absolute.

## nginx example

```nginx
location = /cover/acme {
    try_files /cover_letters/Acme.html =404;
}
```

Ensure your stylesheet path (`css_href` in letter YAML) resolves from the served HTML location.
