"""Readable YAML output for layout files: small mappings (rects, grid blocks) on one line."""

from __future__ import annotations

from typing import Any

import yaml

from workplace_domain.config import LayoutFile

_FLOW_MAX_KEYS = 6


class _LayoutDumper(yaml.SafeDumper):
    pass


def _represent_dict(dumper: yaml.SafeDumper, data: dict[str, Any]) -> yaml.Node:
    flat = all(not isinstance(v, dict | list) for v in data.values())
    return dumper.represent_mapping(
        "tag:yaml.org,2002:map", data, flow_style=flat and len(data) <= _FLOW_MAX_KEYS
    )


_LayoutDumper.add_representer(dict, _represent_dict)


def dump_layout(layout: LayoutFile) -> str:
    data = layout.model_dump(mode="json", exclude_defaults=True)
    return yaml.dump(data, Dumper=_LayoutDumper, sort_keys=False, width=100, allow_unicode=True)
