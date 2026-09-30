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
    remote: bool = False


@dataclass
class BuildConfig:
    yaml_dir: Path
    html_dir: Path
    template_path: Path
    deploy_dir: Path | None
    letter_css_href: str
    css_href: str
    css_path: Path | None
    author: AuthorConfig


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

    return f"""      <table class="letter-contact-table">
        <colgroup>
          <col class="letter-contact-col">
          <col class="letter-contact-col">
          <col class="letter-contact-col">
          <col class="letter-contact-col">
        </colgroup>
        <tr>
          <td>{html.escape(title)}</td>
          <td>{html.escape(location)}</td>
          <td>{email_link}</td>
          <td>{linkedin_link}</td>
        </tr>
        <tr>
          <td></td>
          <td>{html.escape(remote_cell)}</td>
          <td>{html.escape(phone)}</td>
          <td>{github_link}</td>
        </tr>
      </table>"""


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
    signature = data.get("signature", author.name.split()[0] if author.name else "Will")

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
        "{{LETTER_CSS_HREF}}": html.escape(
            data.get("letter_css_href", config.letter_css_href), quote=True
        ),
        "{{CSS_HREF}}": html.escape(data.get("css_href", config.css_href), quote=True),
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

    return BuildConfig(
        yaml_dir=resolve_path(ROOT, str(raw["yaml_dir"])),
        html_dir=resolve_path(ROOT, str(raw["html_dir"])),
        template_path=resolve_path(ROOT, str(raw["template_path"])),
        deploy_dir=deploy_dir,
        letter_css_href=str(raw.get("letter_css_href", "/letter.css")),
        css_href=str(raw.get("css_href", "/cover_letters/cover-letter.css")),
        css_path=css_path,
        author=resolve_author(raw, config_path),
    )


def deploy_assets(config: BuildConfig) -> None:
    if config.deploy_dir is None:
        return
    if config.css_path is None or not config.css_path.exists():
        return
    css_dest = config.deploy_dir / config.css_path.name
    config.deploy_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config.css_path, css_dest)
    print(f"  copied {css_dest}")


def build_one(source: Path, template: str, config: BuildConfig, deploy: bool) -> Path:
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

    return destination


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
        for source in sources:
            print(source.name + ":")
            build_one(source, template, config, deploy=deploy)
        if deploy:
            deploy_assets(config)
    except (ValueError, yaml.YAMLError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
