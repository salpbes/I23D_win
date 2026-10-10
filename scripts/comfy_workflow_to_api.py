"""Turn a ComfyUI editor workflow (.json) into the API format that POST /prompt accepts.

The editor format stores widget values as a plain list, so the input names come from the running
ComfyUI's /object_info. Frontend-only nodes (notes) and muted/bypassed nodes are left out.

    python comfy_workflow_to_api.py template.json out_api.json [--server http://127.0.0.1:8188]
"""

from __future__ import annotations

import argparse
import json
import urllib.request

FRONTEND_ONLY = {"Note", "MarkdownNote", "Reroute", "PrimitiveNode"}
SEED_CONTROLS = {"fixed", "increment", "decrement", "randomize"}
MUTED, BYPASSED = 2, 4


def fetch_object_info(server: str) -> dict:
    with urllib.request.urlopen(f"{server}/object_info", timeout=60) as r:
        return json.load(r)


DYNAMIC_COMBO = "COMFY_DYNAMICCOMBO_V3"
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "COLOR", "LOAD_3D", DYNAMIC_COMBO}


def _is_widget(spec) -> bool:
    kind = spec[0]
    return isinstance(kind, list) or kind in WIDGET_TYPES


def _ordered(spec: dict) -> list:
    return list(spec.get("required", {}).items()) + list(spec.get("optional", {}).items())


def _take_widgets(ordered, values, linked, inputs, prefix=""):
    """Consume editor widget values in order. A dynamic combo's chosen option adds its own
    widgets straight after it, sent to the API as "<combo>.<name>"."""
    for name, s in ordered:
        key = prefix + name
        if _is_widget(s) and not values and key not in linked and "default" in s[1]:
            inputs[key] = s[1]["default"]  # input added to ComfyUI after the workflow was saved
        elif _is_widget(s) and values:
            value = values.pop(0)
            if s[0] == "INT" and values and values[0] in SEED_CONTROLS:
                values.pop(0)  # "control after generate" lives only in the editor
            if key not in linked:
                inputs[key] = value
            if s[0] == DYNAMIC_COMBO:
                option = next((o for o in s[1]["options"] if o["key"] == value), None)
                if option:
                    _take_widgets(_ordered(option["inputs"]), values, linked, inputs, key + ".")


def convert(workflow: dict, info: dict) -> dict:
    nodes = {n["id"]: n for n in workflow["nodes"]}
    links = {l[0]: (l[1], l[2]) for l in workflow["links"]}  # link id -> (from node, from slot)
    api = {}
    for node in workflow["nodes"]:
        kind = node["type"]
        if kind in FRONTEND_ONLY or node.get("mode") in (MUTED, BYPASSED):
            continue
        if kind not in info:
            raise KeyError(f"ComfyUI has no node type {kind!r} (node {node['id']})")
        linked = {i["name"]: links[i["link"]] for i in node.get("inputs", [])
                  if i.get("link") is not None and i["link"] in links}
        values = node.get("widgets_values") or []
        values = [] if isinstance(values, dict) else list(values)  # named values: use defaults
        inputs = {}
        _take_widgets(_ordered(info[kind]["input"]), values, linked, inputs)
        for name, (src, slot) in linked.items():
            if nodes[src]["type"] in FRONTEND_ONLY or nodes[src].get("mode") in (MUTED, BYPASSED):
                continue
            inputs[name] = [str(src), slot]
        api[str(node["id"])] = {"class_type": kind, "inputs": inputs,
                                "_meta": {"title": node.get("title") or kind}}
    return api


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("output")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    args = ap.parse_args()
    with open(args.workflow, encoding="utf-8") as f:
        workflow = json.load(f)
    api = convert(workflow, fetch_object_info(args.server))
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(api, f, indent=1)
    print(f"{len(api)} nodes -> {args.output}")


if __name__ == "__main__":
    main()
