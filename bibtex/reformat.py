#!/usr/bin/env python3
"""
Transform a references HTML section by:
1) Grouping each reference <div> (with a <p> inside) under per-year <h2> headers.
2) Converting DOI links like:
   <a href="https://doi.org/10.xxxx/yyy">https://doi.org/10.xxxx/yyy</a>
   into:
   <span>doi: <a href="https://doi.org/10.xxxx/yyy">10.xxxx/yyy</a></span>
3) Making every occurrence of "Todd, R. E." bold (<strong>).

Usage:
  python refs_transform.py input.html -o output.html
"""

from __future__ import annotations

import argparse
import re
from collections import OrderedDict
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag


YEAR_RE = re.compile(r"\((\d{4})(?:[a-z])?\)")
DOI_HREF_RE = re.compile(r"^https?://doi\.org/(.+)$", re.IGNORECASE)


def extract_year(p_text: str) -> Optional[str]:
    """Extract the 4-digit year from a reference paragraph text."""
    m = YEAR_RE.search(p_text)
    return m.group(1) if m else None


def convert_doi_links_in_p(p: Tag, soup: BeautifulSoup) -> None:
    """
    Convert DOI anchor patterns:
      <a href="https://doi.org/10.x/yyy">https://doi.org/10.x/yyy</a>
    to:
      <span>doi: <a href="https://doi.org/10.x/yyy">10.x/yyy</a></span>
    """
    for a in list(p.find_all("a", href=True)):
        href = a.get("href", "").strip()
        m = DOI_HREF_RE.match(href)
        if not m:
            continue

        doi = m.group(1).strip()
        # Only transform when the link text looks like the full DOI URL
        a_text = a.get_text(strip=True)
        if a_text.lower() not in {href.lower(), f"https://doi.org/{doi}".lower()}:
            continue

        span = soup.new_tag("span")
        span.append(NavigableString("doi: "))

        new_a = soup.new_tag("a", href=href)
        new_a.string = doi
        span.append(new_a)

        a.replace_with(span)


def bold_substring_in_p(p: Tag, soup: BeautifulSoup, author: str = "Todd, R. E.") -> None:
    """
    Wrap occurrences of the exact author string inside <strong>, without
    flattening other markup (em, a, etc.). Works by scanning text nodes.
    """
    for text_node in list(p.find_all(string=True)):
        if not isinstance(text_node, NavigableString):
            continue
        if isinstance(text_node, Tag):  # defensive; bs4 sometimes surprises
            continue

        s = str(text_node)
        if author not in s:
            continue

        parts = s.split(author)
        parent = text_node.parent
        if parent is None:
            continue

        # Build replacement sequence
        new_nodes = []
        for i, part in enumerate(parts):
            if part:
                new_nodes.append(NavigableString(part))
            if i != len(parts) - 1:
                strong = soup.new_tag("strong")
                strong.string = author
                new_nodes.append(strong)

        # Replace the original text node with the new nodes
        for node in reversed(new_nodes):
            text_node.insert_after(node)
        text_node.extract()


def group_refs_by_year(soup: BeautifulSoup) -> None:
    """
    Find <div id="refs" ...> and regroup its direct child reference divs
    under <h2>YEAR</h2> headers, sorted by year (descending).
    """
    refs = soup.find("div", id="refs")
    if not refs or not isinstance(refs, Tag):
        return

    # Collect direct child divs that contain a <p> (your ref blocks)
    ref_divs = []
    for child in list(refs.children):
        if isinstance(child, Tag) and child.name == "div" and child.find("p"):
            ref_divs.append(child)

    if not ref_divs:
        return

    # Group by year while preserving per-year encounter order
    grouped: "OrderedDict[str, list[Tag]]" = OrderedDict()
    unknown = []

    for ref_div in ref_divs:
        p = ref_div.find("p")
        year = extract_year(p.get_text(" ", strip=False) if p else "")
        if year is None:
            unknown.append(ref_div)
            continue
        grouped.setdefault(year, []).append(ref_div)

    # Clear only the collected ref divs (leave other nodes like whitespace/comments alone)
    for ref_div in ref_divs:
        ref_div.extract()

    # Insert rebuilt content at the end of refs
    years_sorted = sorted(grouped.keys(), reverse=True)
    for year in years_sorted:
        h2 = soup.new_tag("h2")
        h2.string = year
        refs.append(h2)
        for ref_div in grouped[year]:
            refs.append(ref_div)

    if unknown:
        h2 = soup.new_tag("h2")
        h2.string = "Unknown year"
        refs.append(h2)
        for ref_div in unknown:
            refs.append(ref_div)


def transform_html(html: str, embolden=tuple()) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml")

    # Transform each reference paragraph (DOI + bold author)
    refs = soup.find("div", id="refs")
    if refs and isinstance(refs, Tag):
        for p in refs.find_all("p"):
            convert_doi_links_in_p(p, soup)
            for substring in embolden:
                bold_substring_in_p(p, soup, author=substring)

        # Then regroup under year headers
        group_refs_by_year(soup)

    # Return full document
    return soup


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_html", help="Path to input .html file")
    ap.add_argument("--bold", "-b", type=argparse.FileType('r'), help="Line-delineated text file of authors to highlight.")
    ap.add_argument("--rm-html-body", action="store_true", help="Remove <html> and <body> tags from output (for embedding in other pages)")
    ap.add_argument("-o", "--output", default=None, help="Path to output .html file (default: stdout)")
    args = ap.parse_args()

    bold_authors = []
    if args.bold:
        for line in args.bold:
            line = line.strip()
            if line:
                bold_authors.append(line.strip())

    with open(args.input_html, "r", encoding="utf-8") as f:
        html = f.read()

    soup = transform_html(html, embolden=tuple(bold_authors))

    if args.rm_html_body:
        if soup.body:
            soup.body.unwrap()
        if soup.html:
            soup.html.unwrap()
        if top_div:= soup.find("div"):
            top_div.unwrap()

    # soup as string and remove blank lines
    html_str = soup.decode(formatter="minimal")
    html_str = "\n".join(
        line for line in html_str.splitlines()
        if line.strip() )
    if html_str.startswith('<h2>'):
        html_str = '<h2>' + html_str[4:].replace("<h2>", "\n<h2>").replace('</h2>',"</h2>\n")
        html_str = html_str.replace("<p>", "  <p>")

    # output result
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html_str)
    else:
        print(html_str)


if __name__ == "__main__":
    main()
