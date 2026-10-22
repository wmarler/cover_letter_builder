#!/usr/bin/env python3
"""Build cover letter HTML from YAML sources."""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"
EXCLUDED_YAML = {"template.yaml"}

NGINX_SLUG_MARKER_RE = re.compile(r"^#\s*cover_letter_builder\s+slug=(\S+)\s*$")
NGINX_LOCATION_LINE_RE = re.compile(
    r"^\s*location\s*=\s*(?P<location>/\S+)\s*\{\s*try_files\s+(?P<try_files>/\S+)\s+=404;\s*\}\s*$"
)

INLINE_MARKUP_RE = re.compile(
    r"\*\*(.+?)\*\*|\*(.+?)\*|\[(.+?)\]\((.+?)\)",
    re.DOTALL,
)


@dataclass
class AuthorConfig:
    name: str
    email: str
    phone: str
    linkedin: str
    github: str
    title: str
    location: str
    signature: str | None = None
    remote: bool = False


@dataclass
class BuildConfig:
    yaml_dir: Path
    html_dir: Path
    template_path: Path
    deploy_dir: Path | None
    css_href: str
    css_path: Path | None
    js_href: str
    js_path: Path | None
    min_viewport_width: int
    nginx_locations_path: Path | None
    nginx_try_files_prefix: str
    author: AuthorConfig


@dataclass
class NginxLocationEntry:
    slug: str
    location: str
    try_files: str


def normalize_date(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


def format_display_date(iso_date) -> str:
    if hasattr(iso_date, "day") and hasattr(iso_date, "strftime"):
        parsed = iso_date
    else:
        parsed = datetime.strptime(str(iso_date), "%Y-%m-%d")
    return f"{parsed.day} {parsed.strftime('%B')}, {parsed.year}"


def link_label(url: str) -> str:
    cleaned = url.strip()
    for prefix in ("https://", "http://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    return cleaned.rstrip("/")


def render_contact_table(
    title: str,
    location: str,
    remote: bool,
    email: str,
    phone: str,
    linkedin: str,
    github: str,
) -> str:
    email_link = (
        f'<a href="mailto:{html.escape(email)}">{html.escape(email)}</a>'
    )
    linkedin_link = (
        f'<a href="{html.escape(linkedin, quote=True)}">'
        f"{html.escape(link_label(linkedin))}</a>"
    )
    github_link = (
        f'<a href="{html.escape(github, quote=True)}">'
        f"{html.escape(link_label(github))}</a>"
    )
    remote_cell = "(Remote)" if remote else ""

    return f"""      <div class="letter-contact-row">
        <div class="letter-contact-title">{html.escape(title)}</div>
        <table class="letter-contact-table">
          <colgroup>
            <col class="letter-contact-col">
            <col class="letter-contact-col">
            <col class="letter-contact-col">
          </colgroup>
          <tr>
            <td>{html.escape(location)}</td>
            <td>{email_link}</td>
            <td>{linkedin_link}</td>
          </tr>
          <tr>
            <td>{html.escape(remote_cell)}</td>
            <td>{html.escape(phone)}</td>
            <td>{github_link}</td>
          </tr>
        </table>
      </div>"""


def render_inline(text: str) -> str:
    """Escape plain text but allow *em*, **strong**, and [links](url)."""
    parts: list[str] = []
    pos = 0
    for match in INLINE_MARKUP_RE.finditer(text):
        parts.append(html.escape(text[pos : match.start()]))
        if match.group(1) is not None:
            parts.append(f"<strong>{html.escape(match.group(1))}</strong>")
        elif match.group(2) is not None:
            parts.append(f"<em>{html.escape(match.group(2))}</em>")
        elif match.group(3) is not None:
            href = html.escape(match.group(4), quote=True)
            label = html.escape(match.group(3))
            parts.append(f'<a href="{href}">{label}</a>')
        pos = match.end()
    parts.append(html.escape(text[pos:]))
    return "".join(parts)


def render_paragraph(text: str, label: str | None = None) -> str:
    body = render_inline(text.strip())
    if label:
        label_html = html.escape(label.strip())
        return f"      <p><strong>{label_html}</strong> {body}</p>"
    return f"      <p>{body}</p>"


def build_body(data: dict) -> str:
    blocks: list[str] = []

    salutation = data.get("salutation", "").strip()
    if salutation:
        blocks.append(render_paragraph(salutation))

    for paragraph in data.get("paragraphs", []):
        if not isinstance(paragraph, dict):
            raise ValueError(f"Each paragraph must be a mapping, got {type(paragraph)!r}")
        text = paragraph.get("text", "")
        if not str(text).strip():
            raise ValueError(f"Paragraph in {data.get('slug')} is missing text")
        blocks.append(render_paragraph(str(text), paragraph.get("label")))

    closing = data.get("closing", "").strip()
    if closing:
        blocks.append(render_paragraph(closing))

    return "\n\n".join(blocks)


def validate(data: dict, source: Path) -> None:
    required = ("slug", "company", "date")
    missing = [field for field in required if not data.get(field)]
    if missing:
        raise ValueError(f"{source.name}: missing required field(s): {', '.join(missing)}")

    normalize_date(data["date"])
    datetime.strptime(normalize_date(data["date"]), "%Y-%m-%d")


def resolve_author(raw: dict[str, Any], config_path: Path) -> AuthorConfig:
    author = raw.get("author")
    if not isinstance(author, dict):
        raise ValueError(f"{config_path.name}: missing required 'author' mapping")

    required = ("name", "email", "phone", "linkedin", "github", "title", "location")
    missing = [field for field in required if not author.get(field)]
    if missing:
        raise ValueError(f"{config_path.name}: author missing field(s): {', '.join(missing)}")

    return AuthorConfig(
        name=str(author["name"]),
        email=str(author["email"]),
        phone=str(author["phone"]),
        linkedin=str(author["linkedin"]),
        github=str(author["github"]),
        title=str(author["title"]),
        location=str(author["location"]),
        signature=str(author["signature"]) if author.get("signature") else None,
        remote=bool(author.get("remote", False)),
    )


def letter_field(data: dict, author: AuthorConfig, field: str) -> Any:
    if field in data and data[field] is not None:
        return data[field]
    return getattr(author, field)


def render_letter(data: dict, template: str, author: AuthorConfig, config: BuildConfig) -> str:
    company = data["company"]
    date_iso = normalize_date(data["date"])
    date_display = data.get("date_display") or format_display_date(data["date"])
    page_title = data.get("page_title") or f"Cover Letter — {author.name} — {company}"
    signature = (
        data.get("signature")
        or author.signature
        or (author.name.split()[0] if author.name else "")
    )

    title = str(letter_field(data, author, "title"))
    location = str(letter_field(data, author, "location"))
    remote = bool(data["remote"]) if "remote" in data else author.remote

    body = build_body(data)
    contact_table = render_contact_table(
        title, location, remote,
        author.email, author.phone, author.linkedin, author.github,
    )

    replacements = {
        "{{PAGE_TITLE}}": html.escape(page_title),
        "{{CSS_HREF}}": html.escape(data.get("css_href", config.css_href), quote=True),
        "{{JS_HREF}}": html.escape(data.get("js_href", config.js_href), quote=True),
        "{{MIN_VIEWPORT_WIDTH}}": str(
            int(data.get("min_viewport_width", config.min_viewport_width))
        ),
        "{{AUTHOR_NAME}}": html.escape(author.name),
        "{{CONTACT_TABLE}}": contact_table,
        "{{DATE_ISO}}": html.escape(date_iso),
        "{{DATE_DISPLAY}}": html.escape(date_display),
        "{{BODY}}": body,
        "{{SIGNATURE}}": html.escape(signature),
    }

    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    return rendered


def output_name(data: dict) -> str:
    return data.get("output") or f"{data['slug']}.html"


def nginx_location_path(data: dict) -> str:
    path = str(data.get("nginx_path") or f"/{data['slug']}").strip()
    if not path.startswith("/"):
        raise ValueError(
            f"{data.get('slug')}: nginx_path must start with '/' (got {path!r})"
        )
    return path


def nginx_try_files_path(config: BuildConfig, data: dict) -> str:
    prefix = config.nginx_try_files_prefix.rstrip("/")
    return f"{prefix}/{output_name(data)}"


def nginx_location_entry(data: dict, config: BuildConfig) -> NginxLocationEntry:
    return NginxLocationEntry(
        slug=str(data["slug"]),
        location=nginx_location_path(data),
        try_files=nginx_try_files_path(config, data),
    )


def format_nginx_location_block(entry: NginxLocationEntry) -> str:
    return (
        f"# cover_letter_builder slug={entry.slug}\n"
        f"  location = {entry.location} {{ try_files {entry.try_files} =404; }}\n"
    )


def parse_nginx_locations(text: str) -> dict[str, NginxLocationEntry]:
    entries: dict[str, NginxLocationEntry] = {}
    pending_slug: str | None = None
    for line in text.splitlines():
        marker = NGINX_SLUG_MARKER_RE.match(line)
        if marker:
            pending_slug = marker.group(1)
            continue
        location_match = NGINX_LOCATION_LINE_RE.match(line)
        if location_match and pending_slug:
            entries[pending_slug] = NginxLocationEntry(
                slug=pending_slug,
                location=location_match.group("location"),
                try_files=location_match.group("try_files"),
            )
            pending_slug = None
    return entries


def render_nginx_locations(entries: dict[str, NginxLocationEntry]) -> str:
    header = (
        "# Generated by cover_letter_builder — do not edit manually.\n"
        "# Include from your nginx server block, then reload:\n"
        "#   nginx -t && systemctl reload nginx\n"
        "\n"
    )
    blocks = [
        format_nginx_location_block(entries[slug])
        for slug in sorted(entries.keys())
    ]
    return header + "\n".join(blocks)


def update_nginx_locations(
    config: BuildConfig, built: list[NginxLocationEntry]
) -> bool:
    if config.nginx_locations_path is None or not built:
        return False

    path = config.nginx_locations_path
    existing: dict[str, NginxLocationEntry] = {}
    if path.exists():
        existing = parse_nginx_locations(path.read_text(encoding="utf-8"))

    for entry in built:
        existing[entry.slug] = entry

    rendered = render_nginx_locations(existing)
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    if rendered == previous:
        return False

    path.write_text(rendered, encoding="utf-8")
    return True


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a YAML mapping at top level")
    return data


def resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def load_config(config_path: Path) -> BuildConfig:
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_path}\n"
            f"Copy config.template.yaml to config.yaml and edit paths."
        )

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise ValueError(f"{config_path.name}: expected a YAML mapping at top level")

    required = ("yaml_dir", "html_dir", "template_path")
    missing = [field for field in required if not raw.get(field)]
    if missing:
        raise ValueError(f"{config_path.name}: missing required field(s): {', '.join(missing)}")

    deploy_raw = raw.get("deploy_dir")
    deploy_dir = None if deploy_raw in (None, "", "null") else resolve_path(ROOT, str(deploy_raw))

    css_path_raw = raw.get("css_path")
    css_path = None if css_path_raw in (None, "", "null") else resolve_path(ROOT, str(css_path_raw))

    js_path_raw = raw.get("js_path")
    js_path = None if js_path_raw in (None, "", "null") else resolve_path(ROOT, str(js_path_raw))

    min_viewport_width = int(raw.get("min_viewport_width", 850))

    nginx_raw = raw.get("nginx_locations_path")
    if nginx_raw in (None, "", "null"):
        nginx_locations_path = None
    else:
        nginx_locations_path = resolve_path(ROOT, str(nginx_raw))

    nginx_try_files_prefix = str(raw.get("nginx_try_files_prefix", "/cover_letters")).strip()
    if not nginx_try_files_prefix.startswith("/"):
        raise ValueError(
            f"{config_path.name}: nginx_try_files_prefix must start with '/'"
        )

    return BuildConfig(
        yaml_dir=resolve_path(ROOT, str(raw["yaml_dir"])),
        html_dir=resolve_path(ROOT, str(raw["html_dir"])),
        template_path=resolve_path(ROOT, str(raw["template_path"])),
        deploy_dir=deploy_dir,
        css_href=str(raw.get("css_href", "/cover_letters/cover-letter.css")),
        css_path=css_path,
        js_href=str(raw.get("js_href", "/cover_letters/cover-letter.js")),
        js_path=js_path,
        min_viewport_width=min_viewport_width,
        nginx_locations_path=nginx_locations_path,
        nginx_try_files_prefix=nginx_try_files_prefix,
        author=resolve_author(raw, config_path),
    )


def deploy_assets(config: BuildConfig) -> None:
    if config.deploy_dir is None:
        return
    config.deploy_dir.mkdir(parents=True, exist_ok=True)
    for asset_path in (config.css_path, config.js_path):
        if asset_path is None or not asset_path.exists():
            continue
        dest = config.deploy_dir / asset_path.name
        shutil.copy2(asset_path, dest)
        print(f"  copied {dest}")


def build_one(
    source: Path, template: str, config: BuildConfig, deploy: bool
) -> tuple[Path, NginxLocationEntry]:
    data = load_yaml(source)
    validate(data, source)
    rendered = render_letter(data, template, config.author, config)
    config.html_dir.mkdir(parents=True, exist_ok=True)

    destination = config.html_dir / output_name(data)
    destination.write_text(rendered, encoding="utf-8")
    print(f"  wrote {destination}")

    if deploy and config.deploy_dir is not None:
        config.deploy_dir.mkdir(parents=True, exist_ok=True)
        deployed = config.deploy_dir / destination.name
        shutil.copy2(destination, deployed)
        print(f"  copied {deployed}")

    return destination, nginx_location_entry(data, config)


def discover_sources(config: BuildConfig, selected: list[str] | None) -> list[Path]:
    if selected:
        paths = []
        for slug in selected:
            candidate = config.yaml_dir / (slug if slug.endswith(".yaml") else f"{slug}.yaml")
            if not candidate.exists():
                raise FileNotFoundError(f"No YAML file found: {candidate}")
            paths.append(candidate)
        return paths

    return sorted(
        path
        for path in config.yaml_dir.glob("*.yaml")
        if path.name not in EXCLUDED_YAML
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build cover letter HTML from YAML.")
    parser.add_argument(
        "slugs",
        nargs="*",
        help="YAML slug(s) to build (default: all files in yaml/, except template.yaml)",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config YAML (default: ./config.yaml)",
    )
    parser.add_argument(
        "--no-deploy",
        action="store_true",
        help="Skip copying built HTML to deploy_dir from config",
    )
    args = parser.parse_args()

    try:
        config = load_config(Path(args.config))
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not config.template_path.exists():
        print(f"Missing template: {config.template_path}", file=sys.stderr)
        return 1

    template = config.template_path.read_text(encoding="utf-8")
    sources = discover_sources(config, args.slugs or None)
    if not sources:
        print(f"No YAML files found in {config.yaml_dir}", file=sys.stderr)
        return 1

    deploy = not args.no_deploy and config.deploy_dir is not None
    if not args.no_deploy and config.deploy_dir is None:
        print("Note: deploy_dir not set in config; skipping deployment.")

    print(f"Building {len(sources)} letter(s)...")
    try:
        nginx_entries: list[NginxLocationEntry] = []
        for source in sources:
            print(source.name + ":")
            _, nginx_entry = build_one(source, template, config, deploy=deploy)
            nginx_entries.append(nginx_entry)
        if deploy:
            deploy_assets(config)
        if update_nginx_locations(config, nginx_entries):
            path = config.nginx_locations_path
            assert path is not None
            print(f"Modified {path}")
            print("Reload nginx when ready: nginx -t && systemctl reload nginx")
    except (ValueError, yaml.YAMLError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
