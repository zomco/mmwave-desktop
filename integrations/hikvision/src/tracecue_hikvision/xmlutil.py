"""Defensive XML helpers for untrusted NVR responses."""

from __future__ import annotations

from xml.etree import ElementTree

from .errors import UnsafePayloadError


MAX_XML_DEPTH = 32


def parse_xml(content: bytes) -> ElementTree.Element:
    prefix = content[:4096].upper()
    if b"<!DOCTYPE" in prefix or b"<!ENTITY" in prefix:
        raise UnsafePayloadError("XML declarations with DTD or entities are not accepted")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise UnsafePayloadError("NVR returned malformed XML") from exc
    stack: list[tuple[ElementTree.Element, int]] = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        if depth > MAX_XML_DEPTH:
            raise UnsafePayloadError("NVR XML exceeds the maximum nesting depth")
        stack.extend((child, depth + 1) for child in element)
    return root


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children(element: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in element.iter() if local_name(child.tag) == name]


def text(element: ElementTree.Element, name: str) -> str | None:
    for child in element.iter():
        if local_name(child.tag) == name and child.text:
            return child.text.strip()
    return None

