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
python3 build.py acme example     # specific slug(s)
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
| `date` | yes | ISO date (`2026-01-15`) |
| `title` | no | Job title in header (default: config `author.title`) |
| `location` | no | Location in header (default: config `author.location`) |
| `remote` | no | Show `(Remote)` under location |
| `salutation` | no | Opening line (`Dear Acme,`) |
| `paragraphs` | no | Body blocks (see below) |
| `closing` | no | Final paragraph before signature |
| `output` | no | Output filename (default: `{slug}.html`) |
| `page_title` | no | Browser tab title |
| `date_display` | no | Human date (auto-generated from `date`) |
| `signature` | no | Sign-off name in footer (default: config `author.signature`, else first word of `author.name`) |
| `css_href` | no | Stylesheet path (default: `/cover_letters/cover-letter.css`) |
| `js_href` | no | Script path for viewport warning (default: `/cover_letters/cover-letter.js`) |

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
css_path: cover-letter.css
js_path: cover-letter.js
css_href: /cover_letters/cover-letter.css
js_href: /cover_letters/cover-letter.js
min_viewport_width: 850
deploy_dir: /path/to/web/cover_letters   # or null to skip

author:
  name: Your Full Name
  # signature: Alex   # optional; defaults to first word of author.name
  title: Your Default Job Title
  location: City, ST
  remote: false
  email: you@example.com
  phone: 555-555-5555
  linkedin: https://linkedin.com/in/you
  github: https://github.com/you
```

Paths are relative to the project root unless absolute. The `author` block is your
resume-style header (defaults for every letter). Override `title`, `location`, or
`remote` in an individual letter YAML when needed.

## nginx example

```nginx
location = /cover/acme {
    try_files /cover_letters/Acme.html =404;
}
```

`cover-letter.css` is self-contained (desk/paper styling, typography, contact header, toast).
Ensure `css_href` and `js_href` resolve from your web root when deploying.
