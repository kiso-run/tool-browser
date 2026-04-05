from __future__ import annotations


_VALID_ACTIONS = {
    "navigate",
    "text",
    "links",
    "forms",
    "snapshot",
    "click",
    "fill",
    "screenshot",
}


def validate_args(args: dict, context: dict) -> list[str]:
    errors: list[str] = []
    action = args.get("action")
    if not isinstance(action, str) or not action.strip():
        return errors
    action = action.strip()
    if action not in _VALID_ACTIONS:
        errors.append(
            "action must be one of: navigate, text, links, forms, snapshot, click, fill, screenshot"
        )
        return errors
    if action == "navigate" and not str(args.get("url", "")).strip():
        errors.append("navigate requires non-empty `url`.")
    if action == "click" and not str(args.get("element", "")).strip():
        errors.append("click requires non-empty `element`.")
    if action == "fill":
        if not str(args.get("element", "")).strip():
            errors.append("fill requires non-empty `element`.")
        if not str(args.get("value", "")).strip():
            errors.append("fill requires non-empty `value`.")
    return errors


def repair_args(args: dict, context: dict) -> dict:
    repaired = dict(args)
    for field in ("action", "url", "selector", "element", "value"):
        if isinstance(repaired.get(field), str):
            repaired[field] = repaired[field].strip()
    return repaired
